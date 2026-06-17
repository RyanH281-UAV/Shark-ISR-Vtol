'use client'

import { Component, ReactNode, useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { AnimatePresence, motion, useInView, useReducedMotion } from "framer-motion";
import AuroraBackground from "@/components/ui/AuroraBackground";
import { STATE_COLOR, type State } from "@/lib/guidance";
import { useInViewport } from "@/lib/useInViewport";

const MissionCanvas = dynamic(() => import("./MissionCanvas"), {
  ssr: false,
  loading: () => <div className="h-full w-full animate-pulse bg-[#101820]" />,
});

const STATES: State[] = ["TRANSIT", "SEARCH", "SCAN", "TRACK"];

// "how it was achieved" — one line per state, surfaced as the active state changes
const CAPTION: Record<State, { how: string; detail: string }> = {
  TRANSIT: { how: "Transit", detail: "Cruise to the patrol area on best-L/D." },
  SEARCH: { how: "Bayesian search", detail: "Probability grid · steer to maximum expected detection gain, not a lawnmower." },
  SCAN: { how: "Confidence gate", detail: "Close in to inspect · confidence must clear τ for K_SUSTAIN frames. One lucky frame never commits." },
  TRACK: { how: "Orbit-to-observe", detail: "Sustained τ crossing → orbit the contact, geolocate, log the detection." },
  RTL: { how: "Return", detail: "Link / compute / battery loss → autopilot-handled return." },
};

const H2 = "The search pattern, from above.";

// ── render/WebGL fallback boundary ──────────────────────────────────────
class CanvasBoundary extends Component<
  { children: ReactNode; fallback: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

function StaticFallback() {
  return (
    <div className="flex h-full w-full items-center justify-center p-8 text-center">
      <p
        style={{ fontFamily: "var(--font-plex-mono), monospace" }}
        className="max-w-sm text-xs leading-relaxed text-[#7B8C99]"
      >
        3D mission view needs WebGL. The model: a lawnmower search over a
        Bayesian probability grid; a sustained τ crossing transitions SEARCH →
        TRACK and the aircraft orbits the detection.
      </p>
    </div>
  );
}

function StateChips({ active }: { active: State }) {
  return (
    <div className="flex flex-wrap gap-2">
      {STATES.map((s) => {
        const on = s === active;
        return (
          <span
            key={s}
            style={{
              fontFamily: "var(--font-plex-mono), monospace",
              borderColor: on ? STATE_COLOR[s] : "#1C2933",
              background: on ? STATE_COLOR[s] : "transparent",
              color: on ? "#0A0F14" : "#7B8C99",
            }}
            className="rounded-md border px-2.5 py-1 text-[0.65rem] uppercase tracking-wider transition-colors"
          >
            {s}
          </span>
        );
      })}
    </div>
  );
}

export default function MissionSection3D() {
  const [active, setActive] = useState<State>("TRANSIT");
  const [webgl, setWebgl] = useState<boolean | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const sectionRef = useRef<HTMLElement>(null);
  const inView = useInView(wrapRef, { once: true });
  const onScreen = useInViewport(sectionRef); // mount Canvas only when visible
  const reduce = useReducedMotion();
  const words = H2.split(" ");

  useEffect(() => {
    try {
      const c = document.createElement("canvas");
      setWebgl(!!(c.getContext("webgl2") || c.getContext("webgl")));
    } catch {
      setWebgl(false);
    }
  }, []);

  return (
    <section
      ref={sectionRef}
      id="mission-3d"
      className="relative min-h-[100vh] bg-[#0A0F14]"
    >
      <AuroraBackground />

      {/* header */}
      <div className="absolute left-8 top-8 z-10 max-w-md">
        <div
          style={{ fontFamily: "var(--font-plex-mono), monospace" }}
          className="text-xs uppercase tracking-widest text-[#7B8C99]"
        >
          // MISSION VISUALISATION · 3D MODEL
        </div>
        <h2
          style={{
            fontFamily: "'Saira Condensed', var(--font-plex-sans), sans-serif",
            fontSize: "clamp(2rem, 5vw, 3.5rem)",
            lineHeight: 1.1,
          }}
          className="mt-2 text-[#E9F0F4]"
        >
          {words.map((w, i) => (
            <span key={`${w}-${i}`} className="inline-block whitespace-pre">
              <motion.span
                className="inline-block"
                initial={reduce ? false : { y: 20, opacity: 0 }}
                animate={reduce ? undefined : inView ? { y: 0, opacity: 1 } : undefined}
                transition={{
                  type: "spring",
                  stiffness: 100,
                  damping: 20,
                  delay: i * 0.04,
                }}
              >
                {i < words.length - 1 ? w + " " : w}
              </motion.span>
            </span>
          ))}
        </h2>
        <p
          style={{ fontFamily: "var(--font-plex-sans), sans-serif" }}
          className="mt-3 max-w-xs text-sm leading-relaxed text-[#C6D3DC]"
        >
          Watch confidence accumulate across frames. One lucky detection never
          flies the aircraft.
        </p>
      </div>

      {/* caption rail — "how it was achieved", tracks the active state */}
      <div className="pointer-events-none absolute right-8 top-8 z-10 max-w-[260px] text-right">
        <AnimatePresence mode="wait">
          <motion.div
            key={active}
            initial={reduce ? false : { opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduce ? undefined : { opacity: 0, y: -8 }}
            transition={{ duration: 0.3 }}
          >
            <div
              style={{ fontFamily: "var(--font-plex-mono), monospace", color: STATE_COLOR[active] }}
              className="text-[0.65rem] uppercase tracking-[0.2em]"
            >
              {active} · {CAPTION[active].how}
            </div>
            <p
              style={{ fontFamily: "var(--font-plex-sans), sans-serif" }}
              className="mt-1.5 text-sm leading-relaxed text-[#C6D3DC]"
            >
              {CAPTION[active].detail}
            </p>
          </motion.div>
        </AnimatePresence>
      </div>

      {/* state chips */}
      <div className="absolute bottom-4 left-4 z-10">
        <StateChips active={active} />
      </div>

      {/* canvas */}
      <motion.div
        ref={wrapRef}
        initial={reduce ? false : { opacity: 0 }}
        animate={reduce ? undefined : inView ? { opacity: 1 } : undefined}
        transition={{ duration: 0.8 }}
        className="absolute inset-0"
      >
        {webgl === false ? (
          <StaticFallback />
        ) : webgl && onScreen ? (
          <CanvasBoundary fallback={<StaticFallback />}>
            <MissionCanvas onState={setActive} />
          </CanvasBoundary>
        ) : (
          <div className="h-full w-full animate-pulse bg-[#101820]" />
        )}
      </motion.div>
    </section>
  );
}
