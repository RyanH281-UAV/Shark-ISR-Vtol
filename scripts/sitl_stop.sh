#!/usr/bin/env bash
# Kills the full shark-isr-vtol SITL stack: ROS 2 launches, PX4, Gazebo, DDS agent.
pkill -f "ros2 launch shark_isr" 2>/dev/null
pkill -f "run_tests.sh" 2>/dev/null
sleep 1
pkill -9 -f "gz sim|gz_sim|px4_sitl|bin/px4|MicroXRCEAgent|micro-xrce-dds" 2>/dev/null
echo "Full shark-isr-vtol SITL stack stopped."
