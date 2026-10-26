import hashlib
import hmac
import json

import pytest

import parkwatch.ring
from parkwatch.ring import RingApiClient, RingEvent, RingOAuthClient, RingWebhookProcessor, verify_webhook_signature


def signed(body: bytes, key: str) -> str:
    return "sha256=" + hmac.new(key.encode(), body, hashlib.sha256).hexdigest()


def test_signature_and_duplicate_delivery():
    key = "test-key"
    body = json.dumps({"request_id": "req-1", "event_type": "motion_detected", "device_id": "cam-1"}).encode()
    processor = RingWebhookProcessor(key)
    assert verify_webhook_signature(body, signed(body, key), key)
    assert processor.parse(body, signed(body, key)).device_id == "cam-1"
    assert processor.parse(body, signed(body, key)) is None


def test_invalid_signature_rejected():
    processor = RingWebhookProcessor("test-key")
    with pytest.raises(PermissionError):
        processor.parse(b"{}", "sha256=bad")


def test_json_api_payload_is_supported():
    payload = {"data": {"attributes": {"request_id": "r", "event_type": "motion_detected", "device_id": "d", "component_ids": [2]}}}
    event = RingEvent.from_payload(payload)
    assert event == RingEvent("r", "motion_detected", "d", ("2",), payload)


def test_oauth_request_uses_park_watch_user_agent(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"access_token": "access", "refresh_token": "refresh"}).encode()

    def fake_urlopen(request, timeout):
        captured["request"] = request
        return Response()

    monkeypatch.setattr(parkwatch.ring, "urlopen", fake_urlopen)
    RingOAuthClient("client", "secret").exchange_authorization_code("code")

    assert captured["request"].get_header("User-agent") == "ParkWatch/0.1"


def test_single_camera_snapshot_omits_components(monkeypatch, tmp_path):
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b"image"

    class Opener:
        def open(self, request, timeout):
            captured["request"] = request
            return Response()

    monkeypatch.setattr(parkwatch.ring, "build_opener", lambda *handlers: Opener())
    destination = tmp_path / "snapshot.jpg"
    RingApiClient("token").download_snapshot("device", destination)

    payload = json.loads(captured["request"].data)
    assert payload["type"] == "latest_in_range"
    assert payload["image_options"] == {"format": "jpeg"}
    assert "components" not in payload
    assert destination.read_bytes() == b"image"
