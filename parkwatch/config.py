"""Configuration for the vision milestone."""

from dataclasses import dataclass, field
import json
from pathlib import Path


@dataclass(frozen=True)
class VisionConfig:
    parking_roi: list[list[float]]
    model: str = "yolo11n.pt"
    min_vehicle_confidence: float = 0.60
    min_roi_overlap: float = 0.50
    ambiguous_overlap: float = 0.05
    vehicle_classes: tuple[str, ...] = ("car", "truck", "bus", "motorcycle")

    @classmethod
    def from_file(cls, path: str | Path) -> "VisionConfig":
        data = json.loads(Path(path).read_text())
        return cls(
            parking_roi=data["parking_roi"],
            model=data.get("model", cls.model),
            min_vehicle_confidence=float(data.get("min_vehicle_confidence", cls.min_vehicle_confidence)),
            min_roi_overlap=float(data.get("min_roi_overlap", cls.min_roi_overlap)),
            ambiguous_overlap=float(data.get("ambiguous_overlap", cls.ambiguous_overlap)),
            vehicle_classes=tuple(data.get("vehicle_classes", cls.vehicle_classes)),
        )

    def validate(self) -> None:
        if len(self.parking_roi) < 3:
            raise ValueError("parking_roi must contain at least three points")
        if not 0 <= self.min_vehicle_confidence <= 1:
            raise ValueError("min_vehicle_confidence must be between 0 and 1")
        if not 0 <= self.min_roi_overlap <= 1:
            raise ValueError("min_roi_overlap must be between 0 and 1")
        if not 0 <= self.ambiguous_overlap <= self.min_roi_overlap:
            raise ValueError("ambiguous_overlap must be between 0 and min_roi_overlap")

