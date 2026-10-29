"""Readable, collision-resistant names for ParkWatch image output."""

from datetime import datetime, timezone
from pathlib import Path
import re


def filename_slug(value: str) -> str:
    """Convert a user-facing parking spot name into a safe filename part."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug or "parking-spot"


def timestamped_image_path(
    output_dir: str | Path,
    labels: list[str] | tuple[str, ...],
    timestamp: datetime | None = None,
) -> Path:
    """Build ``spot-name__UTC-timestamp.jpg`` for one annotated camera image."""
    captured_at = timestamp or datetime.now(timezone.utc)
    if captured_at.tzinfo is None:
        captured_at = captured_at.replace(tzinfo=timezone.utc)
    captured_at = captured_at.astimezone(timezone.utc)
    label = "--".join(filename_slug(item) for item in labels) or "parking-spot"
    utc_timestamp = captured_at.strftime("%Y-%m-%dT%H-%M-%S.%fZ")
    return Path(output_dir) / f"{label}__{utc_timestamp}.jpg"
