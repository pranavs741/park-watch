from parkwatch.notifications import SpotStateTracker
from parkwatch.vision.occupancy import ParkingStatus


def test_tracker_requires_occupied_to_empty_transition_and_confirmation():
    tracker = SpotStateTracker(empty_confirmations=2, cooldown_seconds=100)

    assert not tracker.should_notify("driveway", ParkingStatus.EMPTY, now=0)
    assert not tracker.should_notify("driveway", ParkingStatus.OCCUPIED, now=1)
    assert not tracker.should_notify("driveway", ParkingStatus.EMPTY, now=2)
    assert tracker.should_notify("driveway", ParkingStatus.EMPTY, now=3)


def test_tracker_does_not_alert_unknown_or_repeat_during_cooldown():
    tracker = SpotStateTracker(empty_confirmations=1, cooldown_seconds=100)

    tracker.should_notify("driveway", ParkingStatus.OCCUPIED, now=0)
    assert tracker.should_notify("driveway", ParkingStatus.EMPTY, now=1)
    assert not tracker.should_notify("driveway", ParkingStatus.EMPTY, now=2)
    assert not tracker.should_notify("driveway", ParkingStatus.UNKNOWN, now=3)

