#!/usr/bin/env python3
"""Poll Ring camera snapshots on a fixed interval and analyze them."""

import argparse
import os
from pathlib import Path
import sys
import time
from uuid import uuid4

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from parkwatch.config import VisionConfig
from parkwatch.ring import RingApiClient, RingOAuthClient, RingTokenStore
from parkwatch.vision.annotate import draw_analysis
from parkwatch.vision.detector import YoloVehicleDetector
from parkwatch.vision.occupancy import classify_occupancy


def device_id_from_item(item: dict) -> str | None:
    """Handle common JSON:API and flat device-list shapes."""
    return str(item.get("id")) if item.get("id") else item.get("device_id")


def analyze_snapshot(client: RingApiClient, detector: YoloVehicleDetector, config: VisionConfig, device_id: str, output_dir: Path) -> None:
    image_path = output_dir / f"{device_id}-{uuid4().hex[:8]}.jpg"
    client.download_snapshot(device_id, image_path)
    image = cv2.imread(str(image_path))
    if image is None:
        raise RuntimeError(f"Ring returned an unreadable image: {image_path}")
    detections = detector.detect(image)
    result = classify_occupancy(detections, config.parking_roi, config.min_vehicle_confidence, config.min_roi_overlap, config.ambiguous_overlap)
    annotated = draw_analysis(image, config.parking_roi, result, config.min_vehicle_confidence)
    if not cv2.imwrite(str(image_path), annotated):
        raise RuntimeError(f"Could not write annotated image: {image_path}")
    print(f"{device_id}: {result.status.value} ({image_path})", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Poll Ring snapshots and analyze parking occupancy")
    parser.add_argument("--config", type=Path, default=Path("config/vision.json"))
    parser.add_argument("--device-id", action="append", help="Ring device ID; repeat for multiple cameras")
    parser.add_argument("--interval", type=float, default=60.0, help="Seconds between polls (default: 60)")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/ring"))
    parser.add_argument("--token-file", type=Path, default=Path("outputs/ring/tokens.json"))
    parser.add_argument("--list-devices", action="store_true", help="List accessible Ring devices and exit")
    args = parser.parse_args()
    if args.interval <= 0:
        parser.error("--interval must be greater than zero")

    token = os.getenv("RING_ACCESS_TOKEN")
    if not token and os.path.exists(args.token_file):
        if not os.getenv("RING_CLIENT_ID") or not os.getenv("RING_CLIENT_SECRET"):
            parser.error("RING_CLIENT_ID and RING_CLIENT_SECRET are required to refresh the saved Ring token")
        oauth = RingOAuthClient(os.getenv("RING_CLIENT_ID", ""), os.getenv("RING_CLIENT_SECRET", ""))
        token = RingTokenStore(args.token_file).access_token(oauth)
    if not token:
        parser.error("RING_ACCESS_TOKEN is missing and no usable token file was found; complete OAuth account linking first")
    client = RingApiClient(token, os.getenv("RING_API_URL", "https://api.amazonvision.com"))

    if args.list_devices:
        print(client.list_devices())
        return 0
    if not args.device_id:
        parser.error("provide --device-id, or use --list-devices first")

    config = VisionConfig.from_file(args.config)
    config.validate()
    detector = YoloVehicleDetector(config.model, config.vehicle_classes)
    print(f"Polling {len(args.device_id)} Ring device(s) every {args.interval:g} seconds", flush=True)
    try:
        while True:
            for device_id in args.device_id:
                try:
                    analyze_snapshot(client, detector, config, device_id, args.output_dir)
                except Exception as exc:
                    print(f"{device_id}: poll failed: {exc}", file=sys.stderr, flush=True)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("Polling stopped", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
