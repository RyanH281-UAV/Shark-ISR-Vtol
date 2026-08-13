# Bring-Up Log

> Dated entries per `HARDWARE_BRINGUP.md` ground rule 5. Newest on top.

## 2026-08-13 — B07b (container gates)

**Result: 3 of 4 PASS.** `docker build` ✓ · in-container `colcon build` ✓ · Hailo device
reachable from inside the container ✓ · `ros2 topic hz /camera/image_raw` **still open**.

Three fixes came out of the attempt. All three were reviewed against the actual libraries
afterwards, and two of the original explanations were wrong — recorded here in corrected form
so the next person debugging this is not misled.

**1. `--ipc host`.** `--network host` shares the network namespace but not IPC, so each
container gets its own `/dev/shm`. Fast-DDS discovers over UDP (works) then prefers its
shared-memory transport for same-host traffic — participants match, `ros2 topic list` looks
healthy, and the writer pushes into a ring buffer in its own `/dev/shm` that nobody reads.
*Correction:* in the current single-container design nothing actually needs this — the host runs
no ROS 2. It becomes load-bearing once the uXRCE-DDS agent and the stack are split across two
`docker run` invocations. Set now so that split fails loudly rather than silently.

**2. Bind-mount the host `libhailort.so*`.** The pip wheel is bindings-only — the only `.so` it
ships is `_pyhailort.cpython-310-aarch64-linux-gnu.so`. *Correction:* the first write-up claimed
this made the container "always match whatever driver the host runs". It does the opposite.
`readelf -d` shows `DT_NEEDED: libhailort.so.4.20.0` — a fully versioned filename, not a `.so.4`
SONAME. The mount guarantees userspace and kernel driver are the same build, but the
wheel↔host version match stays a hard requirement: upgrade `hailo-all` to 4.21 and
`import hailo_platform` fails outright. Rebuild the image with a matching wheel on every upgrade.

**3. Force the MJPEG demuxer** (`OPENCV_FFMPEG_CAPTURE_OPTIONS=input_format;mjpeg`).
*Correction:* not because ffmpeg cannot detect bare MJPEG — it probes a bare elementary MJPEG
stream from a file without difficulty. The real problem is joining a live `udp://` source
mid-stream: the first `probesize` bytes may contain no JPEG SOI, so `ff_mjpeg_probe` scores low
and detection is non-deterministic. Forcing the demuxer removes the race.

Also found while reviewing, and fixed: `CAP_PROP_BUFFERSIZE=1` is a **no-op on the FFMPEG
backend** (`set()` returns `False` on OpenCV 4.5.4 / libavformat 58.45), so the latency
mitigation cited in the module docstring, `docker/README.md` and ADR-017 was not doing anything.
Frame lag remains unmeasured — that is B08 work. And `.dockerignore`'s `build/`/`install/`/`log/`
were non-recursive, so ~195 MB of `ros2_ws/build|install|log` still shipped to the daemon on
every build despite the file existing to prevent exactly that.

Next: get `/camera/image_raw` flowing, then B08.

## 2026-08-10 — B07a (host gates)

**Result: PASS.**

AI HAT+ and Camera Module 3 physically attached to the Pi 5 for the first time.

```
$ hailortcli fw-control identify
Executing on device: 0001:01:00.0
Identifying board
Control Protocol Version: 2
Firmware Version: 4.20.0 (release,app,extended context switch buffer)
Board Name: Hailo-8
Device Architecture: HAILO8L

$ rpicam-hello --list-cameras
0 : imx708 [4608x2592 10-bit RGGB] (/base/.../imx708@1a)

$ rpicam-hello -t 10s
[ran clean, no errors]
```

Required a `hailo_pci` dkms rebuild first — `apt full-upgrade` had landed kernel
`6.12.96+rpt-rpi-2712`, newer than the dkms module was built for
(`6.12.93+rpt-rpi-2712` / `...-v8`), so `hailortcli` initially failed with
`HAILO_DRIVER_NOT_INSTALLED` despite the device showing fine in `lspci`. Fixed with:
```
sudo dkms install hailo_pci/4.20.0 -k $(uname -r)
sudo modprobe hailo_pci
```
Check `dkms status` against `uname -r` after any future kernel-bumping `apt upgrade`
on this box.

Boot media: genuine, H2testw-verified USB 3.0 stick (interim bridge, ~8 MB/s write).
See `HARDWARE_BRINGUP.md` B07 for the full storage-corruption root-cause writeup
(counterfeit AliExpress SD cards, confirmed via H2testw — real capacity ~3.9 GB on
a card reporting 64 GB).

Next: B07b — Docker container build/run, per `docker/README.md`.
