#!/usr/bin/env bash
# scaffold.sh — create the modular ROS 2 workspace skeleton for the shark-ISR VTOL stack.
# Each package gets a README stub so "what everything does" is documented from day one.
# Idempotent: re-running will not overwrite existing files.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WS="$ROOT/ros2_ws/src"
echo "Scaffolding into: $WS"
mkdir -p "$WS"

# package name | one-line purpose | build type (ament_python | ament_cmake)
PKGS=(
  "shark_isr_interfaces|Custom msgs/srvs/actions — the integration contract (Detection, SearchState, GuidanceSetpoint, MissionCommand).|ament_cmake"
  "shark_isr_bringup|Launch files and aggregated params; brings the whole stack (or subsets) up.|ament_python"
  "shark_isr_autopilot|The ONLY package talking to the autopilot. PX4 via uXRCE-DDS + px4_msgs (MAVLink fallback): arm, mode, offboard setpoints, telemetry, failsafe.|ament_python"
  "shark_isr_perception|Camera Module 3 (libcamera/picamera2) + onboard Hailo-8L .hef detector; publishes geolocated Detection messages.|ament_python"
  "shark_isr_guidance|Search-pattern generation, Bayesian search map, detection-triggered orbit/loiter; emits GuidanceSetpoints.|ament_python"
  "shark_isr_mission|Mission state machine (transit -> search -> track -> return); arbitrates guidance vs phase; failsafe transitions.|ament_python"
  "shark_isr_telemetry|Structured logging of flight + detections + decisions; relays summaries to the GCS/operator.|ament_python"
)

write_readme () {
  local dir="$1" name="$2" purpose="$3"
  local f="$dir/README.md"
  if [[ -f "$f" ]]; then echo "  skip README (exists): $name"; return; fi
  cat > "$f" <<EOF
# $name

**Purpose:** $purpose

## Interfaces
- **Subscribes:** _TODO_
- **Publishes:** _TODO_
- **Services / Actions:** _TODO_

## Parameters
| Name | Type | Default | Description |
| --- | --- | --- | --- |
| _TODO_ | | | |

## Run in isolation
\`\`\`bash
# TODO: minimal command to launch/run this package alone (e.g. against SITL)
\`\`\`

## Notes
- Depends only on \`shark_isr_interfaces\` for cross-package types.
- No behaviour is "done" until it has a passing SITL check (see docs/BUILD_PLAN.md).
EOF
  echo "  wrote README: $name"
}

for entry in "${PKGS[@]}"; do
  IFS='|' read -r name purpose build <<< "$entry"
  pdir="$WS/$name"
  mkdir -p "$pdir"
  write_readme "$pdir" "$name" "$purpose"

  # Minimal manifest stubs (Ruflo/Claude Code will flesh these out per package)
  if [[ ! -f "$pdir/package.xml" ]]; then
    cat > "$pdir/package.xml" <<EOF
<?xml version="1.0"?>
<package format="3">
  <name>$name</name>
  <version>0.0.0</version>
  <description>$purpose</description>
  <maintainer email="you@example.com">Ryan Hughes</maintainer>
  <license>TODO</license>
  <buildtool_depend>$build</buildtool_depend>
  <!-- TODO: add depends -->
</package>
EOF
  fi
  if [[ "$build" == "ament_python" && ! -f "$pdir/setup.py" ]]; then
    mkdir -p "$pdir/$name" "$pdir/resource"
    touch "$pdir/$name/__init__.py" "$pdir/resource/$name"
    echo "    (ament_python layout stubbed)"
  elif [[ "$build" == "ament_cmake" && ! -f "$pdir/CMakeLists.txt" ]]; then
    echo "    (ament_cmake package — add CMakeLists.txt + msg/srv when interfaces are frozen)"
  fi
done

# Top-level workspace README
WSR="$ROOT/ros2_ws/README.md"
if [[ ! -f "$WSR" ]]; then
  cat > "$WSR" <<'EOF'
# ros2_ws — Shark-ISR VTOL autonomy workspace

Build: `colcon build` from this directory. Source: `source install/setup.bash`.
One package per responsibility; all cross-package types live in `shark_isr_interfaces`.
See ../docs/ARCHITECTURE.md for the system view and ../CLAUDE.md for project conventions.
EOF
  echo "wrote workspace README"
fi

echo "Done. Next: freeze shark_isr_interfaces (Phase 1) before implementing nodes."
