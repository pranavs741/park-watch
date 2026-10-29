from datetime import datetime, timezone

from parkwatch.output import filename_slug, timestamped_image_path


def test_filename_slug_is_safe_and_readable():
    assert filename_slug("Right curb (partial view)") == "right-curb-partial-view"


def test_timestamped_image_path_contains_all_spots_and_utc_time(tmp_path):
    timestamp = datetime(2026, 10, 27, 17, 4, 5, 123456, tzinfo=timezone.utc)

    path = timestamped_image_path(tmp_path, ["Left Spot", "Right Spot"], timestamp)

    assert path == tmp_path / "left-spot--right-spot__2026-10-27T17-04-05.123456Z.jpg"
