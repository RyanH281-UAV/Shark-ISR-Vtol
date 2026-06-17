"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import {
  TAU,
  K_SUSTAIN,
  GAIN,
  DECAY,
  LOST,
  TICK_MS,
  clamp,
  type State,
} from "@/lib/guidance";

/*
 * In-browser illustration of the guidance state machine. Not flight data —
 * a faithful model of the *decision*: confidence accumulates across detection
 * frames, decays on misses, and only a sustained crossing of threshold τ
 * flies the aircraft SEARCH → TRACK. One lucky frame never transitions.
 *
 * The decision constants live in lib/guidance.ts so the 3D MissionCanvas
 * shares the exact same rule. Tune them there.
 */

const STATES: { id: State; color: string; desc: string }[] = [
  { id: "TRANSIT", color: "var(--color-transit)", desc: "Cruise to patrol area on best-L/D." },
  { id: "SEARCH", color: "var(--color-search)", desc: "Bayesian coverage; steer to max expected detection gain." },
  { id: "TRACK", color: "var(--color-track)", desc: "Sustained τ crossing → orbit-to-observe, log geolocated detection." },
  { id: "RTL", color: "var(--color-rtl)", desc: "Link/compute/battery loss → autopilot-handled return." },
];

type LogLine = { t: number; kind: "sys" | "det" | "rtl"; msg: string };

