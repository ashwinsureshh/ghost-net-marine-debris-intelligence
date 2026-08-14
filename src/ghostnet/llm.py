"""Claude API integration for operator-facing rationale text (FR-6.3).

Scope note: the LLM is deliberately confined to *explaining* the plan, not
producing it. Every number a rationale mentions is computed by the agents and
handed to the model as structured input; the model turns that evidence into a
sentence a cleanup coordinator can act on. Nothing in the ranking, the drift
model or the capacity constraint depends on an API call — which is what keeps
PRD §8's reproducibility requirement true ("given the same input tiles and time
window, the pipeline must produce the same verified detections and ranked
plan").

That is also why the offline path is a first-class code path and not an error
case: with no ``ANTHROPIC_API_KEY``, or when the API errors, this module falls
back to a deterministic template and marks the rationale's ``source`` as
``"template"`` so the provenance is visible in the output rather than implied.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from ghostnet.config import load_dotenv_if_present

logger = logging.getLogger(__name__)

# Claude Opus 5. Thinking is on by default on this model; effort is left at
# "low" because rationale writing is a short, well-specified formatting task
# over evidence that has already been computed.
DEFAULT_MODEL = "claude-opus-5"
DEFAULT_EFFORT = "low"
MAX_TOKENS = 4096

SYSTEM_PROMPT = """\
You write the rationale lines for a marine-debris cleanup dispatch plan that a \
human coordinator reviews before any vessel is sent.

