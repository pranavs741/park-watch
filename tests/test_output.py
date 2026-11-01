from datetime import datetime, timezone
import os
import time

from parkwatch.output import filename_slug, remove_old_images, timestamped_image_path


def test_filename_slug_is_safe_and_readable():
    assert filename_slug("Right curb (partial view)") == "right-curb-partial-view"


def test_timestamped_image_path_uses_camera_name_and_pacific_time(tmp_path):
    timestamp = datetime(2026, 10, 27, 17, 4, 5, 123456, tzinfo=timezone.utc)

    path = timestamped_image_path(tmp_path, "Front Garage", timestamp)

    assert path == tmp_path / "front-garage_2026-10-27_10-04-05.jpg"


def test_remove_old_images_does_not_remove_tokens(tmp_path):
    old_image = tmp_path / "old.jpg"
    recent_image = tmp_path / "recent.jpg"
    tokens = tmp_path / "tokens.json"
    for path in (old_image, recent_image, tokens):
        path.write_text("data")

    old_image.touch()
    old_image_age = 3 * 24 * 60 * 60
    os.utime(old_image, (time.time() - old_image_age, time.time() - old_image_age))

    assert remove_old_images(tmp_path, retention_days=2) == 1
    assert not old_image.exists()
    assert recent_image.exists()
    assert tokens.exists()
