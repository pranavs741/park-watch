"""Run the configured parking-space analysis for a Ring snapshot."""

from pathlib import Path
from dataclasses import replace

import cv2

from .config import ParkingSpotConfig, VisionConfig
from .output import timestamped_image_path
from .ring import RingApiClient
from .vision.annotate import draw_analyses
from .vision.detector import YoloVehicleDetector
from .vision.occupancy import OccupancyResult, classify_occupancy


def analyze_snapshot(
    client: RingApiClient,
    detector: YoloVehicleDetector,
    config: VisionConfig,
    device_id: str,
    output_dir: Path,
) -> tuple[Path, list[tuple[ParkingSpotConfig, OccupancyResult]]]:
    """Download, analyze, annotate, and return results for one camera snapshot."""
    spots = config.spots_for_device(device_id)
    image_path = timestamped_image_path(output_dir, [spot.name for spot in spots])
    client.download_snapshot(device_id, image_path)
    image = cv2.imread(str(image_path))
    if image is None:
        raise RuntimeError(f"Ring returned an unreadable image: {image_path}")

    image_height, image_width = image.shape[:2]
    reference_width, reference_height = config.reference_image_size
    scale_x = image_width / reference_width
    scale_y = image_height / reference_height
    detections = detector.detect(image)
    analyses = []
    for spot in spots:
        scaled_spot = replace(
            spot,
            roi=[[x * scale_x, y * scale_y] for x, y in spot.roi],
        )
        result = classify_occupancy(
            detections,
            scaled_spot.roi,
            scaled_spot.min_vehicle_confidence,
            scaled_spot.min_roi_overlap,
            scaled_spot.ambiguous_overlap,
            scaled_spot.overlap_basis,
        )
        analyses.append((scaled_spot, result))

    annotated = draw_analyses(image, analyses)
    if not cv2.imwrite(str(image_path), annotated):
        raise RuntimeError(f"Could not write annotated image: {image_path}")
    return image_path, analyses
