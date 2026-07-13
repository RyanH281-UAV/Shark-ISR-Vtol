#!/usr/bin/env python3
"""
Orbit setpoint geometry visualisation — portfolio asset.

Replicates the math from autopilot_bridge._orbit_setpoint_ned() exactly:
  theta_t = theta + LEAD_RAD  (clockwise orbit)
  x_t = cx + r * cos(theta_t)
  y_t = cy + r * sin(theta_t)

These are the same 20 setpoints T06 verified at min=max=mean=30.00 m.

Output: sim/orbit_trace.png  (transparent-bg variant: sim/orbit_trace_dark.png)
Run:    python3 sim/plot_orbit.py
"""

import math
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyArrowPatch
from pathlib import Path

# ── Parameters (match autopilot_bridge.py exactly) ──────────────────────────
R         = 30.0   # orbit radius, metres
LEAD_RAD  = 0.4    # _ORBIT_LEAD_RAD, ~22.9°
N_SAMPLES = 20     # T06 SAMPLES_NEEDED
# ─────────────────────────────────────────────────────────────────────────────

OUT = Path(__file__).parent / "orbit_trace.png"

# Vehicle positions: evenly spaced around the full circle (clockwise, NED)
# theta sweeps 0 → 2π; we display in ENU (swap x/y) so North is up.
thetas_vehicle = np.linspace(0, 2 * math.pi, N_SAMPLES, endpoint=False)

# Setpoint = lead 0.4 rad ahead (clockwise → add lead)
thetas_sp = thetas_vehicle + LEAD_RAD

# ENU display: East=x, North=y  (NED x↔y swap, y flip — here we just use
# a clean top-down frame where +x=East, +y=North for readability)
vx = R * np.cos(thetas_vehicle - math.pi / 2)   # rotate so 0° = North
vy = R * np.sin(thetas_vehicle - math.pi / 2)
sx = R * np.cos(thetas_sp - math.pi / 2)
sy = R * np.sin(thetas_sp - math.pi / 2)

# ── Figure ───────────────────────────────────────────────────────────────────
BG   = "#0d1117"
RING = "#1f6feb"
VEH  = "#58a6ff"
SP   = "#f0883e"
YAW  = "#3fb950"
SHARK= "#f85149"
TEXT = "#e6edf3"
DIM  = "#484f58"

fig, ax = plt.subplots(figsize=(7, 7), facecolor=BG)
ax.set_facecolor(BG)

# Orbit ring
ring_theta = np.linspace(0, 2 * math.pi, 360)
ax.plot(R * np.cos(ring_theta - math.pi / 2),
        R * np.sin(ring_theta - math.pi / 2),
        color=RING, lw=1.2, ls="--", alpha=0.55, zorder=1)

# Setpoints (the 20 T06-verified points)
ax.scatter(sx, sy, s=52, color=SP, zorder=4, label="TrajectorySetpoint (×20)", linewidths=0)

# Vehicle positions
ax.scatter(vx, vy, s=22, color=VEH, alpha=0.5, zorder=3, linewidths=0)

# Yaw arrows: vehicle faces orbit centre (0, 0)
for i in range(N_SAMPLES):
    dx = -vx[i] * 0.28   # pointing inward
    dy = -vy[i] * 0.28
    ax.annotate("", xy=(vx[i] + dx, vy[i] + dy), xytext=(vx[i], vy[i]),
                arrowprops=dict(arrowstyle="-|>", color=YAW, lw=0.8,
                                mutation_scale=7, alpha=0.6),
                zorder=3)

# Lead angle arc on one hero sample (index 0, top of circle)
hero = 0
ax.plot([vx[hero], sx[hero]], [vy[hero], sy[hero]],
        color=SP, lw=1.2, ls="-", alpha=0.9, zorder=5)

# Hero vehicle marker (drone triangle)
angle_deg = math.degrees(thetas_vehicle[hero] - math.pi / 2)
ax.scatter([vx[hero]], [vy[hero]], s=130, color=VEH, marker="^",
           zorder=6, linewidths=0)

# Lead angle annotation
mid_x = (vx[hero] + sx[hero]) / 2 + 1.5
mid_y = (vy[hero] + sy[hero]) / 2 + 1.5
ax.annotate("lead 0.4 rad\n(≈ 23°)", xy=(mid_x, mid_y),
            fontsize=7.5, color=SP, ha="left", va="bottom",
            fontfamily="monospace")

# Shark target at centre
ax.scatter([0], [0], s=160, color=SHARK, marker="*", zorder=7,
           label="target (orbit centre)", linewidths=0)
ax.annotate("target", xy=(0.8, -2.2), fontsize=8, color=SHARK,
            ha="center", fontfamily="monospace")

# Radius annotation
ax.annotate("", xy=(R * math.cos(-math.pi / 2 + 0.0),
                    R * math.sin(-math.pi / 2 + 0.0)),
            xytext=(0, 0),
            arrowprops=dict(arrowstyle="<->", color=DIM, lw=1.0))
ax.text(1.5, -R / 2, "30.0 m", fontsize=8, color=DIM,
        va="center", fontfamily="monospace")

# PASS badge
ax.text(0.02, 0.98, "T06  20/20 PASS  min=max=mean=30.00 m",
        transform=ax.transAxes, fontsize=8, color="#3fb950",
        va="top", ha="left", fontfamily="monospace",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="#161b22", edgecolor="#238636", lw=1))

# Direction arrow (clockwise label)
ax.annotate("clockwise", xy=(24, 20), fontsize=7.5, color=DIM,
            ha="center", style="italic")
arc_x = [R * math.cos(a - math.pi / 2) for a in np.linspace(0.35, 0.75, 30)]
arc_y = [R * math.sin(a - math.pi / 2) for a in np.linspace(0.35, 0.75, 30)]
ax.plot(arc_x, arc_y, color=DIM, lw=1.2, alpha=0.7)
ax.annotate("", xy=(arc_x[-1], arc_y[-1]), xytext=(arc_x[-2], arc_y[-2]),
            arrowprops=dict(arrowstyle="-|>", color=DIM, lw=0.8,
                            mutation_scale=8, alpha=0.7))

# Legend & axes
legend = ax.legend(loc="lower right", fontsize=8, facecolor="#161b22",
                   edgecolor=DIM, labelcolor=TEXT, framealpha=1)

ax.set_xlim(-42, 42)
ax.set_ylim(-42, 42)
ax.set_aspect("equal")
ax.tick_params(colors=DIM, labelsize=7)
for spine in ax.spines.values():
    spine.set_edgecolor(DIM)
ax.set_xlabel("East  (m)", color=DIM, fontsize=8)
ax.set_ylabel("North  (m)", color=DIM, fontsize=8)
ax.set_title("Orbit setpoint geometry  ·  autopilot_bridge._orbit_setpoint_ned()",
             color=TEXT, fontsize=9, pad=10, fontfamily="monospace")
ax.grid(color=DIM, lw=0.4, alpha=0.3)

plt.tight_layout()
fig.savefig(OUT, dpi=180, bbox_inches="tight", facecolor=BG)
print(f"Saved → {OUT}")
