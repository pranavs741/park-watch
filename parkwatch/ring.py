"""Small, dependency-light adapter for the Ring Partner API."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
from pathlib import Path
import time
from base64 import urlsafe_b64encode
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEFAULT_RING_API_URL = "https://api.amazonvision.com"
DEFAULT_RING_OAUTH_URL = "https://oauth.ring.com"
DEFAULT_USER_AGENT = "ParkWatch/0.1"


def _oauth_http_error(exc: HTTPError, operation: str) -> RuntimeError:
    """Build a useful OAuth error without exposing request credentials."""
    detail = ""
    try:
        payload = json.loads(exc.read().decode("utf-8"))
        if isinstance(payload, dict):
            error = payload.get("error")
            description = payload.get("error_description") or payload.get("message")
            if error and description:
                detail = f": {error} ({description})"
            elif error or description:
                detail = f": {error or description}"
    except (UnicodeDecodeError, json.JSONDecodeError):
        # Ring may return an HTML proxy/WAF response. Avoid reflecting arbitrary
        # response content because this error is also returned by the local HTTP server.
        pass
    return RuntimeError(f"Ring {operation} failed with HTTP {exc.code}{detail}")


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


class RingOAuthClient:
    """Exchange short-lived Ring authorization codes for API tokens."""

    def __init__(self, client_id: str, client_secret: str, oauth_url: str = DEFAULT_RING_OAUTH_URL):
        if not client_id or not client_secret:
            raise ValueError("Ring client ID and client secret are required")
        self.client_id = client_id
        self.client_secret = client_secret
        self.oauth_url = oauth_url.rstrip("/")

    def exchange_authorization_code(self, code: str) -> dict[str, Any]:
        if not code:
            raise ValueError("Ring authorization code is required")
        body = urlencode(
            {
                "grant_type": "authorization_code",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
            }
        ).encode("utf-8")
        request = Request(
            f"{self.oauth_url}/oauth/token",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "User-Agent": DEFAULT_USER_AGENT,
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                token_data = json.loads(response.read())
        except HTTPError as exc:
            raise _oauth_http_error(exc, "token exchange") from exc
        if not token_data.get("access_token") or not token_data.get("refresh_token"):
            raise RuntimeError("Ring token response did not contain both access_token and refresh_token")
        return token_data

    def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        if not refresh_token:
            raise ValueError("Ring refresh token is required")
        body = urlencode(
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            }
        ).encode("utf-8")
        request = Request(
            f"{self.oauth_url}/oauth/token",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "User-Agent": DEFAULT_USER_AGENT,
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                token_data = json.loads(response.read())
        except HTTPError as exc:
            raise _oauth_http_error(exc, "token refresh") from exc
        if not token_data.get("access_token") or not token_data.get("refresh_token"):
            raise RuntimeError("Ring refresh response did not contain both access_token and refresh_token")
        return token_data


class RingTokenStore:
    """Local development token store; use a secrets manager in production."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        return json.loads(self.path.read_text())

    def save(self, token_data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        stored = dict(token_data)
        stored["expires_at"] = time.time() + int(token_data.get("expires_in", 0))
        self.path.write_text(json.dumps(stored, indent=2) + "\n")
        self.path.chmod(0o600)

    def access_token(self, oauth: RingOAuthClient) -> str | None:
        token_data = self.load()
        if not token_data:
            return None
        if token_data.get("expires_at", 0) <= time.time() + 60:
            token_data = oauth.refresh_access_token(token_data.get("refresh_token", ""))
            token_data["account_id"] = self.load().get("account_id")
            token_data["status"] = self.load().get("status", "unclaimed")
            self.save(token_data)
        return token_data.get("access_token")


def verify_account_link_nonce(nonce: str, timestamp: str, account_id: str, hmac_key: str) -> bool:
    """Verify Ring's URL-safe, time-limited account-linking nonce."""
    try:
        timestamp_ms = int(timestamp)
    except (TypeError, ValueError):
        return False
    if abs(time.time() * 1000 - timestamp_ms) > 600_000:
        return False
    message = f"{timestamp}:{account_id}".encode("utf-8")
    expected = urlsafe_b64encode(hmac.new(hmac_key.encode("utf-8"), message, hashlib.sha256).digest()).rstrip(b"=").decode("ascii")
    return hmac.compare_digest(nonce, expected)


class RingApiClient:
    """Minimal Ring client for image retrieval used by ParkWatch."""

    def __init__(self, access_token: str | None = None, base_url: str = DEFAULT_RING_API_URL):
        self.access_token = access_token
        self.base_url = base_url.rstrip("/")

    def _request_json(self, path: str, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.access_token:
            raise RuntimeError("Ring access token is not available; complete OAuth account linking first")
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8") if payload is not None else None,
            method=method,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": DEFAULT_USER_AGENT,
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read())
        except HTTPError as exc:
            raise RuntimeError(f"Ring API request failed with HTTP {exc.code}") from exc

    def list_devices(self) -> dict[str, Any]:
        """Return devices the current Ring access token can access."""
        return self._request_json("/v1/devices")

    def user_profile(self) -> dict[str, Any]:
        return self._request_json("/v1/users/me")

    def complete_account_link(self, nonce: str, account_identifier: str) -> None:
        self._request_json("/v1/accounts/me/app-integrations", "POST", {"account_identifier": account_identifier, "nonce": nonce})
        self._request_json("/v1/accounts/me/app-integrations", "PATCH", {"status": "completed"})

    def download_snapshot(self, device_id: str, output: str | Path, component_id: str | None = None) -> Path:
        if not self.access_token:
            raise RuntimeError("Ring access token is not available; complete OAuth account linking first")
        request = Request(
            f"{self.base_url}/v1/devices/{device_id}/media/image/download",
            data=json.dumps({"components": [{"component_id": component_id or "1"}]}).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
                "Accept": "image/jpeg, image/png",
                "User-Agent": DEFAULT_USER_AGENT,
            },
        )
        destination = Path(output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with urlopen(request, timeout=30) as response:
                destination.write_bytes(response.read())
        except HTTPError as exc:
            raise RuntimeError(f"Ring snapshot download failed with HTTP {exc.code}") from exc
        return destination
