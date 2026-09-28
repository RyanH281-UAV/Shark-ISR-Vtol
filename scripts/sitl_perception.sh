#!/usr/bin/env bash
# Tab 4 of shark_isr_sitl.bat — mock_camera_node + detector_node (sim mode).
# Required for T11 only; harmless to leave running for T06-T10.
set -eo pipefail

sleep 12

cd ~/projects/shark-isr-vtol/ros2_ws
source install/setup.bash

exec ros2 launch shark_isr_perception perception.launch.py use_sim:=true
