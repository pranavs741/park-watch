"""Small, dependency-light adapter for the Ring Partner API."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

DEFAULT_RING_API_URL = "https://api.amazonvision.com"


@dataclass(frozen=True)
class RingEvent:
    request_id: str
    event_type: str
    device_id: str
    component_ids: tuple[str, ...] = ()
    raw: dict[str, Any] | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "RingEvent":
        attributes = payload.get("data", {}).get("attributes", {})
        request_id = payload.get("request_id") or payload.get("id") or attributes.get("request_id")
        event_type = payload.get("event_type") or payload.get("type") or attributes.get("event_type") or attributes.get("type")
        device_id = payload.get("device_id") or attributes.get("device_id")
        component_ids = payload.get("component_ids") or attributes.get("component_ids") or []
        missing = [name for name, value in (("request_id", request_id), ("event_type", event_type), ("device_id", device_id)) if not value]
        if missing:
            raise ValueError(f"Ring webhook is missing: {', '.join(missing)}")
        return cls(str(request_id), str(event_type), str(device_id), tuple(map(str, component_ids)), payload)


def verify_webhook_signature(body: bytes, signature: str, hmac_key: str) -> bool:
    """Verify Ring's ``X-Signature: sha256=<hex>`` header."""
    if not signature or not hmac_key:
        return False
    provided = signature.removeprefix("sha256=").strip()
    expected = hmac.new(hmac_key.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(provided, expected)


class RingWebhookProcessor:
    """Validate and deduplicate webhook deliveries for one process lifetime."""

    def __init__(self, hmac_key: str):
        self.hmac_key = hmac_key
        self._processed: set[str] = set()

    def parse(self, body: bytes, signature: str) -> RingEvent | None:
        if not verify_webhook_signature(body, signature, self.hmac_key):
            raise PermissionError("invalid Ring webhook signature")
        event = RingEvent.from_payload(json.loads(body))
        if event.request_id in self._processed:
            return None
        self._processed.add(event.request_id)
        return event


class RingApiClient:
    """Minimal Ring client for image retrieval used by ParkWatch."""

    def __init__(self, access_token: str, base_url: str = DEFAULT_RING_API_URL):
        if not access_token:
            raise ValueError("Ring access token is required")
        self.access_token = access_token
        self.base_url = base_url.rstrip("/")

    def download_snapshot(self, device_id: str, output: str | Path, component_id: str | None = None) -> Path:
        request = Request(
            f"{self.base_url}/v1/devices/{device_id}/media/image/download",
            data=json.dumps({"components": [{"component_id": component_id or "1"}]}).encode("utf-8"),
            method="POST",
            headers={"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json", "Accept": "image/jpeg, image/png"},
        )
        destination = Path(output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with urlopen(request, timeout=30) as response:
                destination.write_bytes(response.read())
        except HTTPError as exc:
            raise RuntimeError(f"Ring snapshot download failed with HTTP {exc.code}") from exc
        return destination
