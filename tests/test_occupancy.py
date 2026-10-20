import pytest

from parkwatch.vision.detector import Detection
from parkwatch.vision.occupancy import ParkingStatus, classify_occupancy, overlap_ratio, roi_polygon


ROI = [[0, 0], [100, 0], [100, 100], [0, 100]]


def test_full_vehicle_inside_roi_is_occupied():
    result = classify_occupancy([Detection("car", 0.94, (10, 10, 90, 90))], ROI)
    assert result.status is ParkingStatus.OCCUPIED
    assert result.strongest.overlap_ratio == pytest.approx(1.0)


def test_vehicle_outside_roi_is_empty():
    result = classify_occupancy([Detection("car", 0.94, (120, 10, 180, 90))], ROI)
    assert result.status is ParkingStatus.EMPTY
    assert result.strongest.overlap_ratio == pytest.approx(0.0)


def test_partial_vehicle_can_be_unknown():
    result = classify_occupancy([Detection("car", 0.94, (80, 10, 180, 90))], ROI)
    assert result.status is ParkingStatus.UNKNOWN


def test_low_confidence_detection_is_unknown():
    result = classify_occupancy([Detection("car", 0.30, (10, 10, 90, 90))], ROI)
    assert result.status is ParkingStatus.UNKNOWN


def test_empty_detection_list_is_empty():
    assert classify_occupancy([], ROI).status is ParkingStatus.EMPTY


def test_invalid_roi_is_rejected():
    with pytest.raises(ValueError):
        roi_polygon([[0, 0], [1, 1]])

