#!/usr/bin/env bash
# =============================================================================
#  SHARK ISR VTOL — SITL Launcher
#  Project: shark-isr-vtol (autonomous shark monitoring)
#
#  DO NOT use this script for the SkimWing capstone or any other project.
#  This launches a PX4 tiltrotor SITL against the shark_isr_coastal Gazebo world.
#
#  Prerequisites (one-time setup — see sim/README.md):
#    sudo snap install micro-xrce-dds-agent --edge
#    source ros2_ws/install/setup.bash   (after colcon build with px4_msgs)
#
#  Usage:
#    Terminal 1:  ./scripts/run_sim.sh
#    Terminal 2:  source ros2_ws/install/setup.bash && ros2 topic list
#
#  What this starts:
#    1. MicroXRCE-DDS agent  (UDP4 :8888 — bridges PX4 uORB ↔ ROS 2 DDS)
#    2. PX4 SITL             (airframe 4020 gz_tiltrotor + shark coastal world)
#       Gazebo opens automatically; the tiltrotor spawns over Cottesloe Beach, Perth WA.
#
#  To stop: Ctrl+C (traps SIGINT and kills all children)
# =============================================================================
set -euo pipefail

# ── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
WORLDS_DIR="${PROJECT_DIR}/sim/worlds"
PX4_DIR="${HOME}/PX4-Autopilot"

# ── Sanity checks ────────────────────────────────────────────────────────────
if [[ ! -f "${PX4_DIR}/build/px4_sitl_default/bin/px4" ]]; then
    echo "[shark-isr] ERROR: PX4 SITL binary not found at ${PX4_DIR}/build/px4_sitl_default/bin/px4"
    echo "            Run: cd ${PX4_DIR} && make px4_sitl_default"
    exit 1
fi

if [[ ! -f "${WORLDS_DIR}/shark_isr_coastal.sdf" ]]; then
    echo "[shark-isr] ERROR: World file not found: ${WORLDS_DIR}/shark_isr_coastal.sdf"
    exit 1
fi

if ! command -v micro-xrce-dds-agent &>/dev/null && ! command -v MicroXRCEAgent &>/dev/null; then
    echo "[shark-isr] ERROR: MicroXRCEAgent not found."
    echo "            Install: sudo snap install micro-xrce-dds-agent --edge"
    exit 1
fi

# Resolve the agent command name (snap installs as micro-xrce-dds-agent)
AGENT_CMD="$(command -v MicroXRCEAgent 2>/dev/null || command -v micro-xrce-dds-agent)"

# ── Cleanup trap ─────────────────────────────────────────────────────────────
PIDS=()
cleanup() {
    echo ""
    echo "[shark-isr] Shutting down SITL..."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null || true
    echo "[shark-isr] Done."
}
trap cleanup SIGINT SIGTERM EXIT

# ── 1. MicroXRCE-DDS agent ───────────────────────────────────────────────────
echo "[shark-isr] Starting MicroXRCE-DDS agent on UDP4 :8888..."
"${AGENT_CMD}" udp4 -p 8888 &
PIDS+=($!)
sleep 1

# ── 2. PX4 SITL — tiltrotor + shark coastal world ────────────────────────────
echo "[shark-isr] Launching PX4 SITL (airframe 4020 gz_tiltrotor)..."
echo "[shark-isr] World: ${WORLDS_DIR}/shark_isr_coastal.sdf"
echo "[shark-isr] GPS origin: Cottesloe Beach, Perth WA (-31.998, 115.748)"
echo ""

export PX4_SYS_AUTOSTART=4020
export PX4_GZ_WORLD=shark_isr_coastal
export GZ_SIM_RESOURCE_PATH="${WORLDS_DIR}:${GZ_SIM_RESOURCE_PATH:-}"

cd "${PX4_DIR}"
./build/px4_sitl_default/bin/px4 -d &
PIDS+=($!)

echo ""
echo "[shark-isr] ─────────────────────────────────────────────────────"
echo "[shark-isr] SITL running. In a new terminal:"
echo "            source ${PROJECT_DIR}/ros2_ws/install/setup.bash"
echo "            ros2 topic list | grep fmu"
echo "[shark-isr] ─────────────────────────────────────────────────────"
echo ""

# Wait for all children
wait "${PIDS[@]}"
