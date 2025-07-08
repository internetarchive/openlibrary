from scripts.solr_updater.trending_updater_hourly import compute_trending_z_score


def test_compute_trending_z_score_zero_for_low_past() -> None:
    past = [0, 0, 0, 3, 0, 0, 0]
    current = 500
    z = compute_trending_z_score(current, past)
    assert z == 0.0