export function AutonomyLoop() {
  const [running, setRunning] = React.useState(true);
  const [state, setState] = React.useState<State>("TRANSIT");
  const [conf, setConf] = React.useState(0);
  const [log, setLog] = React.useState<LogLine[]>([
    { t: 0, kind: "sys", msg: "armed · offboard control accepted" },
  ]);

  // mutable sim memory the interval reads/writes without re-subscribing
  const sim = React.useRef({
    state: "TRANSIT" as State,
    conf: 0,
    sustain: 0,
    transit: 0,
    inFrame: false, // is a target currently in the camera frame
    frame: 0,
    forceDetect: 0, // user-injected detection frames
    linkLossAt: 600 + Math.floor(Math.random() * 400),
  });

  const pushLog = React.useCallback((kind: LogLine["kind"], msg: string) => {
    setLog((l) => [...l.slice(-7), { t: Date.now(), kind, msg }]);
  }, []);

  React.useEffect(() => {
    if (!running) return;
    const id = setInterval(() => {
      const s = sim.current;
      s.frame++;

      // rare link loss anywhere → RTL, then recover
      if (s.frame === s.linkLossAt && s.state !== "RTL") {
        s.state = "RTL";
        setState("RTL");
        pushLog("rtl", "link loss > 3 s · degrading to autopilot RTL");
      }

      switch (s.state) {
        case "TRANSIT":
          s.transit++;
          if (s.transit > 18) {
            s.state = "SEARCH";
            setState("SEARCH");
            pushLog("sys", "on station · begin Bayesian search");
          }
          break;

        case "SEARCH": {
          // target drifts in and out of frame; user can force frames
          if (s.forceDetect > 0) {
            s.inFrame = true;
            s.forceDetect--;
          } else if (Math.random() < 0.04) {
            s.inFrame = !s.inFrame;
          }
          const hit = s.inFrame && Math.random() < 0.85;
          s.conf = clamp(s.conf + (hit ? GAIN : -DECAY));
          if (s.conf >= TAU) {
            s.sustain++;
            if (s.sustain >= K_SUSTAIN) {
              s.state = "TRACK";
              setState("TRACK");
              pushLog("det", `τ sustained ${K_SUSTAIN} frames → TRACK · orbit-on-detect`);
            }
          } else {
            s.sustain = 0;
          }
          setConf(s.conf);
          break;
        }

        case "TRACK": {
          const hit = Math.random() < 0.8;
          s.conf = clamp(s.conf + (hit ? 0.04 : -0.06));
          if (s.conf < LOST) {
            s.state = "SEARCH";
            s.sustain = 0;
            setState("SEARCH");
            pushLog("sys", "track lost · resume search");
          }
          setConf(s.conf);
          break;
        }

        case "RTL":
          s.conf = clamp(s.conf - 0.04);
          setConf(s.conf);
          if (s.frame > s.linkLossAt + 40) {
            // recover: restart the scenario
            s.state = "TRANSIT";
            s.transit = 0;
            s.sustain = 0;
            s.conf = 0;
            s.inFrame = false;
            s.linkLossAt = s.frame + 600 + Math.floor(Math.random() * 400);
            setState("TRANSIT");
            pushLog("sys", "link restored · re-transit to area");
          }
          break;
      }
    }, TICK_MS);
    return () => clearInterval(id);
  }, [running, pushLog]);

  const inject = () => {
    sim.current.forceDetect = 8;
    pushLog("det", "operator: target injected into frame");
  };

  const reset = () => {
    sim.current = {
      ...sim.current,
      state: "TRANSIT",
      conf: 0,
      sustain: 0,
      transit: 0,
      inFrame: false,
      frame: 0,
      forceDetect: 0,
      linkLossAt: 600 + Math.floor(Math.random() * 400),
    };
    setState("TRANSIT");
    setConf(0);
    setLog([{ t: 0, kind: "sys", msg: "reset · armed" }]);
  };

  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_320px]">
      {/* state graph + gauge */}
      <div className="rounded-sm border border-line bg-surface p-6">
        <div className="flex flex-wrap items-center gap-2">
          {STATES.map((st, i) => (
            <React.Fragment key={st.id}>
              <div
                className={cn(
                  "rounded-md border px-3 py-2 font-mono text-xs tracking-wide transition-all duration-200",
                  state === st.id
                    ? "text-white shadow-sm"
                    : "border-line text-faint"
                )}
                style={
                  state === st.id
                    ? { background: st.color, borderColor: st.color }
                    : undefined
                }
              >
                {st.id}
              </div>
              {i < STATES.length - 1 && (
                <span className="font-mono text-faint">›</span>
              )}
            </React.Fragment>
          ))}
        </div>

        <p className="mt-4 min-h-[2.5rem] max-w-md text-sm leading-relaxed text-secondary">
          {STATES.find((s) => s.id === state)?.desc}
        </p>

        {/* confidence gauge */}
        <div className="mt-6">
          <div className="flex items-baseline justify-between font-mono text-xs text-faint">
            <span>detection confidence</span>
            <span className="text-ink">{conf.toFixed(2)}</span>
          </div>
          <div className="relative mt-2 h-3 overflow-hidden rounded border border-line2 bg-bg">
            <div
              className="h-full transition-[width] duration-100"
              style={{
                width: `${conf * 100}%`,
                background: conf >= TAU ? "var(--color-track)" : "var(--color-accent)",
              }}
            />
            {/* τ marker */}
            <div
              className="absolute inset-y-0 w-px bg-ink"
              style={{ left: `${TAU * 100}%` }}
            >
              <span className="absolute -top-5 left-1/2 -translate-x-1/2 font-mono text-[0.6rem] text-ink">
                τ {TAU}
              </span>
            </div>
          </div>
        </div>

        <div className="mt-6 flex flex-wrap gap-2">
          <button
            onClick={() => setRunning((r) => !r)}
            className="cursor-pointer rounded-md border border-line2 bg-surface px-4 py-2 font-mono text-xs uppercase tracking-wider text-primary transition-colors hover:border-faint"
          >
            {running ? "Pause" : "Run"}
          </button>
          <button
            onClick={inject}
            className="cursor-pointer rounded-md border border-accent bg-accent px-4 py-2 font-mono text-xs uppercase tracking-wider text-white transition-colors hover:bg-blue-700"
          >
            Inject detection
          </button>
          <button
            onClick={reset}
            className="cursor-pointer rounded-md border border-line2 bg-surface px-4 py-2 font-mono text-xs uppercase tracking-wider text-primary transition-colors hover:border-faint"
          >
            Reset
          </button>
        </div>
      </div>

      {/* live log */}
      <div className="rounded-sm border border-line bg-[#0c1218] p-4">
        <div className="mb-3 flex items-center gap-2 border-b border-white/10 pb-2">
          <span className="pulse-dot inline-block h-1.5 w-1.5 rounded-full bg-green-400" />
          <span className="font-mono text-[0.62rem] uppercase tracking-[0.18em] text-slate-400">
            guidance/log · live
          </span>
        </div>
        <div className="flex h-[260px] flex-col justify-end gap-1.5 overflow-hidden font-mono text-[0.72rem] leading-relaxed">
          {log.map((l, i) => (
            <div
              key={i}
              className={cn(
                "truncate",
                l.kind === "det" && "text-amber-400",
                l.kind === "sys" && "text-teal-300",
                l.kind === "rtl" && "text-red-400"
              )}
            >
              <span className="text-slate-600">›</span> {l.msg}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
