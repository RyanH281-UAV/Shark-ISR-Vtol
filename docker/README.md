# docker/ — Humble container for the Pi 5 companion computer

Runs the frozen ROS 2 **Humble** stack on the Pi without putting Ubuntu on the
Pi. Host = **Pi OS 64-bit** (hardware just works: Hailo, camera, serial); the
container = Ubuntu 22.04 + Humble (matches SITL bit-for-bit). Implements the
`HARDWARE_BRINGUP.md` **B07** container path — B07a host gates pass, B07b is at
3 of 4 (the camera stream gate is still open).

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
hailortcli fw-control identify                   # Board Name: Hailo-8 / Arch: HAILO8L
rpicam-hello -t 2000                             # camera preview works
dpkg -l | grep hailort                           # note version -> Dockerfile arg
```

## Build

Download the HailoRT aarch64 cp310 wheel **matching the host `hailort` version**
from the Hailo Developer Zone into this folder, then:

```bash
cd ~/shark-isr-vtol
docker build -f docker/Dockerfile.pi \
  --build-arg HAILORT_WHL=docker/<the-wheel>.whl \
  -t shark-isr:humble .
```

The `docker/` prefix is required: the build context is the repo root, and `COPY`
resolves against the context, not against the Dockerfile's directory. `.dockerignore`
keeps the 12 GB of datasets and site renders out of that context — without it the
Pi ships the whole repo to the daemon on every build.

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
# B07b hardware checks:
# NOTE: the pip wheel ships bindings only — there is no hailortcli binary inside
# the container. Check the device through the Python API instead.
python3 -c "from hailo_platform import VDevice; VDevice(); print('hailo ok')"
ros2 launch shark_isr_perception perception.launch.py use_sim:=false \
  hef_path:=/ws/models/shark_detector.hef            # B08
ros2 topic hz /camera/image_raw                      # frames flowing from host stream
ros2 topic echo /detection                           # detections publishing
```

`camera_node` (container) reads the UDP stream and republishes it as
`/camera/image_raw` — the same topic `mock_camera_node` uses in sim, so
`detector_node` and everything downstream are untouched.

## What crosses the boundary (`run_pi.sh`)

| Wire | How | Why |
|---|---|---|
| DDS network | `--network host` | node discovery; topics flow as in SITL |
| DDS shared memory | `--ipc host` | `--network host` does *not* share `/dev/shm`; without this a second container's Fast-DDS writes into its own SHM segment and data silently never arrives while discovery still looks healthy. Not load-bearing in the current single-container setup — set so the two-container split fails loudly instead |
| Hailo-8L | `--device /dev/hailo0` | PCIe inference device |
| HailoRT userspace | bind-mount host `libhailort.so*` | the pip wheel is bindings-only; its `DT_NEEDED` names `libhailort.so.4.20.0` exactly, so host and wheel must match |
| Pixhawk | `--device /dev/ttyAMA0` | uXRCE-DDS agent ↔ PX4 (set `PIXHAWK_DEV`) |
| Workspace | `-v $WS:/ws` + `--user $(id -u)` | edit on host, build in container. The `--user` matters: as root, `colcon` leaves root-owned `build/ install/ log/` in your host tree |
| Camera | localhost UDP, **not** a device | avoids libcamera-in-Docker; native on host |

## Later / tighter (not now)

- **HailoRT version drift** — rebuild the image whenever you `apt upgrade`
  `hailo-all` on the host; keep the wheel in lockstep.
- **Camera latency — measure this at B08, it is not cosmetic.** No capture
  timestamp crosses the UDP boundary, so `camera_node` stamps frames when it
  *reads* them, and `detector_node` geolocates each frame against the *latest*
  `vehicle_state`. Lag therefore converts directly into position error: ~10 m per
  second of lag at cruise, against a 39 m diagonal footprint. **Nothing currently
  bounds the queue depth** — `camera_node` requests `CAP_PROP_BUFFERSIZE=1`, but
  that property is unsupported on the FFMPEG backend (`set()` returns `False` on
  the OpenCV 4.5.4 / libavformat 58.45 this image ships), so it is a no-op on the
  `udp://` path. Total lag is unmeasured. If it turns out to matter, drain per tick
  (read N, publish the last), move capture to a thread, or as a last resort move to
  `picamera2` inside the container (pass `/dev/media*`, `/dev/video*`,
  `/run/udev`) — more fragile, lower latency.
- **Stream size must match `perception.yaml`.** `rpicam-vid --width/--height` has
  to equal `image_width`/`image_height`. `camera_node` warns and stretches
  otherwise, and a stretch invalidates the `fx/fy/cx/cy` intrinsics.
- **Compose** — a `docker-compose.yml` only earns its place once you're running
  agent + stack as separate long-lived services. One `docker run` is enough for
  bench bring-up.
