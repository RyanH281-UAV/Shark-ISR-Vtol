"use client";

import { useAnimationFrame } from "motion/react";
import { useRef } from "react";

/**
 * Live radar backdrop for the hero. A beam sweeps at 1 rev / 14 s; contacts
 * flare as the beam passes and fade until the next pass. The visitor's cursor
 * is itself a contact — after the beam sweeps it twice it gets "classified".
 * Pure DOM, updated imperatively (no per-frame React renders).
 */

const CONTACTS = [
  { r: 0.36, deg: 42, label: "CONTACT · GULL" },
  { r: 0.46, deg: 152, label: "CONTACT · SHARK 0.91" },
  { r: 0.27, deg: 268, label: "CONTACT · VESSEL" },
];

const SWEEP_S = 14;

export default function Radar({
  pointerPx,
  frozen,
}: {
  pointerPx: React.RefObject<{ x: number; y: number } | null>;
  frozen: boolean;
}) {
  const ring = useRef<HTMLDivElement>(null);
  const beam = useRef<HTMLDivElement>(null);
  const dots = useRef<(HTMLDivElement | null)[]>([]);
  const user = useRef<HTMLDivElement>(null);
  const userLabel = useRef<HTMLSpanElement>(null);
  const userSweeps = useRef(0);
  const lastUserD = useRef(999);

  useAnimationFrame((t) => {
    if (document.hidden) return; // SITE_UPGRADE 3D rule
    if (frozen || !ring.current || !beam.current) return;
    const beamDeg = ((t / 1000) * (360 / SWEEP_S)) % 360;
    beam.current.style.transform = `rotate(${beamDeg}deg)`;

    // trailing-glow intensity: bright just after the beam passes, then decays
    const glow = (deg: number) => {
      const d = (beamDeg - deg + 360) % 360;
      return Math.max(0, 1 - d / 55);
    };

    CONTACTS.forEach((c, i) => {
      const el = dots.current[i];
      if (el) el.style.opacity = String(0.15 + 0.85 * glow(c.deg));
    });

    // visitor cursor as a contact
    const p = pointerPx.current;
    const rect = ring.current.getBoundingClientRect();
    if (p && user.current) {
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      const dx = p.x - cx;
      const dy = p.y - cy;
      const dist = Math.hypot(dx, dy);
      const inside = dist < rect.width / 2 && dist > 30;
      user.current.style.display = inside ? "block" : "none";
      if (inside) {
        user.current.style.left = `${p.x - rect.left}px`;
        user.current.style.top = `${p.y - rect.top}px`;
        const deg = ((Math.atan2(dy, dx) * 180) / Math.PI + 360) % 360;
        const d = (beamDeg - deg + 360) % 360;
        // count a sweep each time the beam crosses the cursor bearing
        if (d < lastUserD.current - 180) userSweeps.current += 1;
        lastUserD.current = d;
        user.current.style.opacity = String(0.25 + 0.75 * Math.max(0, 1 - d / 55));
        if (userLabel.current) {
          const classified = userSweeps.current >= 2;
          userLabel.current.textContent =
            userSweeps.current === 0
              ? "NEW CONTACT"
              : userSweeps.current === 1
                ? "CLASSIFYING…"
                : "SHARK 0.93 · TRACK";
          // classified = TRACK state → amber per the state token system
          userLabel.current.style.color = classified ? "#e8a33d" : "";
        }
      }
    }
  });

  return (
    <div
      aria-hidden
      ref={ring}
      className="absolute left-1/2 top-1/2 h-[86vmin] w-[86vmin] -translate-x-1/2 -translate-y-1/2"
    >
      {/* range rings */}
      <div className="absolute inset-0 rounded-full border border-lined" />
      <div className="absolute inset-[18%] rounded-full border border-lined" />
      <div className="absolute inset-[36%] rounded-full border border-lined" />
      {/* bearing cross-hairs */}
      <div className="absolute left-1/2 top-0 h-full w-px -translate-x-1/2 bg-lined opacity-50" />
      <div className="absolute left-0 top-1/2 h-px w-full -translate-y-1/2 bg-lined opacity-50" />

      {/* beam */}
      <div
        ref={beam}
        className="absolute inset-0 rounded-full opacity-[0.10]"
        style={{
          background:
            "conic-gradient(from 0deg, #45b8ac 0deg, transparent 55deg, transparent 360deg)",
        }}
      />

      {/* fixed contacts */}
      {CONTACTS.map((c, i) => {
        const x = 50 + c.r * 50 * Math.cos((c.deg * Math.PI) / 180);
        const y = 50 + c.r * 50 * Math.sin((c.deg * Math.PI) / 180);
        return (
          <div
            key={c.label}
            ref={(el) => {
              dots.current[i] = el;
            }}
            className="absolute"
            style={{ left: `${x}%`, top: `${y}%`, opacity: 0.15 }}
          >
            <span className="block h-1.5 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-search" />
            <span className="absolute left-2 top-0 whitespace-nowrap font-mono text-[9px] tracking-widest text-search/80">
              {c.label}
            </span>
          </div>
        );
      })}

      {/* visitor contact */}
      <div ref={user} className="absolute hidden" style={{ opacity: 0 }}>
        <span className="block h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full border border-search bg-search/60" />
        <span
          ref={userLabel}
          className="absolute left-2.5 top-0 whitespace-nowrap font-mono text-[9px] tracking-widest text-search"
        />
      </div>
    </div>
  );
}
