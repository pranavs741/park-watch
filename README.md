# ParkWatch

ParkWatch is a Python parking-space monitor that combines Ring camera snapshots, Ultralytics YOLO vehicle detection, configurable polygon regions of interest (ROIs), and optional Discord notifications.

It supports two Ring ingestion modes:

- **Polling:** downloads snapshots from one or more cameras, analyzes them, saves annotated images, and optionally sends Discord alerts.
- **Webhooks:** validates signed Ring motion events, downloads the associated snapshot, and analyzes and annotates it.

## How it works

1. ParkWatch downloads a Ring snapshot.
2. YOLO detects configured vehicle classes.
3. Detections are compared with configured parking-space polygons.
4. Each spot is classified as `OCCUPIED`, `EMPTY`, or `UNKNOWN`.
5. The image is saved with the ROI and detections drawn on it.
6. In polling mode, an optional Discord notifier alerts after a confirmed occupied-to-empty transition.

The classifier is deliberately conservative. A low-confidence detection or partial/ambiguous overlap produces `UNKNOWN`, not `EMPTY`. `UNKNOWN` never triggers an open-space notification.

## Requirements

- Python 3.11+
- A Ring Partner API application and access to the Ring Partner API
- Optional: a Discord incoming webhook
- Optional: Docker and Docker Compose

## Local setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config/vision.example.json config/vision.json
```

## Analyze a local image

Use this to test the vision pipeline without contacting Ring:

```bash
python scripts/analyze_image.py path/to/image.jpg \
  --config config/vision.json \
  --output outputs/annotated.jpg
```

For a multi-camera configuration, pass `--device-id`:

```bash
python scripts/analyze_image.py path/to/image.jpg \
  --config config/vision.json \
  --device-id YOUR_RING_DEVICE_ID \
  --output outputs/annotated.jpg
```

## Vision configuration and ROI calibration

`config/vision.example.json` demonstrates the single-ROI format. For multiple cameras or spots, use a `cameras` object. Each camera may define named `parking_spots` and override thresholds.

Important settings include:

- `model`: YOLO model path or model name.
- `reference_image_size`: width and height used when ROI coordinates were measured.
- `inference_image_size`: YOLO's internal image size; larger values can help with distant vehicles but require more processing.
- `min_candidate_confidence`: lower confidence floor for retained candidate detections.
- `min_vehicle_confidence`: confidence required to establish occupancy.
- `min_roi_overlap`: overlap required to classify a spot as occupied.
- `ambiguous_overlap`: overlap range that causes `UNKNOWN` when the result is uncertain.
- `overlap_basis`: `vehicle` divides intersection by vehicle-box area; `roi` divides by ROI area and is useful when only a visible slice of a space is observable.

Measure ROI coordinates from the clean Ring JPEG, not from a browser screenshot that may be scaled or include controls. If the downloaded image dimensions differ from the reference dimensions, ParkWatch scales the configured ROI before classification. A fully hidden vehicle cannot be classified from that camera.

## Ring polling

Load credentials into the shell. A saved token also requires the Ring client credentials so it can be refreshed:

```bash
set -a
source app-credentials.env
set +a
```

Typical variables are:

```bash
RING_CLIENT_ID='...'
RING_CLIENT_SECRET='...'
RING_ACCESS_TOKEN='...'
DISCORD_WEBHOOK_URL='...'
```

List available devices:

```bash
python scripts/poll_ring.py --list-devices
```

Poll one camera every 60 seconds:

```bash
python scripts/poll_ring.py \
  --config config/vision.json \
  --device-id YOUR_RING_DEVICE_ID \
  --interval 60
```

Repeat `--device-id` for multiple cameras. Use `--once` for one test cycle. Use `--download-only` to download clean images for ROI calibration without running YOLO.

Each poll saves an annotated JPEG under `outputs/ring/`. Images older than one hour are removed by default. Change this with `--retention-days` or `PARKWATCH_RETENTION_DAYS`; token and non-image files are not removed.

## Discord notifications

Set `DISCORD_WEBHOOK_URL` and use polling mode. Notifications are sent only when the spot was previously `OCCUPIED`, becomes `EMPTY` for the configured number of consecutive readings (two by default), and is outside its cooldown (15 minutes by default).

Snapshots narrower than 1280 pixels are analyzed and saved but do not update notification state by default. Change this with `--min-snapshot-width 0` or another width. The notification tracker is in memory, so restarting the process resets its transition history.

## Ring webhook receiver

The webhook receiver validates Ring HMAC signatures, deduplicates request IDs for the current process lifetime, handles the local OAuth token exchange/account-linking flow, downloads motion snapshots, and writes annotated analyses.

```bash
export RING_CLIENT_ID='...'
export RING_CLIENT_SECRET='...'
export RING_HMAC_KEY='...'
export RING_ACCESS_TOKEN='...' # optional when using outputs/ring/tokens.json
python scripts/ring_webhook.py --config config/vision.json
```

The local server exposes `/health`, `/oauth/token`, `/ring/link`, `/ring/home`, and `/webhooks/ring`. A deployed webhook requires publicly reachable HTTPS and an appropriate reverse proxy or tunnel. The webhook path currently analyzes snapshots but does not send Discord notifications; use polling for notification behavior.

## Docker

The Docker image runs the polling worker. Create an untracked `app-credentials.env` file:

```env
PARKWATCH_DEVICE_IDS="FRONT_DOOR_DEVICE_ID FRONT_GARAGE_DEVICE_ID"
PARKWATCH_INTERVAL="60"
RING_ACCESS_TOKEN="..."
RING_CLIENT_ID="..."
RING_CLIENT_SECRET="..."
DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
```

Protect the file and start the service:

```bash
chmod 600 app-credentials.env
docker compose build
docker compose up -d
docker compose logs -f parkwatch
```

The compose file mounts `config/vision.json` read-only and persists Ring outputs and the Ultralytics cache under `outputs/`. Stop the service with `docker compose down`.

Do not put secrets in the Dockerfile or image. Rotate any credential that has been exposed.

## Tests

```bash
PYTHONPATH=. pytest
```

The tests cover ROI classification, configuration validation, Ring signature/OAuth request behavior, notification state transitions, and output retention.
