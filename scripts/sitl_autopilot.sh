#!/usr/bin/env bash
# Tab 2 of shark_isr_sitl.bat — waits for the PX4 DDS bridge, then launches
# the autopilot_bridge node. Run scripts/run_sim.sh (Tab 1) first.
set -eo pipefail

sleep 8

cd ~/projects/shark-isr-vtol/ros2_ws
source install/setup.bash

echo "[shark-isr] Waiting for PX4 DDS bridge (/fmu/in/offboard_control_mode)..."
until ros2 topic list 2>/dev/null | grep -q "/fmu/in/offboard_control_mode"; do
    sleep 1
done
echo "[shark-isr] Bridge up — launching autopilot_bridge"

exec ros2 launch shark_isr_autopilot autopilot.launch.py
