import numpy as np
import pytest

from ghostnet.training_weights import weights_from_counts


def test_unlabelled_counts_cannot_change_class_weights():
    assert weights_from_counts([0, 4, 16]) == weights_from_counts([999999, 4, 16])
    weights = weights_from_counts([0, 4, 16])
    assert weights[0] / weights[1] == pytest.approx(2)
    assert np.mean(weights) == pytest.approx(1)


@pytest.mark.parametrize("counts", [[0, 0, 1], [0, -1, 3], [0, float('nan'), 1]])
def test_invalid_or_debris_free_training_is_rejected(counts):
    with pytest.raises(ValueError):
        weights_from_counts(counts)


def test_only_filtered_training_masks_reach_prior(monkeypatch):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
    import train_cnn

    ids = ['1-1-20_16PDC_0', '1-1-20_16PCC_0']
    retained = train_cnn.filter_by_tile(ids, exclude=frozenset({'16PDC'}))
    seen = []

    def counts(selected):
        seen.extend(selected)
        return np.array([100, 2, 8])

    monkeypatch.setattr(train_cnn, 'label_counts', counts)
    prior = train_cnn.training_prior(retained, 'train-split')
    assert seen == ['1-1-20_16PCC_0']
    assert prior['counts'] == [100, 2, 8]
