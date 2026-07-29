#!/usr/bin/env bash
# Run the Shark-ISR Humble container on the Pi 5 (host = Pi OS 64-bit).
#
# The four wires across the container boundary (see docs discussion / B07):
#   --network host   DDS discovery works; nodes talk exactly as in SITL.
#   /dev/hailo0      Hailo-8L PCIe device (host driver exposes it).
#   Pixhawk serial   uXRCE-DDS agent <-> PX4; adjust to your wiring.
#   camera           NOT a device here — read over localhost UDP from rpicam-vid.
#
# Usage:
#   docker/run_pi.sh                 # interactive shell in the container
#   docker/run_pi.sh <cmd...>        # run a command instead of a shell
set -euo pipefail

IMAGE="${IMAGE:-shark-isr:humble}"
WS="${WS:-$HOME/shark-isr-vtol/ros2_ws}"          # host path to ros2_ws
PIXHAWK_DEV="${PIXHAWK_DEV:-/dev/ttyAMA0}"        # UART; /dev/ttyACM0 if USB

devices=(--device /dev/hailo0)
[[ -e "$PIXHAWK_DEV" ]] && devices+=(--device "$PIXHAWK_DEV") \
    || echo "warn: $PIXHAWK_DEV not present — skipping (set PIXHAWK_DEV)." >&2

exec docker run -it --rm \
    --network host \
    "${devices[@]}" \
    -v "$WS":/ws \
    "$IMAGE" \
    "$@"
