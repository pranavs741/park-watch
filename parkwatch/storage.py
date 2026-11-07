"""Optional cloud storage for completed ParkWatch images."""

from pathlib import Path


class GcsImageUploader:
    """Upload images to Google Cloud Storage using application default credentials."""

    def __init__(self, bucket_name: str | None = None, prefix: str = "parkwatch"):
        self.bucket_name = bucket_name
        self.prefix = prefix.strip("/")
        self._bucket = None

        if bucket_name:
            try:
                from google.cloud import storage
            except ImportError as exc:  # pragma: no cover - depends on optional runtime dependency
                raise RuntimeError(
                    "PARKWATCH_GCS_BUCKET is set, but google-cloud-storage is not installed"
                ) from exc
            self._bucket = storage.Client().bucket(bucket_name)

    @property
    def enabled(self) -> bool:
        return self._bucket is not None

    def upload(self, image_path: Path) -> str | None:
        """Upload an image and return its gs:// URI, or None when disabled."""
        if self._bucket is None:
            return None
        object_name = f"{self.prefix}/{image_path.name}" if self.prefix else image_path.name
        self._bucket.blob(object_name).upload_from_filename(str(image_path), content_type="image/jpeg")
        return f"gs://{self.bucket_name}/{object_name}"
