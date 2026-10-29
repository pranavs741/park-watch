"""Notification delivery and conservative parking-state transitions."""

from dataclasses import dataclass, field
import json
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .vision.occupancy import ParkingStatus


class DiscordWebhookNotifier:
    """Send personal notifications through a Discord incoming webhook."""

    def __init__(self, webhook_url: str, timeout: float = 10.0):
        if not webhook_url:
            raise ValueError("Discord webhook URL cannot be empty")
        self.webhook_url = webhook_url
        self.timeout = timeout

    def send_spot_opened(self, spot_name: str, device_id: str) -> None:
        payload = {
            "content": f"🅿️ **{spot_name}** is open (camera `{device_id}`).",
            "allowed_mentions": {"parse": []},
        }
        request = Request(
            self.webhook_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "ParkWatch/0.1"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                if response.status >= 300:
                    raise RuntimeError(f"Discord webhook returned HTTP {response.status}")
        except HTTPError as exc:
            raise RuntimeError(f"Discord webhook returned HTTP {exc.code}") from exc


@dataclass
class SpotStateTracker:
    """Track transitions and require stable EMPTY readings before alerting."""

    empty_confirmations: int = 2
    cooldown_seconds: float = 900.0
    _statuses: dict[str, ParkingStatus] = field(default_factory=dict, init=False)
    _empty_streaks: dict[str, int] = field(default_factory=dict, init=False)
    _empty_after_occupied: dict[str, bool] = field(default_factory=dict, init=False)
    _last_notifications: dict[str, float] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        if self.empty_confirmations < 1:
            raise ValueError("empty_confirmations must be at least 1")
        if self.cooldown_seconds < 0:
            raise ValueError("cooldown_seconds cannot be negative")

    def should_notify(self, key: str, status: ParkingStatus, now: float | None = None) -> bool:
        previous = self._statuses.get(key)
        if status == ParkingStatus.EMPTY:
            if previous == ParkingStatus.OCCUPIED:
                self._empty_after_occupied[key] = True
            self._empty_streaks[key] = self._empty_streaks.get(key, 0) + 1
        else:
            self._empty_streaks[key] = 0
            self._empty_after_occupied[key] = False
        self._statuses[key] = status

        if not self._empty_after_occupied.get(key, False):
            return False
        if self._empty_streaks[key] < self.empty_confirmations:
            return False

        timestamp = time.monotonic() if now is None else now
        last = self._last_notifications.get(key)
        if last is not None and timestamp - last < self.cooldown_seconds:
            return False
        self._last_notifications[key] = timestamp
        return True
