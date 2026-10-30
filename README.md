# ParkWatch

ParkWatch is an event-driven parking-space monitor. It analyzes Ring snapshots with YOLO and a configurable polygon ROI. The current Ring integration accepts signed motion webhooks and downloads the corresponding camera snapshot for analysis; OAuth account linking and durable state are still deployment work.

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config/vision.example.json config/vision.json
```

The first YOLO run downloads the configured Ultralytics model. Keep `config/vision.json` local; it is ignored by git if you create it from the example.

## Analyze an image

```bash
python scripts/analyze_image.py path/to/ring-screenshot.jpg \
  --config config/vision.json \
  --output outputs/annotated.jpg
```

The command prints `EMPTY`, `OCCUPIED`, or `UNKNOWN`, along with each detected vehicle's confidence and ROI overlap. The annotated image shows the ROI polygon and detection boxes. A vehicle is considered occupying the space when its bounding-box intersection divided by its bounding-box area meets `min_roi_overlap`.

The initial safety-oriented behavior is conservative: low-confidence detections and partial overlaps produce `UNKNOWN`, avoiding a false “parking open” result. Tune thresholds against real watermarked Ring images and a labeled dataset before enabling notifications.

`inference_image_size` controls how large an image YOLO analyzes internally. A
larger value such as `1280` preserves more detail for distant vehicles, at the
cost of additional processing time. `min_candidate_confidence` is the lower
floor for detections retained as possible vehicles; candidates below that floor
are treated as model noise and cannot force a parking spot to `UNKNOWN`.

## ROI and multi-camera configuration

`parking_roi` is an ordered list of image pixel coordinates. Use a polygon rather than a rectangle and avoid the Ring watermark where possible. The polygon must be valid and non-empty. A future ROI setup utility can write this same format.

For several cameras or parking spaces, replace the single `parking_roi` with a
`cameras` object. Each key is the complete Ring device ID, and each camera has
one or more named `parking_spots`:

```json
{
  "model": "yolo11n.pt",
  "min_vehicle_confidence": 0.60,
  "min_roi_overlap": 0.50,
  "ambiguous_overlap": 0.05,
  "vehicle_classes": ["car", "truck", "bus", "motorcycle"],
  "cameras": {
    "FRONT_DOOR_DEVICE_ID": {
      "parking_spots": [
        {"name": "Driveway", "roi": [[534, 793], [920, 833], [963, 938], [537, 919]]}
      ]
    },
    "FRONT_GARAGE_DEVICE_ID": {
      "parking_spots": [
        {"name": "Garage left", "roi": [[100, 500], [300, 500], [300, 700], [100, 700]]},
        {"name": "Garage right edge", "roi": [[1400, 300], [1530, 300], [1530, 650], [1400, 650]], "overlap_basis": "roi", "min_vehicle_confidence": 0.35, "min_roi_overlap": 0.35}
      ]
    }
  }
}
```

The garage coordinates above only demonstrate the format; measure coordinates
from the downloaded Ring JPEG because browser screenshots may be scaled and
include controls. `overlap_basis` defaults to `vehicle`, meaning the
intersection is divided by the detected vehicle area. Use `roi` for a small
visible slice of a mostly hidden parking space; it divides by the ROI area
instead. A fully hidden vehicle cannot be classified from that camera.

## Ring webhook receiver

After obtaining Ring Partner API credentials and an access token through the OAuth account-linking flow, set the webhook HMAC key and token:

```bash
export RING_CLIENT_ID='...'
export RING_CLIENT_SECRET='...'
export RING_HMAC_KEY='...'
# Optional at startup; Ring can provide it through /oauth/token.
export RING_ACCESS_TOKEN='...'
python scripts/ring_webhook.py --config config/vision.json
```

The receiver exposes `/health` for a local check, `/oauth/token` to receive Ring's short-lived authorization code and exchange it for tokens using your Client ID and Client Secret, `/ring/link` for single-user Ring account linking, `/ring/home` for connection status, and `/webhooks/ring` to process signed event notifications. Tokens are saved to `outputs/ring/tokens.json` with restrictive local permissions and refreshed automatically when they are near expiry. This prototype automatically links the first Ring account it receives; it has no multi-user login system. Ring requires publicly reachable HTTPS endpoints in a deployed environment; the local server is intended for development behind a tunnel or reverse proxy.

## Polling Ring every minute

Polling is an alternative to motion webhooks. First load the environment file and list the devices available to the access token:

```bash
set -a
source app-credentials.env
set +a
python scripts/poll_ring.py --list-devices
```

Then start a one-minute polling loop using the device ID returned by Ring:

```bash
python scripts/poll_ring.py \
  --config config/vision.json \
  --device-id YOUR_RING_DEVICE_ID \
  --interval 60
