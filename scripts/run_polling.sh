#!/bin/sh
set -eu

: "${PARKWATCH_DEVICE_IDS:?Set PARKWATCH_DEVICE_IDS to a space-separated list of Ring device IDs}"

set --
for device_id in $PARKWATCH_DEVICE_IDS; do
    set -- "$@" --device-id "$device_id"
done

exec python scripts/poll_ring.py \
    --config config/vision.json \
    --interval "${PARKWATCH_INTERVAL:-60}" \
    --min-snapshot-width "${PARKWATCH_MIN_SNAPSHOT_WIDTH:-1280}" \
    --empty-confirmations "${PARKWATCH_EMPTY_CONFIRMATIONS:-2}" \
    --notification-cooldown "${PARKWATCH_NOTIFICATION_COOLDOWN:-900}" \
    --notification-state-file "${PARKWATCH_NOTIFICATION_STATE_FILE:-outputs/ring/notification_state.json}" \
    "$@"
