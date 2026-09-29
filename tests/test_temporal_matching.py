import pytest

from ghostnet.temporal_matching import TemporalCandidate, associate


def candidate(name, lon, area=10, spectrum=(1., 2., 3., 4.)):
    return TemporalCandidate(name, lon, 0, area, spectrum)


def match(later, **kwargs):
    return associate(candidate("source", 0), later, predicted_lon=1,
                     predicted_lat=0, uncertainty_km=0, fully_observed=False, **kwargs)


def test_prediction_replaces_original_position_as_search_centre():
    result = match([candidate("old-position", 0), candidate("advected", 1)])
    assert result["candidate_id"] == "advected"


def test_spectral_and_size_features_rank_nearby_candidates():
    result = match([candidate("wrong-size", 1, area=100), candidate("consistent", 1.01)])
    assert result["candidate_id"] == "consistent"
    result = match([candidate("wrong-spectrum", 1, spectrum=(4., 3., 2., 1.)),
                    candidate("consistent", 1.001)])
    assert result["candidate_id"] == "consistent"


def test_unobserved_search_area_is_inconclusive_not_negative():
    assert match([])["status"] == "inconclusive"
    result = associate(candidate("source", 0), [], predicted_lon=1, predicted_lat=0,
                       uncertainty_km=0, fully_observed=True)
    assert result["status"] == "not_reobserved"


def test_missing_features_do_not_become_negative_evidence():
    result = associate(candidate("source", 0), [candidate("missing", 1, spectrum=())],
                       predicted_lon=1, predicted_lat=0, uncertainty_km=0, fully_observed=True)
    assert result["status"] == "inconclusive"


def test_uncertainty_expands_search_and_ties_are_stable():
    later = [candidate("b", 1.1), candidate("a", 1.1)]
    assert match(later)["status"] == "inconclusive"
    result = associate(candidate("source", 0), later, predicted_lon=1, predicted_lat=0,
                       uncertainty_km=10, fully_observed=False)
    assert result["candidate_id"] == "a"
    with pytest.raises(ValueError):
        match([], base_tolerance_km=-1)
