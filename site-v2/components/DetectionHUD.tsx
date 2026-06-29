'use client'

import { motion } from "framer-motion";
import { K_SUSTAIN, TAU, STATE_COLOR, type State } from "@/lib/guidance";
import type { Telemetry } from "@/components/3d/MissionCanvasPro";

const MONO = { fontFamily: "var(--font-plex-mono), monospace" } as const;

// The perception math that drives SCAN → TRACK, surfaced as a ground-station HUD.
// τ gate, the confidence integrator, the K_SUSTAIN counter, and the geolocation
// output — all read live from the same sim that flies the drone.
export default function DetectionHUD({
  t,
  variant = "panel",
}: {
  t: Telemetry;
  variant?: "panel" | "rail";
}) {
  const confPct = Math.round(t.conf * 100);
  const tauPct = Math.round(TAU * 100);
  const crossed = t.conf >= TAU;
  const barColor = crossed ? STATE_COLOR.TRACK : STATE_COLOR.SCAN;
  const active = t.state === "SCAN" || t.state === "TRACK";

  return (
    <div
      style={MONO}
      className={`pointer-events-none select-none text-[#C6D3DC] ${
        variant === "rail" ? "w-full" : "w-[320px] max-w-[86vw]"
      }`}
    >
      <div className="rounded-lg border border-[#1C2933] bg-[#0A0F14]/85 p-4 backdrop-blur-sm">
        {/* header */}
        <div className="flex items-center justify-between">
          <span className="text-[0.6rem] uppercase tracking-[0.18em] text-[#7B8C99]">
            Onboard perception
          </span>
          <span
            className="rounded border px-1.5 py-0.5 text-[0.58rem] uppercase tracking-wider"
            style={{ borderColor: STATE_COLOR[t.state], color: STATE_COLOR[t.state] }}
          >
            {t.state}
          </span>
        </div>
        <div className="mt-1 text-[0.62rem] text-[#7B8C99]">
          yolov8n → .hef · Hailo-8L · 640 px · 10 Hz
        </div>

        {/* confidence integrator vs τ */}
        <div className="mt-4">
          <div className="flex items-baseline justify-between">
            <span className="text-[0.6rem] uppercase tracking-wider text-[#7B8C99]">
              confidence
            </span>
            <span
              className="text-sm font-bold tabular-nums"
              style={{ color: barColor }}
            >
              {t.conf.toFixed(2)}
            </span>
          </div>
          <div className="relative mt-1.5 h-2 w-full overflow-hidden rounded-full bg-[#101820]">
            <motion.div
              className="absolute inset-y-0 left-0 rounded-full"
              style={{ background: barColor }}
              animate={{ width: `${confPct}%` }}
              transition={{ type: "spring", stiffness: 200, damping: 30 }}
            />
            {/* τ marker */}
            <div
              className="absolute inset-y-0 w-px bg-[#E9F0F4]"
              style={{ left: `${tauPct}%` }}
            />
            <div
              className="absolute -top-0.5 text-[0.5rem] text-[#E9F0F4]"
              style={{ left: `calc(${tauPct}% + 3px)` }}
            >
              τ
            </div>
          </div>
          <div className="mt-1.5 text-[0.58rem] leading-tight text-[#7B8C99]">
            C ← clamp(C + 0.12·hit − 0.05·miss)
          </div>
        </div>

        {/* K_SUSTAIN counter */}
        <div className="mt-3 flex items-center justify-between">
          <span className="text-[0.6rem] uppercase tracking-wider text-[#7B8C99]">
            sustain ≥ τ
          </span>
          <div className="flex gap-1">
            {Array.from({ length: K_SUSTAIN }).map((_, i) => (
              <span
                key={i}
                className="h-2 w-2 rounded-sm transition-colors"
                style={{
                  background: i < t.sustain ? STATE_COLOR.TRACK : "#1C2933",
                }}
              />
            ))}
          </div>
        </div>
        <div className="mt-1 text-[0.58rem] text-[#7B8C99]">
          {t.sustain}/{K_SUSTAIN} frames · one lucky frame never commits
        </div>

        {/* geolocation — appears on TRACK */}
        <div className="mt-3 border-t border-[#1C2933] pt-3">
          <div className="text-[0.6rem] uppercase tracking-wider text-[#7B8C99]">
            geolocation
          </div>
          {t.geoloc ? (
            <div className="mt-1">
              <div className="text-xs tabular-nums text-[#E9F0F4]">
                {t.geoloc.lat.toFixed(5)}, {t.geoloc.lon.toFixed(5)}
              </div>
              <div className="text-[0.55rem] text-[#7B8C99]">
                pixel + attitude + 30 m AGL → WGS-84 · modelled
              </div>
            </div>
          ) : (
            <div className="mt-1 text-[0.62rem] text-[#7B8C99]/60">
              {active ? "awaiting τ-sustained lock…" : "— no contact —"}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
