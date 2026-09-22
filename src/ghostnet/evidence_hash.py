"""Portable text-evidence identities; binary checkpoints retain raw-byte hashes.

sha256-utf8-lf-v1 decodes strict UTF-8, replaces CRLF with LF, then hashes
UTF-8 bytes. Nothing else is normalized: spaces, key order, numeric spelling,
final newline, BOM and lone CR remain significant. This tolerates Git newline
conversion without accepting changed evidence content or arbitrary reformatting.
"""

import hashlib
from pathlib import Path

TEXT_HASH_METHOD = "sha256-utf8-lf-v1"


def text_evidence_sha256(path: Path) -> str:
    text = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_text_evidence(path: Path, digest: str, method: str) -> None:
    if method != TEXT_HASH_METHOD:
        raise ValueError(f"Unsupported evidence hash method: {method!r}")
    if text_evidence_sha256(path) != digest:
        raise ValueError(f"Evidence hash mismatch: {path}")
