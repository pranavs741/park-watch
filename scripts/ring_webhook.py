#!/usr/bin/env python3
"""Run a small Ring webhook receiver and analyze motion snapshots."""

import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import os
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from parkwatch.config import VisionConfig
from parkwatch.ring import RingApiClient, RingOAuthClient, RingTokenStore, RingWebhookProcessor, verify_account_link_nonce
from parkwatch.vision.annotate import draw_analysis
from parkwatch.vision.detector import YoloVehicleDetector
from parkwatch.vision.occupancy import classify_occupancy


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Missing {name}. Load app-credentials.env first with: set -a; source app-credentials.env; set +a")
    return value


def make_handler(config: VisionConfig, processor: RingWebhookProcessor, oauth: RingOAuthClient, client: RingApiClient, token_store: RingTokenStore, output_dir: Path):
    detector = YoloVehicleDetector(config.model, config.vehicle_classes)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path == "/health":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status":"ok"}')
                return
            if urlsplit(self.path).path == "/ring/home":
                self.handle_home()
                return
            if urlsplit(self.path).path == "/ring/link":
                self.handle_link()
                return
            self.send_error(404)

        def handle_home(self):
            token_data = token_store.load() or {}
            status = token_data.get("status", "not linked")
            account_id = token_data.get("account_id", "not available")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"<h1>ParkWatch Ring connection</h1><p>Status: {status}</p><p>Ring account: {account_id}</p>".encode())

        def handle_link(self):
            query = parse_qs(urlsplit(self.path).query)
            nonce = query.get("nonce", [""])[0]
            timestamp = query.get("time", [""])[0]
            token_data = token_store.load() or {}
            account_id = token_data.get("account_id")
            if not nonce or not timestamp or not account_id:
                self.send_error(400, "Ring link requires nonce, time, and a token received from Ring")
                return
            if not verify_account_link_nonce(nonce, timestamp, account_id, processor.hmac_key):
                self.send_error(403, "invalid or expired Ring account-link nonce")
                return
            client.complete_account_link(nonce, "parkwatch-local")
            token_data["status"] = "completed"
            token_data["account_identifier"] = "parkwatch-local"
            token_store.save(token_data)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h1>ParkWatch Ring account linked</h1><p>You can close this page.</p>")

        def do_POST(self):  # noqa: N802
            if self.path == "/oauth/token":
                self.handle_token_exchange()
                return
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

        def handle_token_exchange(self):
            """Receive Ring's authorization code and exchange it server-to-server."""
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            try:
                form = parse_qs(body.decode("utf-8"))
                code = form.get("code", [""])[0]
                client_id = form.get("client_id", [""])[0]
                if client_id and client_id != oauth.client_id:
                    raise PermissionError("authorization code was sent for a different Ring app")
                token_data = oauth.exchange_authorization_code(code)
                client.access_token = token_data["access_token"]
                profile = client.user_profile()
                profile_data = profile.get("data", {})
                token_data["account_id"] = profile_data.get("id") or profile.get("account_id")
                token_data["status"] = "unclaimed"
                token_store.save(token_data)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status":"token_received"}')
                print("Ring access token received and loaded in memory", flush=True)
            except (PermissionError, ValueError) as exc:
                self.send_error(400, str(exc))
            except Exception as exc:
                print(f"Ring OAuth error: {exc}", flush=True)
                self.send_error(502, str(exc))

        def log_message(self, format, *args):
            return

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description="Receive Ring webhooks and analyze snapshots")
    parser.add_argument("--config", type=Path, default=Path("config/vision.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/ring"))
    parser.add_argument("--token-file", type=Path, default=Path("outputs/ring/tokens.json"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    config = VisionConfig.from_file(args.config)
    config.validate()
    processor = RingWebhookProcessor(required_env("RING_HMAC_KEY"))
    oauth = RingOAuthClient(required_env("RING_CLIENT_ID"), required_env("RING_CLIENT_SECRET"))
    token_store = RingTokenStore(args.token_file)
    access_token = os.getenv("RING_ACCESS_TOKEN") or token_store.access_token(oauth)
    client = RingApiClient(access_token, os.getenv("RING_API_URL", "https://api.amazonvision.com"))
    server = HTTPServer((args.host, args.port), make_handler(config, processor, oauth, client, token_store, args.output_dir))
    print(f"Listening on http://{args.host}:{args.port}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
