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

## ROI configuration

`parking_roi` is an ordered list of image pixel coordinates. Use a polygon rather than a rectangle and avoid the Ring watermark where possible. The polygon must be valid and non-empty. A future ROI setup utility can write this same format.

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

Each poll downloads one snapshot, runs the existing detector, and saves an annotated image under `outputs/ring/`. The rate limit is a ceiling, not a target; one request per minute per camera is intentionally conservative. Press `Ctrl+C` to stop cleanly.

## Tests

```bash
pytest
```
