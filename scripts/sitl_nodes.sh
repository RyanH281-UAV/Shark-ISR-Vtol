#!/usr/bin/env bash
# Tab 3 of shark_isr_sitl.bat — waits for autopilot_bridge, then launches
# guidance_node + mission_node together. Ctrl-C kills both.
set -eo pipefail

sleep 12

cd ~/projects/shark-isr-vtol/ros2_ws
source install/setup.bash

echo "[shark-isr] Waiting for autopilot_bridge (/vehicle_state)..."
until ros2 topic list 2>/dev/null | grep -q "/vehicle_state"; do
    sleep 1
done
echo "[shark-isr] autopilot_bridge up — launching guidance_node + mission_node"

PIDS=()
cleanup() { kill "${PIDS[@]}" 2>/dev/null || true; }
trap cleanup SIGINT SIGTERM EXIT

ros2 launch shark_isr_guidance guidance.launch.py &
PIDS+=($!)
ros2 launch shark_isr_mission mission.launch.py &
PIDS+=($!)

wait "${PIDS[@]}"
