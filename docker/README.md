# docker/ — Humble container for the Pi 5 companion computer

Runs the frozen ROS 2 **Humble** stack on the Pi without putting Ubuntu on the
Pi. Host = **Pi OS 64-bit** (hardware just works: Hailo, camera, serial); the
container = Ubuntu 22.04 + Humble (matches SITL bit-for-bit). Closes
`HARDWARE_BRINGUP.md` **B07**.

## Why containerise

The stack was frozen on Humble (Ubuntu 22.04); Hailo + Camera Module 3 are
first-class on Pi OS, painful on Ubuntu-on-Pi5. Containerising gets both:
hardware from the host, ROS from the image. DDS makes the boundary invisible —
your node graph is unchanged.

## One-time host setup (Pi OS 64-bit)

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y hailo-all docker.io          # Hailo driver+tools, Docker
sudo usermod -aG docker "$USER"                  # re-login after this
sudo reboot
# verify hardware on the HOST:
hailortcli fw-control identify                   # must report Hailo-8L
rpicam-hello -t 2000                             # camera preview works
dpkg -l | grep hailort                           # note version -> Dockerfile arg
```

## Build

Download the HailoRT aarch64 cp310 wheel **matching the host `hailort` version**
from the Hailo Developer Zone into this folder, then:

```bash
cd ~/shark-isr-vtol
docker build -f docker/Dockerfile.pi \
  --build-arg HAILORT_WHL=<the-wheel>.whl \
  -t shark-isr:humble .
```

## Run

**Camera stays native on the host** — start the stream first (own terminal):

```bash
rpicam-vid -t 0 --codec mjpeg --width 640 --height 480 \
  --framerate 10 --inline -o 'udp://127.0.0.1:8554'
```

Then the container:

```bash
docker/run_pi.sh                 # shell inside the container
# first time, inside:
cd /ws && colcon build && source install/setup.bash
# B07 hardware checks:
hailortcli fw-control identify                       # Hailo seen from container
ros2 launch shark_isr_perception perception.launch.py use_sim:=false \
  hef_path:=/ws/models/shark_detector.hef            # B08
ros2 topic hz /camera/image_raw                      # frames flowing from host stream
ros2 topic echo /detection                           # detections publishing
```

`camera_node` (container) reads the UDP stream and republishes it as
`/camera/image_raw` — the same topic `mock_camera_node` uses in sim, so
`detector_node` and everything downstream are untouched.

## The four wires (`run_pi.sh`)

| Wire | How | Why |
|---|---|---|
| DDS network | `--network host` | node discovery; topics flow as in SITL |
| Hailo-8L | `--device /dev/hailo0` | PCIe inference device |
| Pixhawk | `--device /dev/ttyAMA0` | uXRCE-DDS agent ↔ PX4 (set `PIXHAWK_DEV`) |
| Camera | localhost UDP, **not** a device | avoids libcamera-in-Docker; native on host |

## Later / tighter (not now)

- **HailoRT version drift** — rebuild the image whenever you `apt upgrade`
  `hailo-all` on the host; keep the wheel in lockstep.
- **Camera latency** — MJPEG-over-UDP adds a little; measure at B08. If it
  matters, move to `picamera2` inside the container (pass `/dev/media*`,
  `/dev/video*`, `/run/udev`) — more fragile, lower latency.
- **Compose** — a `docker-compose.yml` only earns its place once you're running
  agent + stack as separate long-lived services. One `docker run` is enough for
  bench bring-up.
