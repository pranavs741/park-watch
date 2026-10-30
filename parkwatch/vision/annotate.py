"""Annotated image rendering."""

import cv2
import numpy as np

from .occupancy import OccupancyResult, ParkingStatus


def draw_analysis(
    image,
    roi_points,
    result: OccupancyResult,
    min_confidence: float = 0.0,
    spot_name: str = "Parking",
    header_row: int = 0,
    min_overlap_to_draw: float = 0.0,
):
    output = image.copy()
    polygon = np.array(roi_points, dtype=np.int32)
    color = {ParkingStatus.OCCUPIED: (0, 0, 255), ParkingStatus.EMPTY: (0, 180, 0), ParkingStatus.UNKNOWN: (0, 180, 255)}[result.status]
    overlay = output.copy()
    cv2.fillPoly(overlay, [polygon], color)
    output = cv2.addWeighted(overlay, 0.18, output, 0.82, 0)
    cv2.polylines(output, [polygon], True, color, 3)
    for assessment in result.assessments:
        # The classifier may retain low-confidence detections to produce
        # UNKNOWN, but those candidates are too noisy to draw prominently.
        if (
            assessment.detection.confidence < min_confidence
            or assessment.overlap_ratio < min_overlap_to_draw
        ):
            continue
        x1, y1, x2, y2 = map(int, assessment.detection.bbox)
        occupies = assessment.occupies_roi and assessment.detection.confidence >= min_confidence
        cv2.rectangle(output, (x1, y1), (x2, y2), color if occupies else (255, 150, 0), 2)
        label = f"{assessment.detection.class_name} {assessment.detection.confidence:.2f} overlap {assessment.overlap_ratio:.2f}"
        detection_font = max(0.35, min(0.55, output.shape[1] / 1920 * 0.55))
        detection_thickness = max(1, round(detection_font * 2))
        cv2.putText(output, label, (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, detection_font, (255, 255, 255), detection_thickness)
        cv2.putText(output, label, (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, detection_font, (20, 20, 20), 1)
    label_font = max(0.45, min(0.8, output.shape[1] / 1920 * 0.8))
    label_thickness = max(1, round(label_font * 2))
    (text_width, text_height), baseline = cv2.getTextSize(
        f"{spot_name}: {result.status.value}", cv2.FONT_HERSHEY_SIMPLEX, label_font, label_thickness
    )
    row_height = text_height + baseline + 14
    top = 10 + header_row * row_height
    label = f"{spot_name}: {result.status.value}"
    width = min(output.shape[1] - 10, 20 + text_width)
    cv2.rectangle(output, (10, top), (width, top + row_height), color, -1)
    cv2.putText(output, label, (20, top + text_height + 5), cv2.FONT_HERSHEY_SIMPLEX, label_font, (255, 255, 255), label_thickness)
    return output


def draw_analyses(image, analyses):
    """Draw several named parking-space results on the same camera image."""
    output = image.copy()
    for row, (spot, result) in enumerate(analyses):
        output = draw_analysis(
            output,
            spot.roi,
            result,
            spot.min_vehicle_confidence,
            spot.name,
            row,
            spot.ambiguous_overlap,
        )
    return output
