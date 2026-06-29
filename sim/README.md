# sim/ — Shark ISR VTOL Simulation

**This directory is SPECIFIC to the shark-monitoring ISR project.**
Do not share worlds, scripts, or configs with the SkimWing capstone or any other project.

## Stack

| Component | Version | Role |
|---|---|---|
| PX4 Autopilot | v1.16.0 | SITL firmware |
| Gazebo Harmonic | gz-sim 8.x | Physics + sensor simulation |
| MicroXRCE-DDS agent | snap `--edge` | PX4 uORB ↔ ROS 2 DDS bridge |
| px4_msgs | release/1.16 | ROS 2 message types matching PX4 v1.16 |

## One-time setup

```bash
# 1. Install MicroXRCE-DDS agent (once per WSL install)
sudo snap install micro-xrce-dds-agent --edge

# 2. Symlink the project world into PX4's worlds directory (once per PX4 clone)
ln -sf ~/projects/shark-isr-vtol/sim/worlds/shark_isr_coastal.sdf \
       ~/PX4-Autopilot/Tools/simulation/gz/worlds/shark_isr_coastal.sdf

# 3. Build the shark workspace (includes px4_msgs + shark_isr_interfaces)
source /opt/ros/humble/setup.bash
cd ros2_ws
colcon build
source install/setup.bash
```

## Running the simulation

PX4 v1.16 with Gazebo Harmonic requires Gazebo to start first; the PX4 binary
then attaches to the running world. `run_sim.sh` handles this automatically.

```bash
# Terminal 1 — Gazebo + MicroXRCE-DDS agent + PX4 SITL
./scripts/run_sim.sh

# Terminal 2 — verify PX4 topics visible in ROS 2
source ros2_ws/install/setup.bash
ros2 topic list | grep fmu

# Expected topics include:
#   /fmu/in/offboard_control_mode
#   /fmu/in/trajectory_setpoint
#   /fmu/in/vehicle_command
#   /fmu/out/vehicle_local_position
#   /fmu/out/vehicle_attitude
#   /fmu/out/battery_status
#   /fmu/out/vtol_vehicle_status
```

## Airframe

**4020 `gz_tiltrotor`** — VTOL Tiltrotor in Gazebo Harmonic.

Geometry matches the Hornet: two front tilting rotors + one fixed rear rotor.
`CA_AIRFRAME=3` (Tiltrotor VTOL), `MAV_TYPE=21` (VTOL Tiltrotor).

## World

`sim/worlds/shark_isr_coastal.sdf` — open ocean surface, Perth coastal GPS origin.

- **GPS origin:** Cottesloe Beach, Perth WA (lat -31.998°, lon 115.748°, elev 0 m AMSL)
- Ocean surface collision plane (vehicle can land on water for testing)
- Coastal sky and sun angle
- 2 km × 2 km surface area

## Troubleshooting

| Symptom | Fix |
|---|---|
| `MicroXRCEAgent not found` | `sudo snap install micro-xrce-dds-agent --edge` |
| `px4 binary not found` | `cd ~/PX4-Autopilot && make px4_sitl_default` |
| No `/fmu/` topics in ROS 2 | Confirm agent is running: `ps aux \| grep MicroXRCE` |
| Gazebo doesn't open | Check `GZ_SIM_RESOURCE_PATH` includes `sim/worlds/` |
