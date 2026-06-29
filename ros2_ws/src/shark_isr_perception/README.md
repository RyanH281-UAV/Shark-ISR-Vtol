# shark_isr_perception

**Purpose:** Camera ingest (Camera Module 3 Standard lens) + Hailo-8L onboard inference + pinhole/flat-earth geolocation. Publishes geolocated `Detection` messages to guidance and telemetry.

## Nodes

### `mock_camera_node` (sim only)
Publishes `sensor_msgs/Image` + `CameraInfo` from disk images or noise at configurable FPS. Used in sim so `detector_node` has a camera source without physical hardware.

### `detector_node`
Subscribes to `/camera/image_raw` and `/vehicle_state`.  
In **sim mode** (`use_sim:=true`): publishes probabilistic mock `Detection` messages to exercise the full pipeline.  
In **real mode** (`use_sim:=false`): loads a Hailo `.hef` model via HailoRT and runs onboard inference on each frame.

## Interfaces

| Direction | Topic | Type |
|---|---|---|
| Subscribes | `/camera/image_raw` | `sensor_msgs/Image` |
| Subscribes | `/vehicle_state` | `shark_isr_interfaces/VehicleState` |
| Publishes  | `/detection` | `shark_isr_interfaces/Detection` |
| Publishes  | `/camera/camera_info` | `sensor_msgs/CameraInfo` (mock camera only) |

## Parameters (`config/perception.yaml`)

| Name | Type | Default | Description |
|---|---|---|---|
| `use_sim` | bool | `true` | Sim mode (mock detections, no HailoRT) |
| `hef_path` | str | `""` | Path to `.hef` model on Pi 5 (real mode) |
| `confidence_threshold` | float | `0.45` | Minimum score to publish Detection |
| `mock_detection_prob` | float | `0.02` | Per-frame mock detection probability (sim) |
| `image_width` | int | `640` | Camera image width [px] |
| `image_height` | int | `480` | Camera image height [px] |
| `fx`, `fy`, `cx`, `cy` | float | `616, 616, 320, 240` | Camera intrinsics [px] |
| `camera_fps` | float | `10.0` | Mock camera frame rate |
| `mock_images_dir` | str | `""` | Dir of test frames for mock camera (`""` = noise) |

## Camera geometry (ADR-010)

Camera Module 3 **Standard lens** (Sony IMX708). Diagonal FOV ~66° (half-angle 33°).  
At 640×480: `fx = fy ≈ 616 px` (approximate — calibrate for production).  
**Patrol altitude: 30 m AGL.** Ground footprint ≈ 39 m. Shark pixel size ≈ 41 px at 640 px input (above 32 px detection threshold).

## Geolocation (`geolocate.py`)

Pinhole + flat-earth. No ROS dependencies — fully unit-testable.

```
pixel (u, v)
  → normalised ray in camera optical frame      [u/fx, v/fy, 1]
  → rotated to body FLU                         R_cam_to_body (nadir: top=forward)
  → rotated to ENU world                        attitude_q conjugate
  → intersected with z=0 plane                  t = agl_m / (-ray_enu_z)
  → ENU offset                                  (dx_east, dy_north) = t × ray_enu_xy
  → WGS-84 delta                                flat-earth lat/lon
```

Uncertainty: `position_std_m = footprint_half × (agl_uncertainty / agl_m) + 1.0 m`.

## Run in isolation (sim)

```bash
# WSL, workspace sourced
ros2 launch shark_isr_perception perception.launch.py use_sim:=true

# verify detections appear (stochastic, ~2% per frame at 10 Hz)
ros2 topic echo /detection --once
```

## Run in isolation (real hardware — Pi 5)

```bash
ros2 launch shark_isr_perception perception.launch.py \
    use_sim:=false \
    hef_path:=/path/to/shark_detector.hef
```

## Tests

```bash
# No ROS or simulator needed — pure math tests
pytest test/test_geolocate.py -v
```

9 tests cover: centre bbox → directly below, known pixel offset → correct ENU displacement, AGL linear scaling, invalid AGL raises, position_std positive, non-zero vehicle position.
