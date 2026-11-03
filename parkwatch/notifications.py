"""Notification delivery and conservative parking-state transitions."""

from dataclasses import dataclass, field
import json
from pathlib import Path
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

    def send_spot_opened(self, spot_name: str, device_id: str, camera_name: str | None = None) -> None:
        camera_label = camera_name or device_id
        payload = {
            "content": f"🅿️ **{spot_name}** is open (camera **{camera_label}**).",
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
    state_file: Path | None = None
    _statuses: dict[str, ParkingStatus] = field(default_factory=dict, init=False)
    _empty_streaks: dict[str, int] = field(default_factory=dict, init=False)
    _empty_after_occupied: dict[str, bool] = field(default_factory=dict, init=False)
    _last_notifications: dict[str, float] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        if self.empty_confirmations < 1:
            raise ValueError("empty_confirmations must be at least 1")
        if self.cooldown_seconds < 0:
            raise ValueError("cooldown_seconds cannot be negative")
        if self.state_file is not None:
            self._load()

    def _load(self) -> None:
        """Restore state from disk, treating a missing/corrupt file as empty state."""
        assert self.state_file is not None
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            self._statuses = {
                key: ParkingStatus(value) for key, value in data.get("statuses", {}).items()
            }
            self._empty_streaks = {
                str(key): int(value) for key, value in data.get("empty_streaks", {}).items()
            }
            self._empty_after_occupied = {
                str(key): bool(value) for key, value in data.get("empty_after_occupied", {}).items()
            }
            self._last_notifications = {
                str(key): float(value) for key, value in data.get("last_notifications", {}).items()
            }
        except (FileNotFoundError, OSError, ValueError, TypeError, json.JSONDecodeError):
            # A bad state file should not prevent the poller from starting.
            self._statuses.clear()
            self._empty_streaks.clear()
            self._empty_after_occupied.clear()
            self._last_notifications.clear()

    def _save(self) -> None:
        """Atomically persist state so a VM/container restart can resume transitions."""
        if self.state_file is None:
            return
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "statuses": {key: status.value for key, status in self._statuses.items()},
            "empty_streaks": self._empty_streaks,
            "empty_after_occupied": self._empty_after_occupied,
            "last_notifications": self._last_notifications,
        }
        temporary = self.state_file.with_name(f".{self.state_file.name}.tmp")
        temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(self.state_file)

    def should_notify(self, key: str, status: ParkingStatus, now: float | None = None) -> bool:
        previous = self._statuses.get(key)
        if status == ParkingStatus.EMPTY:
            if previous == ParkingStatus.OCCUPIED or previous == ParkingStatus.UNKNOWN:
                self._empty_after_occupied[key] = True
            self._empty_streaks[key] = self._empty_streaks.get(key, 0) + 1
        else:
            self._empty_streaks[key] = 0
            self._empty_after_occupied[key] = False
        self._statuses[key] = status

        if not self._empty_after_occupied.get(key, False):
            self._save()
            return False
        if self._empty_streaks[key] < self.empty_confirmations:
            self._save()
            return False

        # Wall-clock time is required here because monotonic timestamps cannot
        # be compared across process/VM restarts.
        timestamp = time.time() if now is None else now
        last = self._last_notifications.get(key)
        if last is not None and timestamp - last < self.cooldown_seconds:
            self._save()
            return False
        self._last_notifications[key] = timestamp
        self._save()
        return True
