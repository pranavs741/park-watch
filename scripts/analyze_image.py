#!/usr/bin/env python3
"""Analyze one image and write an annotated result."""

import argparse
from pathlib import Path
import sys

import cv2

# When run as `python scripts/analyze_image.py`, Python adds `scripts/` rather
# than the repository root to sys.path. Add the project root so the local
# `parkwatch` package can be imported without requiring `pip install -e .`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from parkwatch.config import VisionConfig
from parkwatch.vision.annotate import draw_analyses
from parkwatch.vision.detector import YoloVehicleDetector
from parkwatch.vision.occupancy import classify_occupancy


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify a ParkWatch parking ROI in an image")
    parser.add_argument("image", type=Path)
    parser.add_argument("--config", type=Path, default=Path("config/vision.json"))
    parser.add_argument("--output", type=Path, default=Path("outputs/annotated.jpg"))
    parser.add_argument("--device-id", help="Select a camera from a multi-camera config")
    args = parser.parse_args()

    config = VisionConfig.from_file(args.config)
    config.validate()
    image = cv2.imread(str(args.image))
    if image is None:
        raise SystemExit(f"Could not read image: {args.image}")
    detector = YoloVehicleDetector(
        config.model,
        config.vehicle_classes,
        config.inference_image_size,
        config.min_candidate_confidence,
    )
    detections = detector.detect(image)
    analyses = []
    for spot in config.spots_for_device(args.device_id):
        result = classify_occupancy(
            detections,
            spot.roi,
            spot.min_vehicle_confidence,
            spot.min_roi_overlap,
            spot.ambiguous_overlap,
            spot.overlap_basis,
        )
        analyses.append((spot, result))
    annotated = draw_analyses(image, analyses)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(args.output), annotated):
        raise SystemExit(f"Could not write output: {args.output}")

    for spot, result in analyses:
        print(f"{spot.name}: {result.status.value}")
        for item in result.assessments:
            if (
                item.detection.confidence < spot.min_vehicle_confidence
                and item.overlap_ratio < spot.ambiguous_overlap
            ):
                continue
            print(f"  Vehicle: {item.detection.class_name}")
            print(f"  YOLO confidence: {item.detection.confidence:.2f}")
            print(f"  ROI overlap ({spot.overlap_basis} basis): {item.overlap_ratio:.2f}")
    print(f"Annotated image: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
