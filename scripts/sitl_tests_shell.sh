#!/usr/bin/env bash
# Tab 5 of shark_isr_sitl.bat — ready shell for running the T-series tests
# once Tabs 1-4 are all up. Does not auto-run so you can watch Gazebo first.
cd ~/projects/shark-isr-vtol
source ros2_ws/install/setup.bash

echo "[shark-isr] Stack should be up in Tabs 1-4. When ready, run e.g.:"
echo "    ./sim/tests/run_tests.sh t10 t11"
echo "    ./sim/tests/run_tests.sh          # full T06-T11"
exec bash
