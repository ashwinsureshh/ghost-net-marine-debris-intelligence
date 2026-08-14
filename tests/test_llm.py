"""Claude integration for FR-6.3 rationales — including every offline path.

No test here touches the network. The fake clients below stand in for
``anthropic.Anthropic`` so the parsing, refusal and failure branches are all
exercised without a key.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from ghostnet.llm import (
    RationaleRequest,
    RationaleWriter,
    _Rationale,
    _RationaleSet,
    render_template,
)

REQUEST = RationaleRequest(
    detection_id="d-1",
    score=0.82,
    components={"detection_confidence": 0.91, "drift_urgency": 0.6},
    verification_summary="passed 5 false-positive checks",
    drift_summary="7-day forward track, envelope 30 km",
    top_rivers=[("Test Kali", 0.71), ("Small Creek", 0.18)],
    dark_vessel_count=2,
    nearest_mpa_km=12.4,
)


@dataclass
class _Response:
    parsed_output: Any
    stop_reason: str = "end_turn"
    stop_details: Any = None


class _FakeMessages:
    def __init__(self, response=None, error: Exception | None = None):
        self._response = response
        self._error = error
        self.calls: list[dict] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._response


class _FakeClient:
    def __init__(self, response=None, error: Exception | None = None):
        self.messages = _FakeMessages(response, error)


# --- the offline path ------------------------------------------------------


def test_template_is_deterministic_and_mentions_the_evidence():
    first = render_template(REQUEST)
    assert first == render_template(REQUEST)
    assert "0.82" in first
    assert "Test Kali" in first
    assert "12 km from the nearest MPA" in first
    assert "AIS-silent" in first
    assert "investigation signal only" in first
    # The prototype disclaimer deliberately lives on the plan's caveats and in
    # the operator UI, not on every site line — see render_template.
    assert "human review" not in first


def test_template_copes_with_a_site_that_has_almost_no_evidence():
    bare = RationaleRequest(detection_id="d-2", score=0.1)
    assert "no distinguishing evidence recorded" in render_template(bare)


def test_no_api_key_means_every_rationale_comes_from_the_template():
    writer = RationaleWriter(enabled=False)
    result = writer.write([REQUEST])
    assert result["d-1"][1] == "template"
    assert result["d-1"][0] == render_template(REQUEST)


def test_availability_follows_the_environment(monkeypatch):
    monkeypatch.setattr("ghostnet.llm.load_dotenv_if_present", lambda: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert RationaleWriter().available is False
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    assert RationaleWriter().available is True


def test_no_requests_means_no_call():
    writer = RationaleWriter(client=_FakeClient())
    assert writer.write([]) == {}


# --- the API path ----------------------------------------------------------


def test_a_successful_call_is_marked_as_llm_authored():
    client = _FakeClient(
        _Response(_RationaleSet(rationales=[_Rationale(detection_id="d-1", rationale="Top site.")]))
    )
    writer = RationaleWriter(client=client)
    result = writer.write([REQUEST])
    assert result["d-1"] == ("Top site.", "llm")


def test_the_request_uses_the_current_opus_model_and_carries_the_evidence():
    client = _FakeClient(_Response(_RationaleSet(rationales=[])))
    RationaleWriter(client=client).write([REQUEST])
    call = client.messages.calls[0]
    assert call["model"] == "claude-opus-5"
    assert call["output_format"] is _RationaleSet
    assert "Test Kali" in call["messages"][0]["content"]
    assert "never an accusation" not in call["system"]  # disclaimer lives on the data
    assert "not an accusation" in call["system"] or "illegal" in call["system"]


def test_a_rationale_for_an_unknown_site_is_ignored():
    client = _FakeClient(
        _Response(
            _RationaleSet(
                rationales=[
                    _Rationale(detection_id="d-1", rationale="Real."),
                    _Rationale(detection_id="d-999", rationale="Hallucinated site."),
                ]
            )
        )
    )
    result = RationaleWriter(client=client).write([REQUEST])
    assert set(result) == {"d-1"}


def test_a_blank_rationale_falls_back_to_the_template():
    client = _FakeClient(
        _Response(_RationaleSet(rationales=[_Rationale(detection_id="d-1", rationale="  ")]))
    )
    result = RationaleWriter(client=client).write([REQUEST])
    assert result["d-1"][1] == "template"


def test_a_missing_rationale_falls_back_to_the_template():
    client = _FakeClient(_Response(_RationaleSet(rationales=[])))
    result = RationaleWriter(client=client).write([REQUEST])
    assert result["d-1"] == (render_template(REQUEST), "template")


# --- failure modes: the plan must survive all of them ----------------------


def test_a_refusal_degrades_to_templates_rather_than_raising():
    class _Details:
        category = "cyber"

    client = _FakeClient(_Response(None, stop_reason="refusal", stop_details=_Details()))
    result = RationaleWriter(client=client).write([REQUEST])
    assert result["d-1"][1] == "template"


def test_a_truncated_response_degrades_to_templates():
    client = _FakeClient(_Response(None, stop_reason="max_tokens"))
    result = RationaleWriter(client=client).write([REQUEST])
    assert result["d-1"][1] == "template"


def test_an_api_exception_never_breaks_the_plan():
    client = _FakeClient(error=RuntimeError("connection reset"))
    result = RationaleWriter(client=client).write([REQUEST])
    assert result["d-1"][1] == "template"


def test_prompt_block_never_invents_fields_that_were_not_measured():
    bare = RationaleRequest(detection_id="d-3", score=0.4)
    block = bare.as_prompt_block()
    assert "probable_sources: none identified" in block
    assert "nearest_mpa_km: unknown" in block


@pytest.mark.parametrize("count", [0, 3])
def test_dark_vessel_count_is_always_stated(count):
    request = RationaleRequest(detection_id="d-4", score=0.5, dark_vessel_count=count)
    assert f"dark_vessels_in_window: {count}" in request.as_prompt_block()