Rules:
- Use only the evidence given for each site. Never introduce a number, place \
name, vessel or date that is not in the input.
- One rationale per site, 1-2 sentences, plain prose, no bullet points, no \
markdown, no preamble.
- Lead with why this site outranks the others, then the single most \
decision-relevant caveat.
- Source attribution is a probability distribution: write "most likely" or \
"probable", never "the source is".
- Dark-vessel presence is a research signal for investigation. Never state or \
imply that a vessel did something illegal.
- This is a research prototype validated on historical data. Do not describe \
the plan as operational or the recommendation as final.
"""


@dataclass
class RationaleRequest:
    """Everything the model is allowed to know about one candidate site."""

    detection_id: str
    score: float
    components: dict[str, float] = field(default_factory=dict)
    verification_summary: str = ""
    drift_summary: str = ""
    top_rivers: list[tuple[str, float]] = field(default_factory=list)
    dark_vessel_count: int = 0
    nearest_mpa_km: float | None = None

    def as_prompt_block(self) -> str:
        lines = [
            f"site_id: {self.detection_id}",
            f"priority_score: {self.score:.3f}",
            "score_components: "
            + ", ".join(f"{k}={v:.2f}" for k, v in sorted(self.components.items())),
        ]
        if self.verification_summary:
            lines.append(f"verification: {self.verification_summary}")
        if self.drift_summary:
            lines.append(f"drift: {self.drift_summary}")
        if self.top_rivers:
            ranked = "; ".join(f"{n} p={p:.2f}" for n, p in self.top_rivers)
            lines.append(f"probable_sources: {ranked}")
        else:
            lines.append("probable_sources: none identified")
        lines.append(f"dark_vessels_in_window: {self.dark_vessel_count}")
        if self.nearest_mpa_km is not None:
            lines.append(f"nearest_mpa_km: {self.nearest_mpa_km:.1f}")
        else:
            lines.append("nearest_mpa_km: unknown (Protected Planet data not loaded)")
        return "\n".join(lines)


class _Rationale(BaseModel):
    detection_id: str = Field(description="Echo the site_id exactly as given")
    rationale: str = Field(description="1-2 sentences of plain prose")


class _RationaleSet(BaseModel):
    rationales: list[_Rationale]


def render_template(request: RationaleRequest) -> str:
    """Deterministic rationale used offline and whenever the API path fails.

    Reads like a machine wrote it, which is the point: the plan must remain
    reviewable and reproducible with no network access at all.
    """
    parts: list[str] = []
    conf = request.components.get("detection_confidence")
    if conf is not None:
        parts.append(f"verified detection at confidence {conf:.2f}")
    if request.verification_summary:
        parts.append(request.verification_summary)
    if request.nearest_mpa_km is not None:
        parts.append(f"{request.nearest_mpa_km:.0f} km from the nearest MPA")
    if request.drift_summary:
        parts.append(request.drift_summary)
    if request.top_rivers:
        name, prob = request.top_rivers[0]
        parts.append(f"most likely source {name} (p={prob:.2f})")
    if request.dark_vessel_count:
        parts.append(
            f"{request.dark_vessel_count} AIS-silent vessel(s) in the window "
            "(investigation signal only)"
        )
    body = "; ".join(parts) if parts else "no distinguishing evidence recorded"
    # No prototype disclaimer here: the plan carries it in ``caveats`` and the
    # operator UI shows it in the header and again at the approval step.
    # Repeating it per site would push the actual evidence off the card.
    return f"Priority {request.score:.2f} — {body}."


class RationaleWriter:
    """Writes FR-6.3 rationales via Claude, falling back to templates offline.

    ``client`` is injectable so tests exercise the parsing and fallback paths
    without touching the network or needing a key.
    """

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        effort: str = DEFAULT_EFFORT,
        client: object | None = None,
        enabled: bool | None = None,
    ) -> None:
        self.model = model
        self.effort = effort
        self._client = client
        self._enabled = enabled

    @property
    def available(self) -> bool:
        """True when a rationale call would actually be attempted."""
        if self._enabled is not None:
            return self._enabled
        if self._client is not None:
            return True
        load_dotenv_if_present()
        return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())

    def _get_client(self):
        if self._client is not None:
            return self._client
        import anthropic  # imported lazily: the package must import without it

        self._client = anthropic.Anthropic()
        return self._client

    def write(self, requests: list[RationaleRequest]) -> dict[str, tuple[str, str]]:
        """Return ``{detection_id: (rationale, "llm" | "template")}``.

        Never raises: a failure here must degrade the plan's prose, not the
        plan. The reason is logged and the deterministic template used instead.
        """
        if not requests:
            return {}
        fallback = {r.detection_id: (render_template(r), "template") for r in requests}
        if not self.available:
            logger.info(
                "No ANTHROPIC_API_KEY — writing %d dispatch rationale(s) from "
                "the deterministic template.",
                len(requests),
            )
            return fallback

        try:
            parsed = self._call(requests)
        except Exception as exc:  # noqa: BLE001 - degrade, never fail the plan
            logger.warning(
                "Rationale generation failed (%s: %s); using templates instead.",
                type(exc).__name__,
                exc,
            )
            return fallback

        if parsed is None:
            return fallback

        out = dict(fallback)
        wanted = {r.detection_id for r in requests}
        for item in parsed.rationales:
            text = item.rationale.strip()
            if item.detection_id in wanted and text:
                out[item.detection_id] = (text, "llm")
        return out

    def _call(self, requests: list[RationaleRequest]) -> _RationaleSet | None:
        import anthropic

        client = self._get_client()
        blocks = "\n\n".join(r.as_prompt_block() for r in requests)
        user = (
            f"Write one rationale for each of the {len(requests)} sites below, "
            "in the order given.\n\n" + blocks
        )
        try:
            response = client.messages.parse(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                output_config={"effort": self.effort},
                output_format=_RationaleSet,
                messages=[{"role": "user", "content": user}],
            )
        except anthropic.RateLimitError:
            # Free-tier friendly: the plan is still valid without LLM prose.
            logger.warning("Anthropic rate limit hit; using template rationales.")
            return None
        except (anthropic.APIStatusError, anthropic.APIConnectionError) as exc:
            logger.warning("Anthropic API unavailable (%s); using templates.", exc)
            return None

        if response.stop_reason == "refusal":
            category = getattr(response.stop_details, "category", None)
            logger.warning(
                "Rationale request was declined (category=%s); using templates.",
                category,
            )
            return None
        if response.stop_reason == "max_tokens":
            logger.warning("Rationale response was truncated; using templates.")
            return None
        return response.parsed_output
