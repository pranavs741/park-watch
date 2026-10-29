import json

import pytest

from parkwatch.config import VisionConfig


def test_legacy_single_roi_remains_supported(tmp_path):
    path = tmp_path / "vision.json"
    path.write_text(json.dumps({"parking_roi": [[0, 0], [10, 0], [10, 10]]}))

    config = VisionConfig.from_file(path)
    config.validate()

    assert config.spots_for_device("any-camera")[0].name == "Parking"


def test_camera_specific_spots_and_overrides(tmp_path):
    path = tmp_path / "vision.json"
    path.write_text(json.dumps({
        "min_vehicle_confidence": 0.6,
        "cameras": {
            "garage": {
                "parking_spots": [
                    {
                        "name": "Right edge",
                        "roi": [[0, 0], [10, 0], [10, 10]],
                        "overlap_basis": "roi",
                        "min_vehicle_confidence": 0.35
                    }
                ]
            }
        }
    }))

    config = VisionConfig.from_file(path)
    config.validate()
    spot = config.spots_for_device("garage")[0]

    assert spot.name == "Right edge"
    assert spot.overlap_basis == "roi"
    assert spot.min_vehicle_confidence == pytest.approx(0.35)
    with pytest.raises(ValueError, match="no parking spots configured"):
        config.spots_for_device("front-door")
