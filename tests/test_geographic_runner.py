import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from run_geographic_validation import validate_report  # noqa: E402


@pytest.fixture
def completed(tmp_path):
    checkpoint = tmp_path / "weights.pt"
    checkpoint.write_bytes(b"test checkpoint identity")
    report = tmp_path / "report.json"
    data = {
        "checkpoint_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
        "training_protocol": {
            "seed": 20260825, "epochs": 60, "holdout_tiles": ["16PDC"],
            "training_prior": {"mode": "train-split", "training_ids_sha256": "retained"},
            "normalisation": {"mean": [1], "std": [2]},
            "hyperparameters": {"batch_size": 8, "lr": 3e-4, "width": 32},
        },
    }
    report.write_text(json.dumps(data))
    return report, checkpoint, data


def test_completed_result_can_be_reused(completed):
    report, checkpoint, data = completed
    assert validate_report(report, checkpoint, "16PDC", 20260825, "retained",
                           {"mean": [1], "std": [2]}) == data


def test_changed_checkpoint_cannot_be_reused(completed):
    report, checkpoint, _ = completed
    checkpoint.write_bytes(b"different checkpoint")
    with pytest.raises(ValueError, match="provenance"):
        validate_report(report, checkpoint, "16PDC", 20260825, "retained",
                        {"mean": [1], "std": [2]})


def test_different_training_population_cannot_be_reused(completed):
    report, checkpoint, _ = completed
    with pytest.raises(ValueError, match="provenance"):
        validate_report(report, checkpoint, "16PDC", 20260825, "different",
                        {"mean": [1], "std": [2]})


def test_different_normalisation_cannot_be_reused(completed):
    report, checkpoint, _ = completed
    with pytest.raises(ValueError, match="provenance"):
        validate_report(report, checkpoint, "16PDC", 20260825, "retained", {})
