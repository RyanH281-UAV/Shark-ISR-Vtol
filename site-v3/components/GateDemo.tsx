"use client";

import * as React from "react";
import { Reveal } from "./Reveal";
import {
  TAU,
  K_SUSTAIN,
  GAIN,
  DECAY,
  LOST,
  TICK_MS,
  STATE_COLOR,
  clamp,
  type State,
} from "@/lib/guidance";

/*
 * In-browser illustration of the confidence gate (ADR-016). Not flight data —
 * a faithful model of the decision: confidence accumulates across detection
 * frames, decays on misses, and only a sustained crossing of threshold τ
 * flies the aircraft SEARCH → TRACK. The constants mirror the flight code
 * (confidence_gate.py / guidance.yaml) — same rule, same numbers.
 */

const STATES: { id: State; desc: string }[] = [
  { id: "TRANSIT", desc: "Cruise to the patrol area on best-L/D." },
  { id: "SEARCH", desc: "Persistent patrol; evidence accumulates, one frame never commits." },
  { id: "TRACK", desc: "Sustained τ crossing → orbit-to-observe, geolocated fixes logged." },
  { id: "RTL", desc: "Link, compute or battery loss → autopilot-handled return." },
];

type LogLine = { kind: "sys" | "det" | "rtl"; msg: string };

export default function GateDemo() {
  const [running, setRunning] = React.useState(true);
  const [state, setState] = React.useState<State>("TRANSIT");
  const [conf, setConf] = React.useState(0);
  const [log, setLog] = React.useState<LogLine[]>([
    { kind: "sys", msg: "armed · offboard control accepted" },
  ]);

  const sim = React.useRef({
    state: "TRANSIT" as State,
    conf: 0,
    sustain: 0,
    transit: 0,
    inFrame: false,
    frame: 0,
    forceDetect: 0,
    linkLossAt: 600 + Math.floor(Math.random() * 400),
  });

  const pushLog = React.useCallback((kind: LogLine["kind"], msg: string) => {
    setLog((l) => [...l.slice(-6), { kind, msg }]);
  }, []);

  React.useEffect(() => {
    if (!running) return;
    const id = setInterval(() => {
      const s = sim.current;
      s.frame++;

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
            pushLog("sys", "on station · begin persistent patrol");
          }
          break;

        case "SEARCH": {
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
              pushLog("det", `τ sustained ${K_SUSTAIN} ticks → TRACK · orbit-on-detect`);
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
            pushLog("sys", "track lost · resume patrol");
          }
          setConf(s.conf);
          break;
        }

        case "RTL":
          s.conf = clamp(s.conf - 0.04);
          setConf(s.conf);
          if (s.frame > s.linkLossAt + 40) {
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
    sim.current.forceDetect = 12;
    pushLog("det", "operator: target injected into frame");
  };

  return (
    <section id="gate" className="bg-navy">
      <div className="mx-auto max-w-6xl px-6 py-28">
        <Reveal className="mb-10 max-w-2xl">
          <p className="mb-3 font-mono text-xs tracking-[0.3em] text-search">
            ADR-016 · SAME RULE AS THE AIRCRAFT
          </p>
          <h2 className="font-display text-4xl font-semibold uppercase leading-[0.95] tracking-tight text-fgd sm:text-5xl">
            Try to fool the gate
          </h2>
          <p className="mt-4 leading-relaxed text-muted">
            This runs the flight code&apos;s decision rule with the flight
            code&apos;s constants (τ={TAU}, K={K_SUSTAIN}). Inject a detection —
            a single frame spikes the score and dies. Only sustained evidence
            transitions the aircraft.
          </p>
        </Reveal>

        <Reveal delay={0.1}>
          <div className="grid gap-px overflow-hidden rounded border border-lined bg-lined lg:grid-cols-[1.4fr_1fr]">
            {/* state chips + gauge + controls */}
            <div className="bg-navy-2 p-7">
              <div className="flex flex-wrap items-center gap-2">
                {STATES.map((st, i) => (
                  <React.Fragment key={st.id}>
                    <span
                      className="rounded border px-3 py-1.5 font-mono text-xs tracking-wider transition-colors duration-200"
                      style={
                        state === st.id
                          ? {
                              background: STATE_COLOR[st.id],
                              borderColor: STATE_COLOR[st.id],
                              color: "#0b1e33",
                            }
                          : { borderColor: "rgba(150,170,190,0.25)", color: "#93a7ba" }
                      }
                    >
                      {st.id}
                    </span>
                    {i < STATES.length - 1 && (
                      <span className="font-mono text-muted">›</span>
                    )}
                  </React.Fragment>
                ))}
              </div>

              <p className="mt-4 min-h-10 max-w-md text-sm leading-relaxed text-muted">
                {STATES.find((s) => s.id === state)?.desc}
              </p>

              <div className="mt-6">
                <div className="flex items-baseline justify-between font-mono text-xs text-muted">
                  <span>detection confidence</span>
                  <span className="text-fgd">{conf.toFixed(2)}</span>
                </div>
                <div className="relative mt-2 h-3 overflow-hidden rounded border border-lined bg-navy">
                  <div
                    className="h-full transition-[width] duration-100"
                    style={{
                      width: `${conf * 100}%`,
                      background:
                        conf >= TAU ? STATE_COLOR.TRACK : STATE_COLOR.SEARCH,
                    }}
                  />
                  <div
                    className="absolute inset-y-0 w-px bg-fgd/80"
                    style={{ left: `${TAU * 100}%` }}
                  >
                    <span className="absolute -top-5 left-1/2 -translate-x-1/2 font-mono text-[0.6rem] text-fgd">
                      τ {TAU}
                    </span>
                  </div>
                </div>
              </div>

              <div className="mt-7 flex flex-wrap gap-3">
                <button
                  onClick={inject}
                  className="cursor-pointer rounded bg-search px-5 py-2.5 font-mono text-xs font-medium tracking-wider text-navy transition-colors duration-200 hover:bg-search/85"
                >
                  INJECT DETECTION
                </button>
                <button
                  onClick={() => setRunning((r) => !r)}
                  className="cursor-pointer rounded border border-lined px-5 py-2.5 font-mono text-xs tracking-wider text-fgd transition-colors duration-200 hover:border-search/60 hover:text-search"
                >
                  {running ? "PAUSE" : "RUN"}
                </button>
              </div>
            </div>

            {/* live log */}
            <div className="relative bg-navy p-6 scanlines">
              <div className="mb-3 flex items-center gap-2 border-b border-lined pb-2">
                <span className="inline-block h-1.5 w-1.5 rounded-full bg-search" />
                <span className="font-mono text-[0.62rem] uppercase tracking-[0.18em] text-muted">
                  guidance/log · live
                </span>
              </div>
              <div className="flex h-56 flex-col justify-end gap-1.5 overflow-hidden font-mono text-[0.72rem] leading-relaxed">
                {log.map((l, i) => (
                  <div
                    key={i}
                    className="truncate"
                    style={{
                      color:
                        l.kind === "det"
                          ? STATE_COLOR.TRACK
                          : l.kind === "rtl"
                            ? STATE_COLOR.RTL
                            : STATE_COLOR.SEARCH,
                    }}
                  >
                    <span className="text-muted">›</span> {l.msg}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
