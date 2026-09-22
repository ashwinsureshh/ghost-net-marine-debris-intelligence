import hashlib
import sys
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("torch")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import train_cnn  # noqa: E402
from ghostnet.agents.detection_cnn import normalise  # noqa: E402


def test_fit_reads_only_supplied_training_images(monkeypatch):
    seen = []

    class Image:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return np.tile([1., 3., np.nan], (11, 1)).reshape(11, 1, 3)

    def open_image(path):
        seen.append(path)
        return Image()

    monkeypatch.setattr(train_cnn, "_paths_for", lambda pid: (pid, "unused-mask"))
    monkeypatch.setattr(train_cnn.rasterio, "open", open_image)
    stats = train_cnn.fit_normalisation(["retained"])
    assert seen == ["retained"]
    assert stats["mean"] == [2.] * 11
    assert stats["std"] == [1.] * 11
    assert stats["finite_pixels"] == [2] * 11
    assert stats["training_ids_sha256"] == hashlib.sha256(b"retained").hexdigest()


def test_custom_normalisation_is_used():
    assert np.allclose(normalise(np.full((11, 2, 2), 5),
                                {"mean": [3] * 11, "std": [2] * 11}), 1)


@pytest.mark.parametrize("std", [[0] * 11, [float("nan")] * 11, [1]])
def test_invalid_custom_normalisation_rejected(std):
    with pytest.raises(ValueError, match="normalisation"):
        normalise(np.ones((11, 2, 2)), {"mean": [0] * 11, "std": std})


def test_inference_uses_checkpoint_statistics(monkeypatch):
    from ghostnet.agents import detection_cnn

    stats = {"mean": [3] * 11, "std": [2] * 11}
    detector = detection_cnn.LoadedDetector(None, {"normalisation": stats}, "cpu")

    class Observed(Exception):
        pass

    def spy(stack, statistics):
        assert statistics == stats
        raise Observed

    monkeypatch.setattr(detection_cnn, "normalise", spy)
    with pytest.raises(Observed):
        detection_cnn.predict_debris_probability(np.ones((11, 256, 256)), detector)
