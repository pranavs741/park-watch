"""Run the configured parking-space analysis for a Ring snapshot."""

from pathlib import Path

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

    detections = detector.detect(image)
    analyses = []
    for spot in spots:
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
    if not cv2.imwrite(str(image_path), annotated):
        raise RuntimeError(f"Could not write annotated image: {image_path}")
    return image_path, analyses
