"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

/*
 * Interactive autonomy stack. Boards are bespoke schematic illustrations (not
 * product photos — those are copyrighted). Specs/flags sourced from the project
 * wiki + docs/HORNET_PLATFORM.md / ADR-006. Click a board to inspect it; hover
 * a bus to trace the signal.
 */

type PartId = "cam" | "hailo" | "pi" | "pixhawk" | "airframe";
type BusId = "csi" | "pcie" | "dds" | "pwm";

type Part = {
  id: PartId;
  name: string;
  role: string;
  accent: string;
  specs: string[];
  flag?: string;
  buses: BusId[];
  photo?: string;
};

const PARTS: Record<PartId, Part> = {
  cam: {
    id: "cam",
    name: "Camera Module 3",
    role: "Sony IMX708 · CSI-2",
    accent: "#38bdf8",
    specs: [
      "Standard lens (locked) · ~66° diagonal FOV",
      "Frames downscaled to 640 px model input",
      "Driven by libcamera / picamera2",
    ],
    flag: "Glare is the dominant detection killer — CPL filter planned (~$17, ~10–15 g).",
    buses: ["csi"],
  },
  hailo: {
    id: "hailo",
    name: "AI HAT+ · Hailo-8L",
    role: "NPU · 13 TOPS INT8",
    accent: "#f59e0b",
    specs: [
      "PCIe Gen 3 via the M.2 HAT+",
      "HailoRT runtime, YOLOv8s compiled to .hef",
      "Inference runs onboard — no video downlink",
    ],
    flag: "Thermal: sustained inference in a sealed LW-PLA fuselage throttles without active cooling.",
    buses: ["pcie"],
    photo: "/hardware/hailo.jpg",
  },
  pi: {
    id: "pi",
    name: "Raspberry Pi 5",
    role: "Companion computer · ROS 2 outer loop",
    accent: "#22c55e",
    specs: [
      "Hosts ROS 2, the uXRCE-DDS agent, and px4_msgs",
      "Runs all 7 ROS 2 packages (~46 g board)",
      "5 V rail must feed Pi + HAT + camera under load",
    ],
    flag: "Never in the safety-critical loop — total loss degrades to a PX4-handled RTL. LM2596S (3 A) is undersized; spec a ≥5 A buck.",
    buses: ["csi", "pcie", "dds"],
    photo: "/hardware/pi5.jpg",
  },
  pixhawk: {
    id: "pixhawk",
    name: "Pixhawk 6C Mini",
    role: "Flight controller · PX4 v1.16",
    accent: "#a78bfa",
    specs: [
      "Owns the inner loop, the tilt transition, every failsafe",
      "Tiltrotor VTOL airframe configured in QGroundControl",
      "Linked to the Pi over uXRCE-DDS (serial)",
    ],
    flag: "The sole safety-critical computer. ROS 2 can only *ask* — it cannot override a failsafe.",
    buses: ["dds", "pwm"],
    photo: "/hardware/pixhawk.png",
  },
  airframe: {
    id: "airframe",
    name: "Titan Dynamics Hornet",
    role: "Tri-tiltrotor · MTOW 2.5 kg",
    accent: "#64748b",
    specs: [
      "2 front tilt servos + fixed rear motor",
      "3× 35 A BLHeli ESC · 6S Li-ion / LiPo",
      "1.1 m span, LW-PLA fuselage",
    ],
    flag: "MTOW 2.5 kg is a hard ceiling — every gram of compute is weighed against it.",
    buses: ["pwm"],
  },
};

const BUSES: Record<BusId, { label: string; detail: string }> = {
  csi: { label: "CSI-2", detail: "IMX708 frames → libcamera" },
  pcie: { label: "PCIe Gen 3", detail: ".hef inference, onboard" },
  dds: { label: "uXRCE-DDS", detail: "offboard setpoints · VehicleCommand" },
  pwm: { label: "PWM", detail: "motors · tilt servos · surfaces" },
};

const ORDER: PartId[] = ["cam", "hailo", "pi", "pixhawk", "airframe"];

