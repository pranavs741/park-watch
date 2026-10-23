#!/usr/bin/env python3
"""Run a small Ring webhook receiver and analyze motion snapshots."""

import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import os
from pathlib import Path
import sys
from uuid import uuid4

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from parkwatch.config import VisionConfig
from parkwatch.ring import RingApiClient, RingWebhookProcessor
from parkwatch.vision.annotate import draw_analysis
from parkwatch.vision.detector import YoloVehicleDetector
from parkwatch.vision.occupancy import classify_occupancy


def make_handler(config: VisionConfig, processor: RingWebhookProcessor, client: RingApiClient, output_dir: Path):
    detector = YoloVehicleDetector(config.model, config.vehicle_classes)

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            if self.path != "/webhooks/ring":
                self.send_error(404)
                return
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            try:
                event = processor.parse(body, self.headers.get("X-Signature", ""))
                if event is not None and event.event_type in {"motion_detected", "motion.vehicle", "motion.human"}:
                    image_path = output_dir / f"{event.request_id}-{uuid4().hex[:8]}.jpg"
                    client.download_snapshot(event.device_id, image_path, event.component_ids[0] if event.component_ids else None)
                    image = cv2.imread(str(image_path))
                    if image is None:
                        raise RuntimeError(f"Ring returned an unreadable image: {image_path}")
                    detections = detector.detect(image)
                    result = classify_occupancy(detections, config.parking_roi, config.min_vehicle_confidence, config.min_roi_overlap, config.ambiguous_overlap)
                    annotated = draw_analysis(image, config.parking_roi, result, config.min_vehicle_confidence)
                    if not cv2.imwrite(str(image_path), annotated):
                        raise RuntimeError(f"Could not write annotated image: {image_path}")
                    print(f"{event.request_id}: {result.status.value} ({image_path})", flush=True)
                self.send_response(200)
                self.end_headers()
            except (PermissionError, ValueError) as exc:
                self.send_error(401, str(exc))
            except Exception as exc:
                self.send_error(500, str(exc))

        def log_message(self, format, *args):
            return

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description="Receive Ring webhooks and analyze snapshots")
    parser.add_argument("--config", type=Path, default=Path("config/vision.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/ring"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    config = VisionConfig.from_file(args.config)
    config.validate()
    processor = RingWebhookProcessor(os.environ["RING_HMAC_KEY"])
    client = RingApiClient(os.environ["RING_ACCESS_TOKEN"], os.getenv("RING_API_URL", "https://api.amazonvision.com"))
    server = HTTPServer((args.host, args.port), make_handler(config, processor, client, args.output_dir))
    print(f"Listening on http://{args.host}:{args.port}/webhooks/ring", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
