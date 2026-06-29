'use client'

import { useEffect, useRef } from "react";
import { TAU, type State } from "@/lib/guidance";
import type { Telemetry } from "@/components/3d/MissionCanvasPro";

const MONO = { fontFamily: "var(--font-plex-mono), monospace" } as const;

// "What the detector sees" — a drone's-eye 2D inset. A moving aerial water
// frame; when a candidate is under inspection the YOLO box draws on and the
// confidence label rises with the integrator. Driven by the same telemetry.
export default function SensorPiP({ t }: { t: Telemetry }) {
  const cv = useRef<HTMLCanvasElement>(null);
  const tel = useRef<Telemetry>(t);
  tel.current = t;

  useEffect(() => {
    const c = cv.current;
    if (!c) return;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const W = (c.width = 240);
    const H = (c.height = 168);
    let raf = 0;
    let start = performance.now();

    const draw = (now: number) => {
      const time = (now - start) / 1000;
      const s = tel.current;

      // aerial water backdrop — drifting bands of teal/navy
      ctx.fillStyle = "#0B141B";
      ctx.fillRect(0, 0, W, H);
      const drift = reduce ? 0 : (time * 14) % 24;
      for (let y = -24; y < H + 24; y += 24) {
        const shade = 12 + ((y / 24) % 2 === 0 ? 6 : 0);
        ctx.fillStyle = `rgb(${shade},${shade + 12},${shade + 18})`;
        ctx.globalAlpha = 0.5;
        ctx.fillRect(0, y + drift, W, 12);
      }
      ctx.globalAlpha = 1;

      // reticle corners
      ctx.strokeStyle = "#2A3A47";
      ctx.lineWidth = 1;
      const m = 10,
        L = 14;
      const corners: [number, number, number, number][] = [
        [m, m, 1, 1],
        [W - m, m, -1, 1],
        [m, H - m, 1, -1],
        [W - m, H - m, -1, -1],
      ];
      corners.forEach(([x, y, dx, dy]) => {
        ctx.beginPath();
        ctx.moveTo(x, y + dy * L);
        ctx.lineTo(x, y);
        ctx.lineTo(x + dx * L, y);
        ctx.stroke();
      });

      // detection box when inspecting / tracking
      const scanning = s.state === "SCAN" || s.state === "TRACK";
      if (scanning) {
        const cx = W * 0.58;
        const cy = H * 0.5;
        // box tightens as confidence rises
        const fill = Math.min(s.conf / TAU, 1);
        const bw = 64 - fill * 14;
        const bh = 46 - fill * 10;
        const locked = s.state === "TRACK";
        const col = locked ? "#E8A33D" : "#3FA7D6";

        // dashed while scanning, solid when locked
        ctx.strokeStyle = col;
        ctx.lineWidth = locked ? 2 : 1.5;
        ctx.setLineDash(locked ? [] : [5, 4]);
        ctx.lineDashOffset = reduce ? 0 : -time * 18;
        ctx.strokeRect(cx - bw / 2, cy - bh / 2, bw, bh);
        ctx.setLineDash([]);

        // shark blob inside
        ctx.fillStyle = "rgba(8,16,22,0.65)";
        ctx.beginPath();
        ctx.ellipse(cx, cy, bw * 0.28, bh * 0.18, 0.4, 0, Math.PI * 2);
        ctx.fill();

        // label
        ctx.fillStyle = col;
        ctx.font = "10px ui-monospace, monospace";
        const label = `shark ${s.conf.toFixed(2)}`;
        const tw = ctx.measureText(label).width;
        ctx.fillRect(cx - bw / 2, cy - bh / 2 - 13, tw + 8, 13);
        ctx.fillStyle = "#0A0F14";
        ctx.fillText(label, cx - bw / 2 + 4, cy - bh / 2 - 3);
      }

      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, []);

  return (
    <div style={MONO} className="pointer-events-none select-none">
      <div className="overflow-hidden rounded-lg border border-[#1C2933] bg-[#0A0F14]/85 backdrop-blur-sm">
        <div className="flex items-center justify-between border-b border-[#1C2933] px-2.5 py-1">
          <span className="text-[0.55rem] uppercase tracking-[0.16em] text-[#7B8C99]">
            Sensor feed · modelled
          </span>
          <span className="h-1.5 w-1.5 rounded-full bg-[#45B8AC]" />
        </div>
        <canvas ref={cv} className="block h-[168px] w-[240px]" />
      </div>
    </div>
  );
}