export function HardwareStack() {
  const [selected, setSelected] = React.useState<PartId>("pi");
  const [hoverBus, setHoverBus] = React.useState<BusId | null>(null);
  const part = PARTS[selected];

  const busActive = (b: BusId) =>
    hoverBus === b || part.buses.includes(b);

  return (
    <div className="grid gap-5 lg:grid-cols-[1.35fr_1fr]">
      {/* diagram */}
      <div className="relative overflow-hidden rounded-sm border border-white/10 bg-[#0a0f14] p-2">
        {/* blueprint grid */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-[0.4]"
          style={{
            backgroundImage:
              "linear-gradient(rgba(56,189,248,0.08) 1px,transparent 1px),linear-gradient(90deg,rgba(56,189,248,0.08) 1px,transparent 1px)",
            backgroundSize: "26px 26px",
          }}
        />
        <svg
          viewBox="0 0 560 640"
          className="relative w-full"
          role="img"
          aria-label="Interactive diagram of the autonomy hardware stack and the buses connecting each board."
        >
          {/* ---- connection paths ---- */}
          <Wire d="M135 124 C 135 180, 200 190, 230 250" bus="csi" active={busActive("csi")} />
          <Wire d="M430 134 C 430 190, 380 200, 350 250" bus="pcie" active={busActive("pcie")} />
          <Wire d="M210 392 C 210 420, 220 430, 230 452" bus="dds" active={busActive("dds")} />
          <Wire d="M340 512 C 380 512, 390 512, 410 512" bus="pwm" active={busActive("pwm")} />

          {/* ---- boards ---- */}
          <Board
            id="cam" x={60} y={32} w={150} h={92}
            selected={selected === "cam"} onSelect={setSelected}
          >
            <circle cx={135} cy={78} r={20} fill="none" stroke="currentColor" strokeWidth={2} />
            <circle cx={135} cy={78} r={9} fill="currentColor" opacity={0.4} />
          </Board>

          <Board
            id="hailo" x={355} y={42} w={155} h={92}
            selected={selected === "hailo"} onSelect={setSelected}
          >
            <rect x={415} y={72} width={36} height={36} rx={3} fill="currentColor" opacity={0.35} />
            <text x={433} y={94} textAnchor="middle" className="fill-current text-[8px] font-mono" opacity={0.9}>NPU</text>
          </Board>

          <Board
            id="pi" x={120} y={250} w={320} h={142}
            selected={selected === "pi"} onSelect={setSelected}
          >
            {/* 40-pin header */}
            <g opacity={0.5}>
              {Array.from({ length: 20 }).map((_, i) => (
                <rect key={i} x={150 + i * 13} y={266} width={6} height={6} rx={1} fill="currentColor" />
              ))}
            </g>
            {/* ports */}
            <rect x={150} y={350} width={40} height={22} rx={2} fill="currentColor" opacity={0.3} />
            <rect x={200} y={350} width={40} height={22} rx={2} fill="currentColor" opacity={0.3} />
            <rect x={388} y={300} width={36} height={50} rx={2} fill="currentColor" opacity={0.25} />
          </Board>

          <Board
            id="pixhawk" x={120} y={452} w={220} h={120}
            selected={selected === "pixhawk"} onSelect={setSelected}
          >
            <g opacity={0.45}>
              {Array.from({ length: 6 }).map((_, i) => (
                <rect key={i} x={150 + i * 26} y={540} width={18} height={10} rx={1} fill="currentColor" />
              ))}
            </g>
          </Board>

          <Board
            id="airframe" x={410} y={460} w={120} h={104}
            selected={selected === "airframe"} onSelect={setSelected}
          >
            <circle cx={470} cy={500} r={13} fill="none" stroke="currentColor" strokeWidth={2} opacity={0.6} />
            <line x1={470} y1={500} x2={470} y2={540} stroke="currentColor" strokeWidth={2} opacity={0.4} />
          </Board>
        </svg>
        <p className="px-2 pb-1 font-mono text-[0.58rem] leading-relaxed text-slate-600">
          Board photos: Raspberry&nbsp;Pi&nbsp;5 © SimonWaldherr · Hailo module ©
          RetroEditor · Pixhawk © Pixhawk project — CC&nbsp;BY&nbsp;4.0, via
          Wikimedia Commons. Camera &amp; airframe shown schematic.
        </p>
      </div>

      {/* detail panel */}
      <div className="flex flex-col rounded-sm border border-white/10 bg-[#0c1218] p-6">
        <div className="flex items-center gap-2 border-b border-white/10 pb-3">
          <span
            className="inline-block h-2.5 w-2.5 rounded-full"
            style={{ background: part.accent }}
          />
          <span className="font-mono text-[0.62rem] uppercase tracking-[0.18em] text-slate-400">
            {part.role}
          </span>
        </div>

        <h3 className="mt-4 font-display text-2xl font-bold text-white">
          {part.name}
        </h3>

        <ul className="mt-4 space-y-2.5">
          {part.specs.map((s) => (
            <li key={s} className="flex gap-2.5 text-sm leading-relaxed text-slate-300">
              <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full" style={{ background: part.accent }} />
              {s}
            </li>
          ))}
        </ul>

        {part.flag && (
          <div className="mt-5 rounded-lg border border-amber-500/25 bg-amber-500/5 p-3">
            <div className="font-mono text-[0.6rem] uppercase tracking-wider text-amber-400/90">
              Flag
            </div>
            <p className="mt-1 text-sm leading-relaxed text-slate-300">{part.flag}</p>
          </div>
        )}

        {/* buses for this part */}
        <div className="mt-auto pt-5">
          <div className="font-mono text-[0.6rem] uppercase tracking-wider text-slate-500">
            Connections
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            {part.buses.map((b) => (
              <span
                key={b}
                onMouseEnter={() => setHoverBus(b)}
                onMouseLeave={() => setHoverBus(null)}
                className="cursor-default rounded border border-white/15 px-2 py-1 font-mono text-[0.65rem] text-slate-300"
              >
                {BUSES[b].label}
                <span className="ml-1.5 text-slate-500">{BUSES[b].detail}</span>
              </span>
            ))}
          </div>
        </div>

        {/* quick selector */}
        <div className="mt-5 flex flex-wrap gap-1.5 border-t border-white/10 pt-4">
          {ORDER.map((id) => (
            <button
              key={id}
              onClick={() => setSelected(id)}
              className={cn(
                "cursor-pointer rounded border px-2.5 py-1 font-mono text-[0.62rem] transition-colors",
                selected === id
                  ? "border-white/40 text-white"
                  : "border-white/10 text-slate-500 hover:text-slate-300"
              )}
            >
              {PARTS[id].name.split(" ")[0]}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function Wire({ d, bus, active }: { d: string; bus: BusId; active: boolean }) {
  // midpoint label placed roughly at path center via a transparent helper
  return (
    <g className="transition-opacity">
      <path
        d={d}
        fill="none"
        stroke={active ? "#38bdf8" : "#1e2d3a"}
        strokeWidth={active ? 2.5 : 1.5}
        strokeDasharray={active ? "6 4" : undefined}
      >
        {active && (
          <animate attributeName="stroke-dashoffset" from="20" to="0" dur="0.8s" repeatCount="indefinite" />
        )}
      </path>
      <BusLabel d={d} bus={bus} active={active} />
    </g>
  );
}

// label centered on the path using getPointAtLength after mount
function BusLabel({ d, bus, active }: { d: string; bus: BusId; active: boolean }) {
  const ref = React.useRef<SVGPathElement>(null);
  const [pt, setPt] = React.useState<{ x: number; y: number } | null>(null);
  React.useEffect(() => {
    const p = ref.current;
    if (!p) return;
    const mid = p.getPointAtLength(p.getTotalLength() / 2);
    setPt({ x: mid.x, y: mid.y });
  }, [d]);
  return (
    <>
      <path ref={ref} d={d} fill="none" stroke="none" />
      {pt && (
        <g transform={`translate(${pt.x} ${pt.y})`}>
          <rect x={-26} y={-9} width={52} height={18} rx={3} fill="#0a0f14" stroke={active ? "#38bdf8" : "#1e2d3a"} strokeWidth={1} />
          <text textAnchor="middle" y={4} className="fill-current font-mono text-[9px]" style={{ color: active ? "#7dd3fc" : "#64748b" }}>
            {BUSES[bus].label}
          </text>
        </g>
      )}
    </>
  );
}

function Board({
  id, x, y, w, h, selected, onSelect, children,
}: {
  id: PartId; x: number; y: number; w: number; h: number;
  selected: boolean; onSelect: (id: PartId) => void; children?: React.ReactNode;
}) {
  const part = PARTS[id];
  const clip = `clip-${id}`;
  return (
    <g
      onClick={() => onSelect(id)}
      className="cursor-pointer"
      style={{ color: part.accent }}
      role="button"
      aria-pressed={selected}
      aria-label={`${part.name} — ${part.role}`}
      tabIndex={0}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onSelect(id)}
    >
      <defs>
        <clipPath id={clip}>
          <rect x={x} y={y} width={w} height={h} rx={6} />
        </clipPath>
      </defs>

      <rect
        x={x} y={y} width={w} height={h} rx={6}
        fill={part.photo ? "#000" : selected ? "rgba(255,255,255,0.04)" : "#0e151c"}
        stroke={selected ? part.accent : "#243341"}
        strokeWidth={selected ? 2 : 1.25}
        style={selected ? { filter: `drop-shadow(0 0 10px ${part.accent}66)` } : undefined}
        className="transition-all duration-200"
      />

      {part.photo ? (
        <>
          <image
            href={part.photo}
            x={x} y={y} width={w} height={h}
            preserveAspectRatio="xMidYMid slice"
            clipPath={`url(#${clip})`}
            opacity={selected ? 1 : 0.82}
            className="transition-opacity duration-200"
          />
          {/* label scrim */}
          <rect
            x={x} y={y + h - 26} width={w} height={26}
            fill="#0a0f14" opacity={0.78} clipPath={`url(#${clip})`}
          />
          <text x={x + 10} y={y + h - 9} className="font-mono text-[11px] font-medium" fill="#e9f0f4">
            {part.name}
          </text>
        </>
      ) : (
        <>
          <text x={x + 12} y={y + 22} className="font-mono text-[11px] font-medium" fill={selected ? part.accent : "#7b8c99"}>
            {part.name}
          </text>
          <g style={{ color: selected ? part.accent : "#46586a" }}>{children}</g>
        </>
      )}

      {/* corner tick */}
      <path d={`M${x + 8} ${y} h-8 v8`} fill="none" stroke={part.accent} strokeWidth={1.5} opacity={selected ? 1 : 0.5} />
    </g>
  );
}
