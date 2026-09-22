import json
from pathlib import Path

import pytest

from ghostnet.evidence_hash import (
    TEXT_HASH_METHOD,
    text_evidence_sha256,
    validate_text_evidence,
)

ROOT = Path(__file__).resolve().parents[1]


def test_lf_and_crlf_share_identity_but_changed_evidence_does_not(tmp_path):
    source = tmp_path / "evidence.json"
    lf = b'{\n  "value": 12, "name": "coast"\n}\n'
    source.write_bytes(lf)
    expected = text_evidence_sha256(source)
    source.write_bytes(lf.replace(b"\n", b"\r\n"))
    validate_text_evidence(source, expected, TEXT_HASH_METHOD)
    for changed in (lf.replace(b"12", b"13"), lf.replace(b"  ", b" "), lf.rstrip()):
        source.write_bytes(changed)
        with pytest.raises(ValueError, match="mismatch"):
            validate_text_evidence(source, expected, TEXT_HASH_METHOD)
    with pytest.raises(ValueError, match="Unsupported"):
        validate_text_evidence(source, expected, "sha256")


@pytest.mark.parametrize("newline", [b"\n", b"\r\n"])
def test_committed_calibration_source_is_portable(tmp_path, newline):
    recorded = json.loads((ROOT / "eval/drift_calibration.json").read_text("utf-8"))
    raw = (ROOT / "eval/drift_temporal.json").read_bytes().replace(b"\r\n", b"\n")
    source = tmp_path / "source.json"
    source.write_bytes(raw.replace(b"\n", newline))
    validate_text_evidence(source, recorded["source_sha256"], recorded["source_hash_method"])
