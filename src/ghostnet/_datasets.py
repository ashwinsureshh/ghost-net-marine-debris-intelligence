"""Dataset key -> directory, mirroring ``scripts/fetch_data.py``.

Kept as a tiny module rather than importing ``scripts.fetch_data`` so that
``ghostnet`` has no dependency on the scripts/ directory being importable.
If a dataset is added there, add it here too — the keys must stay in step, and
``tests/test_config.py`` asserts they do.
"""

from __future__ import annotations

DATASET_DIRS: dict[str, str] = {
    "sentinel2": "raw/sentinel2",
    "marida": "marida",
    "oscar": "oscar",
    "drifters": "drifters",
    "rivers": "rivers",
    "gfw": "gfw",
    "mpa": "protected_planet",
}
