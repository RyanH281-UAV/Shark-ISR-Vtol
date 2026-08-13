#!/usr/bin/env bash
# Run the Shark-ISR Humble container on the Pi 5 (host = Pi OS 64-bit).
#
# What crosses the container boundary (see ADR-017):
#   --network host   DDS discovery works; nodes talk exactly as in SITL.
#   --ipc host       shared /dev/shm — see the note below.
#   /dev/hailo0      Hailo-8L PCIe device (host driver exposes it).
#   Pixhawk serial   uXRCE-DDS agent <-> PX4; adjust to your wiring.
#   libhailort.so*   host userspace lib, bind-mounted — see the note below.
#   ros2_ws          bind-mounted so you edit on the host, build in the container.
#   camera           NOT a device here — read over localhost UDP from rpicam-vid.
#
# --ipc host: --network host shares the network namespace but NOT the IPC
# namespace, so each container gets its own /dev/shm. Fast-DDS prefers its
# shared-memory transport between same-host participants; discovery runs over
# UDP and matches fine, so `ros2 topic list` looks healthy while the writer
# pushes into a ring buffer in *its own* /dev/shm that nobody reads — a silent
# data-plane failure with a healthy-looking control plane.
#   Scope, stated honestly: in the current single-container design nothing
#   actually needs this — the host runs no ROS 2 and `docker exec` joins the
#   same namespaces. It becomes load-bearing the moment the uXRCE-DDS agent and
#   the stack are split across two `docker run` invocations. Set now so that
#   split doesn't produce a baffling silent failure later. Bonus: it also picks
#   up the host's /dev/shm sizing instead of Docker's 64 MB default.
#
# Usage:
#   docker/run_pi.sh                 # interactive shell in the container
#   docker/run_pi.sh <cmd...>        # run a command instead of a shell
set -euo pipefail
shopt -s nullglob                                 # so a no-match glob yields nothing

IMAGE="${IMAGE:-shark-isr:humble}"
WS="${WS:-$HOME/shark-isr-vtol/ros2_ws}"          # host path to ros2_ws
PIXHAWK_DEV="${PIXHAWK_DEV:-/dev/ttyAMA0}"        # UART; /dev/ttyACM0 if USB

[[ -d "$WS" ]] || { echo "err: workspace '$WS' not found (set WS=...)." >&2; exit 1; }

devices=()
if [[ -e /dev/hailo0 ]]; then
    devices+=(--device /dev/hailo0)
else
    echo "warn: /dev/hailo0 not present — is hailo-all installed on the host? " \
         "Container starts without it; detector_node will fail in real mode." >&2
fi
if [[ -e "$PIXHAWK_DEV" ]]; then
    devices+=(--device "$PIXHAWK_DEV")
else
    echo "warn: $PIXHAWK_DEV not present — skipping (set PIXHAWK_DEV)." >&2
fi

# The pip HailoRT wheel is bindings-only: the only .so it ships is
# _pyhailort.cpython-310-aarch64-linux-gnu.so, whose DT_NEEDED lists
# libhailort.so.4.20.0. Nothing bundles that library, so it has to come from
# the host (installed by hailo-all).
#
# What this buys, precisely: the userspace lib and the kernel driver are
# guaranteed to be the same build. What it does NOT buy: independence from the
# host version. DT_NEEDED names a fully-versioned filename, not a .so.4 SONAME
# — so if the host is upgraded to 4.21, the mount supplies libhailort.so.4.21.0,
# the loader still wants 4.20.0, and `import hailo_platform` fails outright.
# Rebuild the image with a matching wheel whenever hailo-all is upgraded.
# ponytail: ldconfig lookup rather than a hardcoded glob — Debian arm64 may put
# this under /usr/lib/aarch64-linux-gnu/ instead.
libmounts=()
while read -r f; do
    [[ -e "$f" ]] && libmounts+=(-v "$f:/opt/hailort-lib/$(basename "$f"):ro")
done < <(ldconfig -p 2>/dev/null | awk '/libhailort\.so/{print $NF}' | sort -u)
if [[ ${#libmounts[@]} -eq 0 ]]; then
    echo "warn: no libhailort.so* found via ldconfig — is hailo-all installed?" >&2
fi

# Run as the invoking user, else colcon writes root-owned build/ install/ log/
# into the host's bind-mounted ros2_ws and the host user can no longer build.
# ponytail: --user with HOME=/tmp is enough; no /etc/passwd entry needed for colcon.
tty=(-i); [[ -t 0 ]] && tty=(-it)                 # so non-interactive callers work

exec docker run "${tty[@]}" --rm \
    --network host \
    --ipc host \
    --user "$(id -u):$(id -g)" \
    -e HOME=/tmp \
    "${devices[@]}" \
    "${libmounts[@]}" \
    -e LD_LIBRARY_PATH=/opt/hailort-lib:/opt/ros/humble/lib \
    -v "$WS":/ws \
    "$IMAGE" \
    "$@"
