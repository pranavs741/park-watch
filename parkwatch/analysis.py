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


def normalize_snapshot_width(image, width: int):
    """Return an image with the requested width, preserving its aspect ratio."""
    if image.shape[1] == width:
        return image
    target_height = round(image.shape[0] * width / image.shape[1])
    interpolation = cv2.INTER_AREA if width < image.shape[1] else cv2.INTER_CUBIC
    return cv2.resize(image, (width, target_height), interpolation=interpolation)


def analyze_snapshot(
    client: RingApiClient,
    detector: YoloVehicleDetector,
    config: VisionConfig,
    device_id: str,
    output_dir: Path,
) -> tuple[Path, list[tuple[ParkingSpotConfig, OccupancyResult]]]:
    """Download, analyze, annotate, and return results for one camera snapshot."""
    spots = config.spots_for_device(device_id)
    image_path = timestamped_image_path(output_dir, config.camera_name(device_id))
    client.download_snapshot(device_id, image_path, resolution=config.snapshot_resolution_for_device(device_id))
    image = cv2.imread(str(image_path))
    if image is None:
        raise RuntimeError(f"Ring returned an unreadable image: {image_path}")

    # Ring can return different native resolutions for different cameras or
    # requests. Normalize the working/saved image width while preserving its
    # aspect ratio. This makes output dimensions predictable; it does not add
    # detail to a low-resolution source image.
    if image.shape[1] != config.snapshot_width:
        image = normalize_snapshot_width(image, config.snapshot_width)
        if not cv2.imwrite(str(image_path), image):
            raise RuntimeError(f"Could not write normalized image: {image_path}")

    image_height, image_width = image.shape[:2]
    reference_width, reference_height = config.reference_image_size_for_device(device_id)
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
