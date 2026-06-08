# Detection.msg — A single shark (or other object) detection event
#
# Published by:  shark_isr_perception
# Subscribed by: shark_isr_guidance, shark_isr_telemetry
#
# Coordinate frames
#   bbox_*      : image frame, normalised [0.0, 1.0], origin top-left, +x right, +y down
#   geo_*       : WGS-84; altitude AMSL [m]
#   position_std_m : horizontal 1-sigma [m]

std_msgs/Header header          # stamp = detection time; frame_id = "camera_optical"

# ── Detector output ──────────────────────────────────────────────────────────
uint8 CLASS_SHARK = 0
uint8 object_class              # see CLASS_* constants
float32 confidence              # [0.0, 1.0] HailoRT detection score

# Bounding box in image frame (normalised, origin top-left)
float32 bbox_x_min              # left edge   [0.0, 1.0]
float32 bbox_y_min              # top edge    [0.0, 1.0]
float32 bbox_x_max              # right edge  [0.0, 1.0]
float32 bbox_y_max              # bottom edge [0.0, 1.0]

# ── Geolocated position (WGS-84) ─────────────────────────────────────────────
# Derived via: camera intrinsics + vehicle attitude (ENU/FLU quat) + AGL estimate
bool geo_valid                  # true if transform succeeded and AGL is reliable
float64 latitude_deg            # [deg] WGS-84
float64 longitude_deg           # [deg] WGS-84
float32 altitude_amsl_m         # [m] AMSL (≈ 0 over sea; kept for consistency)
float32 position_std_m          # [m] horizontal 1-sigma uncertainty (propagated)
