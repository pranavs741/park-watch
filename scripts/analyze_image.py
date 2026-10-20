#!/usr/bin/env python3
"""Analyze one image and write an annotated result."""

import argparse
from pathlib import Path
import cv2

from parkwatch.config import VisionConfig
from parkwatch.vision.annotate import draw_analysis
from parkwatch.vision.detector import YoloVehicleDetector
from parkwatch.vision.occupancy import classify_occupancy


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify a ParkWatch parking ROI in an image")
    parser.add_argument("image", type=Path)
    parser.add_argument("--config", type=Path, default=Path("config/vision.json"))
    parser.add_argument("--output", type=Path, default=Path("outputs/annotated.jpg"))
    args = parser.parse_args()

    config = VisionConfig.from_file(args.config)
    config.validate()
    image = cv2.imread(str(args.image))
    if image is None:
        raise SystemExit(f"Could not read image: {args.image}")
    detector = YoloVehicleDetector(config.model, config.vehicle_classes)
    detections = detector.detect(image, confidence=0.0)
    result = classify_occupancy(detections, config.parking_roi, config.min_vehicle_confidence, config.min_roi_overlap, config.ambiguous_overlap)
    annotated = draw_analysis(image, config.parking_roi, result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(args.output), annotated):
        raise SystemExit(f"Could not write output: {args.output}")

    print(f"Parking: {result.status.value}")
    for item in result.assessments:
        print(f"Vehicle: {item.detection.class_name}")
        print(f"YOLO confidence: {item.detection.confidence:.2f}")
        print(f"ROI overlap: {item.overlap_ratio:.2f}")
    print(f"Annotated image: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

