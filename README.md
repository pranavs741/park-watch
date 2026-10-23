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
export RING_HMAC_KEY='...'
export RING_ACCESS_TOKEN='...'
python scripts/ring_webhook.py --config config/vision.json
```

The receiver listens on `POST /webhooks/ring`, verifies `X-Signature: sha256=...`, ignores duplicate `request_id` deliveries, downloads the snapshot from Ring, and writes the annotated result to `outputs/ring/`. Ring requires a publicly reachable HTTPS webhook endpoint in a deployed environment; the local server is intended for development behind a tunnel or reverse proxy.

## Tests

```bash
pytest
```
