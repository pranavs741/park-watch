# ParkWatch

ParkWatch is an event-driven parking-space monitor. This repository currently implements milestone 1: analyzing a single Ring screenshot with YOLO and a configurable polygon ROI. Ring webhooks, media retrieval, state persistence, and notifications are intentionally reserved for later milestones.

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

## Tests

```bash
pytest
```
