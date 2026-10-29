"""YOLO vehicle detection adapter."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Detection:
    class_name: str
    confidence: float
    bbox: tuple[float, float, float, float]


class YoloVehicleDetector:
    """Thin adapter around Ultralytics, kept separate from occupancy logic."""

    def __init__(
        self,
        model_name: str,
        vehicle_classes: tuple[str, ...],
        image_size: int = 640,
        candidate_confidence: float = 0.10,
    ):
        try:
            from ultralytics import YOLO
        except ImportError as exc:  # pragma: no cover - depends on optional runtime dependency
            raise RuntimeError("Install requirements.txt before running image analysis") from exc
        self.model = YOLO(model_name)
        self.vehicle_classes = set(vehicle_classes)
        self.image_size = image_size
        self.candidate_confidence = candidate_confidence

    def detect(self, image: Any, confidence: float | None = None) -> list[Detection]:
        threshold = self.candidate_confidence if confidence is None else confidence
        results = self.model.predict(
            source=image,
            conf=threshold,
            imgsz=self.image_size,
            verbose=False,
        )
        detections: list[Detection] = []
        for result in results:
            names = result.names
            boxes = result.boxes
            for xyxy, score, class_id in zip(boxes.xyxy.tolist(), boxes.conf.tolist(), boxes.cls.tolist()):
                class_name = str(names[int(class_id)])
                if class_name in self.vehicle_classes:
                    detections.append(Detection(class_name, float(score), tuple(map(float, xyxy))))
        return detections

