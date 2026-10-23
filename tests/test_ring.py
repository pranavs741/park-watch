import hashlib
import hmac
import json

import pytest

from parkwatch.ring import RingEvent, RingWebhookProcessor, verify_webhook_signature


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
