"""Parking-region geometry and state classification."""

from dataclasses import dataclass
from enum import Enum
from shapely.geometry import Polygon, box

from .detector import Detection


class ParkingStatus(str, Enum):
    EMPTY = "EMPTY"
    OCCUPIED = "OCCUPIED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class DetectionAssessment:
    detection: Detection
    overlap_ratio: float
    occupies_roi: bool


@dataclass(frozen=True)
class OccupancyResult:
    status: ParkingStatus
    assessments: list[DetectionAssessment]

    @property
    def strongest(self) -> DetectionAssessment | None:
        return max(self.assessments, key=lambda item: item.overlap_ratio, default=None)


def roi_polygon(points: list[list[float]]) -> Polygon:
    polygon = Polygon(points)
    if not polygon.is_valid or polygon.area <= 0:
        raise ValueError("parking ROI must be a valid, non-empty polygon")
    return polygon


def overlap_ratio(detection: Detection, roi: Polygon, basis: str = "vehicle") -> float:
    vehicle = box(*detection.bbox)
    denominator = vehicle.area if basis == "vehicle" else roi.area
    if denominator == 0:
        return 0.0
    if basis not in {"vehicle", "roi"}:
        raise ValueError("overlap basis must be 'vehicle' or 'roi'")
    return float(vehicle.intersection(roi).area / denominator)


def classify_occupancy(
    detections: list[Detection],
    roi_points: list[list[float]],
    min_confidence: float = 0.60,
    min_roi_overlap: float = 0.50,
    ambiguous_overlap: float = 0.05,
    overlap_basis: str = "vehicle",
) -> OccupancyResult:
    roi = roi_polygon(roi_points)
    assessments = [
        DetectionAssessment(detection, overlap_ratio(detection, roi, overlap_basis), False)
        for detection in detections
    ]
    assessments = [
        DetectionAssessment(item.detection, item.overlap_ratio, item.overlap_ratio >= min_roi_overlap)
        for item in assessments
    ]
    if any(item.occupies_roi and item.detection.confidence >= min_confidence for item in assessments):
        return OccupancyResult(ParkingStatus.OCCUPIED, assessments)

    relevant = [item for item in assessments if item.detection.confidence >= min_confidence]
    low_confidence = [
        item for item in assessments
        if item.detection.confidence < min_confidence and item.overlap_ratio >= ambiguous_overlap
    ]
    partial = [item for item in relevant if ambiguous_overlap <= item.overlap_ratio < min_roi_overlap]
    if low_confidence or partial:
        return OccupancyResult(ParkingStatus.UNKNOWN, assessments)
    return OccupancyResult(ParkingStatus.EMPTY, assessments)

