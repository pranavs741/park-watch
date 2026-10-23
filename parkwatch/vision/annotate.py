"""Annotated image rendering."""

import cv2
import numpy as np

from .occupancy import OccupancyResult, ParkingStatus


def draw_analysis(image, roi_points, result: OccupancyResult, min_confidence: float = 0.0):
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
        if assessment.detection.confidence < min_confidence:
            continue
        x1, y1, x2, y2 = map(int, assessment.detection.bbox)
        occupies = assessment.occupies_roi and assessment.detection.confidence >= min_confidence
        cv2.rectangle(output, (x1, y1), (x2, y2), color if occupies else (255, 150, 0), 2)
        label = f"{assessment.detection.class_name} {assessment.detection.confidence:.2f} overlap {assessment.overlap_ratio:.2f}"
        cv2.putText(output, label, (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
        cv2.putText(output, label, (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (20, 20, 20), 1)
    cv2.rectangle(output, (10, 10), (350, 55), color, -1)
    cv2.putText(output, f"Parking: {result.status.value}", (20, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
    return output