```

To download a clean camera image for measuring ROI coordinates without running
YOLO, use:

```bash
python scripts/poll_ring.py \
  --device-id YOUR_RING_DEVICE_ID \
  --download-only
```

To poll multiple configured cameras, repeat `--device-id`:

```bash
python scripts/poll_ring.py \
  --config config/vision.json \
  --device-id FRONT_DOOR_DEVICE_ID \
  --device-id FRONT_GARAGE_DEVICE_ID \
  --interval 60
```

Each poll downloads one snapshot, runs the existing detector, and saves an annotated image under `outputs/ring/`. Filenames contain the configured parking spot names and the UTC poll timestamp, for example `right-curb-partial-view__2026-10-27T17-04-05.123456Z.jpg`. If one camera has several spots, all of their names are joined with `--` because they share one annotated camera image. The rate limit is a ceiling, not a target; one request per minute per camera is intentionally conservative. Press `Ctrl+C` to stop cleanly.

## Discord notifications

Create a Discord incoming webhook in the channel where you want alerts, then set
the webhook URL in the environment. An incoming webhook is sufficient for
personal alerts; a Discord bot is not required.

```bash
export DISCORD_WEBHOOK_URL='https://discord.com/api/webhooks/...'
python scripts/poll_ring.py \
  --config config/vision.json \
  --device-id YOUR_RING_DEVICE_ID \
  --interval 60
```

ParkWatch sends an alert only after a spot changes from `OCCUPIED` to `EMPTY`
and remains empty for two consecutive readings. `UNKNOWN` never triggers an
open-space alert. Alerts for the same spot have a 15-minute cooldown. These
defaults can be changed with `--empty-confirmations` and
`--notification-cooldown`.

Notifications use each camera's configured `name` instead of its long Ring
device ID. By default, snapshots narrower than `1280` pixels are analyzed and
saved but are excluded from notification state changes, preventing a low-
resolution Ring thumbnail from causing a false alert. Change this with
`--min-snapshot-width` or set it to `0` to disable the quality gate.

## Run with Docker

Docker is the recommended deployment format for a VM. The image contains the
Python and YOLO dependencies, while credentials, Ring tokens, snapshots, and
the local YOLO model remain outside the image.

Add the device IDs to `app-credentials.env` as a space-separated value. Do not
commit that file:

```bash
PARKWATCH_DEVICE_IDS="FRONT_DOOR_DEVICE_ID FRONT_GARAGE_DEVICE_ID"
PARKWATCH_INTERVAL="60"
```

Build and start the poller:

```bash
docker compose build
docker compose up -d
docker compose logs -f parkwatch
```

The container restarts automatically if it exits or Docker restarts. Stop it
with `docker compose down`. The Ring token, annotated snapshots, and downloaded
YOLO model are stored in `outputs/`, so they survive container replacement.

Never put credentials in the `Dockerfile` or image. Keep
`app-credentials.env` readable only by your user (`chmod 600
app-credentials.env`) and rotate credentials that have been exposed.

## Tests

```bash
PYTHONPATH=. pytest
```
