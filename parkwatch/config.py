"""Configuration for cameras and their parking spaces."""

from dataclasses import dataclass, field
import json
from pathlib import Path

from shapely.geometry import Polygon


@dataclass(frozen=True)
class ParkingSpotConfig:
    """One named parking space and the thresholds used to classify it."""

    name: str
    roi: list[list[float]]
    min_vehicle_confidence: float
    min_roi_overlap: float
    ambiguous_overlap: float
    overlap_basis: str = "vehicle"


@dataclass(frozen=True)
class VisionConfig:
    parking_roi: list[list[float]] = field(default_factory=list)
    model: str = "yolo11n.pt"
    reference_image_size: tuple[int, int] = (1920, 1080)
    inference_image_size: int = 640
    min_candidate_confidence: float = 0.10
    min_vehicle_confidence: float = 0.60
    min_roi_overlap: float = 0.50
    ambiguous_overlap: float = 0.05
    vehicle_classes: tuple[str, ...] = ("car", "truck", "bus", "motorcycle")
    parking_spots: tuple[ParkingSpotConfig, ...] = ()
    cameras: dict[str, tuple[ParkingSpotConfig, ...]] = field(default_factory=dict)
    camera_names: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_file(cls, path: str | Path) -> "VisionConfig":
        data = json.loads(Path(path).read_text())
        defaults = {
            "min_vehicle_confidence": float(data.get("min_vehicle_confidence", cls.min_vehicle_confidence)),
            "min_roi_overlap": float(data.get("min_roi_overlap", cls.min_roi_overlap)),
            "ambiguous_overlap": float(data.get("ambiguous_overlap", cls.ambiguous_overlap)),
        }

        def make_spot(item: dict, fallback_name: str) -> ParkingSpotConfig:
            return ParkingSpotConfig(
                name=str(item.get("name", fallback_name)),
                roi=item["roi"],
                min_vehicle_confidence=float(item.get("min_vehicle_confidence", defaults["min_vehicle_confidence"])),
                min_roi_overlap=float(item.get("min_roi_overlap", defaults["min_roi_overlap"])),
                ambiguous_overlap=float(item.get("ambiguous_overlap", defaults["ambiguous_overlap"])),
                overlap_basis=str(item.get("overlap_basis", "vehicle")),
            )

        parking_spots = tuple(
            make_spot(item, f"Spot {index}")
            for index, item in enumerate(data.get("parking_spots", []), start=1)
        )
        cameras = {
            str(device_id): tuple(
                make_spot(item, f"Spot {index}")
                for index, item in enumerate(camera.get("parking_spots", []), start=1)
            )
            for device_id, camera in data.get("cameras", {}).items()
        }
        camera_names = {
            str(device_id): str(camera.get("name", device_id))
            for device_id, camera in data.get("cameras", {}).items()
        }
        return cls(
            parking_roi=data.get("parking_roi", []),
            model=data.get("model", cls.model),
            reference_image_size=tuple(data.get("reference_image_size", cls.reference_image_size)),
            inference_image_size=int(data.get("inference_image_size", cls.inference_image_size)),
            min_candidate_confidence=float(data.get("min_candidate_confidence", cls.min_candidate_confidence)),
            min_vehicle_confidence=defaults["min_vehicle_confidence"],
            min_roi_overlap=defaults["min_roi_overlap"],
            ambiguous_overlap=defaults["ambiguous_overlap"],
            vehicle_classes=tuple(data.get("vehicle_classes", cls.vehicle_classes)),
            parking_spots=parking_spots,
            cameras=cameras,
            camera_names=camera_names,
        )

    def validate(self) -> None:
        if len(self.reference_image_size) != 2 or any(value <= 0 for value in self.reference_image_size):
            raise ValueError("reference_image_size must contain two positive values")
        if self.inference_image_size <= 0:
            raise ValueError("inference_image_size must be greater than zero")
        if not 0 <= self.min_candidate_confidence <= 1:
            raise ValueError("min_candidate_confidence must be between 0 and 1")
        if not 0 <= self.min_vehicle_confidence <= 1:
            raise ValueError("min_vehicle_confidence must be between 0 and 1")
        if not 0 <= self.min_roi_overlap <= 1:
            raise ValueError("min_roi_overlap must be between 0 and 1")
        if not 0 <= self.ambiguous_overlap <= self.min_roi_overlap:
            raise ValueError("ambiguous_overlap must be between 0 and min_roi_overlap")
        configured_spots = list(self.parking_spots)
        for spots in self.cameras.values():
            configured_spots.extend(spots)
        if not configured_spots and self.parking_roi:
            configured_spots.append(self._legacy_spot())
        if not configured_spots:
            raise ValueError("configure parking_roi, parking_spots, or cameras")
        for spot in configured_spots:
            self._validate_spot(spot)

    def spots_for_device(self, device_id: str | None = None) -> tuple[ParkingSpotConfig, ...]:
        """Return camera-specific spots, or a shared/legacy spot configuration."""
        if self.cameras:
            if not device_id or device_id not in self.cameras:
                raise ValueError(f"no parking spots configured for Ring device {device_id!r}")
            return self.cameras[device_id]
        if self.parking_spots:
            return self.parking_spots
        return (self._legacy_spot(),)

    def camera_name(self, device_id: str) -> str:
        """Return a human-friendly camera name for notifications."""
        return self.camera_names.get(device_id, device_id)

    def _legacy_spot(self) -> ParkingSpotConfig:
        return ParkingSpotConfig(
            name="Parking",
            roi=self.parking_roi,
            min_vehicle_confidence=self.min_vehicle_confidence,
            min_roi_overlap=self.min_roi_overlap,
            ambiguous_overlap=self.ambiguous_overlap,
        )

    @staticmethod
    def _validate_spot(spot: ParkingSpotConfig) -> None:
        if not spot.name.strip():
            raise ValueError("parking spot name cannot be empty")
        if len(spot.roi) < 3:
            raise ValueError(f"{spot.name}: ROI must contain at least three points")
        polygon = Polygon(spot.roi)
        if not polygon.is_valid or polygon.area <= 0:
            raise ValueError(f"{spot.name}: ROI must be a valid, non-empty polygon")
        if not 0 <= spot.min_vehicle_confidence <= 1:
            raise ValueError(f"{spot.name}: min_vehicle_confidence must be between 0 and 1")
        if not 0 <= spot.min_roi_overlap <= 1:
            raise ValueError(f"{spot.name}: min_roi_overlap must be between 0 and 1")
        if not 0 <= spot.ambiguous_overlap <= spot.min_roi_overlap:
            raise ValueError(f"{spot.name}: ambiguous_overlap must be between 0 and min_roi_overlap")
        if spot.overlap_basis not in {"vehicle", "roi"}:
            raise ValueError(f"{spot.name}: overlap_basis must be 'vehicle' or 'roi'")

