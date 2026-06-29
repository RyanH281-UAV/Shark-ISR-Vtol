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
#    ln -sf ~/projects/shark-isr-vtol/sim/worlds/shark_isr_coastal.sdf \
#           ~/PX4-Autopilot/Tools/simulation/gz/worlds/shark_isr_coastal.sdf
#    source ros2_ws/install/setup.bash   (after colcon build with px4_msgs)
#
#  Usage:
#    Terminal 1:  ./scripts/run_sim.sh
#    Terminal 2:  source ros2_ws/install/setup.bash && ros2 topic list | grep fmu
#
#  What this starts (in order — Gazebo must be ready before PX4 attaches):
#    1. Gazebo Harmonic (gz sim server, shark_isr_coastal world, headless-safe)
#    2. MicroXRCE-DDS agent  (UDP4 :8888 — bridges PX4 uORB ↔ ROS 2 DDS)
#    3. PX4 SITL             (airframe 4020 gz_tiltrotor, attaches to running gz)
#
#  To stop: Ctrl+C (traps SIGINT and kills all children)
# =============================================================================
set -euo pipefail

# ── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
WORLDS_DIR="${PROJECT_DIR}/sim/worlds"
PX4_DIR="${HOME}/PX4-Autopilot"
PX4_GZ_WORLDS="${PX4_DIR}/Tools/simulation/gz/worlds"

# ── Sanity checks ────────────────────────────────────────────────────────────
if [[ ! -f "${PX4_DIR}/build/px4_sitl_default/bin/px4" ]]; then
    echo "[shark-isr] ERROR: PX4 SITL binary not found."
    echo "            Run: cd ${PX4_DIR} && make px4_sitl_default"
    exit 1
fi

if [[ ! -f "${WORLDS_DIR}/shark_isr_coastal.sdf" ]]; then
    echo "[shark-isr] ERROR: World file not found: ${WORLDS_DIR}/shark_isr_coastal.sdf"
    exit 1
fi

if [[ ! -e "${PX4_GZ_WORLDS}/shark_isr_coastal.sdf" ]]; then
    echo "[shark-isr] ERROR: World not symlinked into PX4 worlds dir."
    echo "            Run: ln -sf ${WORLDS_DIR}/shark_isr_coastal.sdf \\"
    echo "                        ${PX4_GZ_WORLDS}/shark_isr_coastal.sdf"
    exit 1
fi

if ! command -v micro-xrce-dds-agent &>/dev/null && ! command -v MicroXRCEAgent &>/dev/null; then
    echo "[shark-isr] ERROR: MicroXRCEAgent not found."
    echo "            Install: sudo snap install micro-xrce-dds-agent --edge"
    exit 1
fi

AGENT_CMD="$(command -v MicroXRCEAgent 2>/dev/null || command -v micro-xrce-dds-agent)"

# ── WSL2 clock sync ───────────────────────────────────────────────────────────
# One-shot sync at startup. The previous continuous hwclock loop ran every 5s
# and was injecting step jumps each time WSL2's virtual HW clock had drifted,
# which triggered PX4's "time jump detected" and reset the DDS session.
sudo hwclock -s 2>/dev/null || true

# ── Kill any stale sim processes before starting ──────────────────────────────
echo "[shark-isr] Killing any stale gz/PX4/XRCE processes..."
pkill -9 -f "gz sim|gz_sim|px4_sitl|bin/px4|MicroXRCEAgent|micro-xrce-dds" 2>/dev/null || true
sleep 3
echo "[shark-isr] Stale processes cleared."

# ── Wipe stale PX4 state (dataman + params carry over between runs) ───────────
PX4_ROOTFS="${PX4_DIR}/build/px4_sitl_default/rootfs"
rm -f "${PX4_ROOTFS}/dataman" "${PX4_ROOTFS}"/*.bson
echo "[shark-isr] Cleared stale PX4 state."

# ── Cleanup trap ─────────────────────────────────────────────────────────────
PIDS=()
cleanup() {
    trap - SIGINT SIGTERM EXIT
    echo ""
    echo "[shark-isr] Shutting down SITL..."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null || true
    echo "[shark-isr] Done."
}
trap cleanup SIGINT SIGTERM EXIT

# ── 1. Gazebo Harmonic sim server ─────────────────────────────────────────────
# Source PX4's gz env to get plugin + model paths, then launch the world.
# PX4 v1.16 requires Gazebo to be running before the px4 binary starts.
# Pre-init these so gz_env.sh's append syntax ($VAR:$NEW) doesn't hit set -u.
export GZ_SIM_RESOURCE_PATH=${GZ_SIM_RESOURCE_PATH:-}
export GZ_SIM_SYSTEM_PLUGIN_PATH=${GZ_SIM_SYSTEM_PLUGIN_PATH:-}
# shellcheck source=/dev/null
source "${PX4_DIR}/build/px4_sitl_default/rootfs/gz_env.sh"

echo "[shark-isr] Starting Gazebo (shark_isr_coastal world)..."
echo "[shark-isr] GPS origin: Cottesloe Beach, Perth WA (-31.998, 115.748)"
gz sim -r -s "${PX4_GZ_WORLDS}/shark_isr_coastal.sdf" &
PIDS+=($!)

# Wait for world to be ready (poll gz topic list)
echo "[shark-isr] Waiting for Gazebo world..."
for i in $(seq 1 30); do
    if gz topic -l 2>/dev/null | grep -q "shark_isr_coastal/clock"; then
        echo "[shark-isr] Gazebo world ready (${i}s)"
        break
    fi
    if [[ $i -eq 30 ]]; then
        echo "[shark-isr] ERROR: Timed out waiting for Gazebo world."
        exit 1
    fi
    sleep 1
done

# ── 2. MicroXRCE-DDS agent ───────────────────────────────────────────────────
echo "[shark-isr] Starting MicroXRCE-DDS agent on UDP4 :8888..."
"${AGENT_CMD}" udp4 -p 8888 &
PIDS+=($!)
sleep 1

# ── 3. PX4 SITL — attaches to running Gazebo world ───────────────────────────
echo "[shark-isr] Launching PX4 SITL (airframe 4020 gz_tiltrotor)..."
export PX4_SYS_AUTOSTART=4020
export PX4_GZ_WORLD=shark_isr_coastal
# SITL param overrides — bypass hardware checks not present in simulation
export PX4_PARAM_CBRK_SUPPLY_CHK=894281   # no power monitor in sim
export PX4_PARAM_COM_RC_IN_MODE=4         # no RC input needed
export PX4_PARAM_NAV_RCL_ACT=0            # no RC loss failsafe
export PX4_PARAM_COM_DISARM_PRFLT=-1      # disable pre-flight auto-disarm
export PX4_PARAM_COM_OF_LOSS_T=5.0        # tolerate brief offboard stream gaps

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

wait "${PIDS[@]}"
