#!/usr/bin/env python3
"""Poll Ring camera snapshots on a fixed interval and analyze them."""

import argparse
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from parkwatch.analysis import analyze_snapshot as run_analysis
from parkwatch.config import VisionConfig
from parkwatch.notifications import DiscordWebhookNotifier, SpotStateTracker
from parkwatch.output import timestamped_image_path
from parkwatch.ring import RingApiClient, RingOAuthClient, RingTokenStore
from parkwatch.vision.detector import YoloVehicleDetector


def device_id_from_item(item: dict) -> str | None:
    """Handle common JSON:API and flat device-list shapes."""
    return str(item.get("id")) if item.get("id") else item.get("device_id")


def analyze_snapshot(client: RingApiClient, detector: YoloVehicleDetector, config: VisionConfig, device_id: str, output_dir: Path) -> None:
    image_path, analyses = run_analysis(client, detector, config, device_id, output_dir)
    statuses = ", ".join(f"{spot.name}={result.status.value}" for spot, result in analyses)
    print(f"{device_id}: {statuses} ({image_path})", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Poll Ring snapshots and analyze parking occupancy")
    parser.add_argument("--config", type=Path, default=Path("config/vision.json"))
    parser.add_argument("--device-id", action="append", help="Ring device ID; repeat for multiple cameras")
    parser.add_argument("--interval", type=float, default=60.0, help="Seconds between polls (default: 60)")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/ring"))
    parser.add_argument("--token-file", type=Path, default=Path("outputs/ring/tokens.json"))
    parser.add_argument("--list-devices", action="store_true", help="List accessible Ring devices and exit")
    parser.add_argument("--once", action="store_true", help="Poll each camera once, then exit")
    parser.add_argument(
        "--discord-webhook-url",
        default=os.getenv("DISCORD_WEBHOOK_URL"),
        help="Discord incoming webhook URL (or set DISCORD_WEBHOOK_URL)",
    )
    parser.add_argument(
        "--empty-confirmations",
        type=int,
        default=2,
        help="Consecutive EMPTY readings required before notifying (default: 2)",
    )
    parser.add_argument(
        "--notification-cooldown",
        type=float,
        default=900.0,
        help="Seconds before repeating an alert for the same spot (default: 900)",
    )
    parser.add_argument(
        "--download-only",
        action="store_true",
        help="Download one unannotated snapshot per camera for ROI setup, then exit",
    )
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

    if args.download_only:
        for device_id in args.device_id:
            image_path = timestamped_image_path(args.output_dir, ["calibration", device_id[-8:]])
            client.download_snapshot(device_id, image_path)
            print(f"{device_id}: downloaded {image_path}", flush=True)
        return 0

    config = VisionConfig.from_file(args.config)
    config.validate()
    for device_id in args.device_id:
        config.spots_for_device(device_id)
    detector = YoloVehicleDetector(
        config.model,
        config.vehicle_classes,
        config.inference_image_size,
        config.min_candidate_confidence,
    )
    notifier = DiscordWebhookNotifier(args.discord_webhook_url) if args.discord_webhook_url else None
    tracker = SpotStateTracker(args.empty_confirmations, args.notification_cooldown)
    print(f"Polling {len(args.device_id)} Ring device(s) every {args.interval:g} seconds", flush=True)
    try:
        while True:
            for device_id in args.device_id:
                try:
                    image_path, analyses = run_analysis(client, detector, config, device_id, args.output_dir)
                    statuses = ", ".join(f"{spot.name}={result.status.value}" for spot, result in analyses)
                    print(f"{device_id}: {statuses} ({image_path})", flush=True)
                    if notifier:
                        for spot, result in analyses:
                            key = f"{device_id}:{spot.name}"
                            if tracker.should_notify(key, result.status):
                                notifier.send_spot_opened(spot.name, device_id)
                                print(f"{device_id}: Discord notification sent for {spot.name}", flush=True)
                except Exception as exc:
                    print(f"{device_id}: poll failed: {exc}", file=sys.stderr, flush=True)
            if args.once:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("Polling stopped", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
