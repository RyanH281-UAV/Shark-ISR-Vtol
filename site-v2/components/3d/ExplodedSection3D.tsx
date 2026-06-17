'use client'

import { Component, ReactNode, useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import AuroraBackground from "@/components/ui/AuroraBackground";
import { useInViewport } from "@/lib/useInViewport";

const ExplodedCanvas = dynamic(() => import("./ExplodedCanvas"), {
  ssr: false,
  loading: () => <div className="h-full w-full animate-pulse bg-[#101820]" />,
});

type Phase = 1 | 2 | 3;

const PHASE_COPY: Record<Phase, { eyebrow: string; title: string }> = {
  1: { eyebrow: "// AIRFRAME · 1.1 M WINGSPAN TRI-TILTROTOR", title: "One aircraft. Eight printed assemblies." },
  2: { eyebrow: "// ELECTRONICS BAY · ISR PAYLOAD", title: "The bay that makes it autonomous." },
  3: { eyebrow: "// COMPUTE STACK · SIGNAL FLOW A → B → C → D", title: "Four nodes. No operator in the loop." },
};

// ponytail: small copy duplicate of the stack nodes — kept here so this section
// (and its no-WebGL fallback) needs zero pull from the three/drei canvas module,
// which would defeat the ssr:false dynamic split.
const STACK_INFO = [
  { id: "cam", label: "Camera Module 3", bus: "CSI-2" },
  { id: "hailo", label: "Hailo-8L AI HAT+", bus: "PCIe Gen 3" },
  { id: "pi5", label: "Raspberry Pi 5", bus: "uXRCE-DDS" },
  { id: "px4", label: "Pixhawk 6C Mini", bus: "PWM / UART" },
];

const AIRFRAME_LABELS = [
  "Fuselage — upper", "Fuselage — lower", "Port wing", "Starboard wing",
  "Tail", "Front-left nacelle", "Front-right nacelle", "Rear nacelle",
];

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
  const mono = { fontFamily: "var(--font-plex-mono), monospace" };
  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-8 px-8">
      {/* airframe row */}
      <div className="flex w-full max-w-3xl flex-wrap items-center justify-center gap-x-3 gap-y-2">
        {AIRFRAME_LABELS.map((l, i) => (
          <div key={l} className="flex items-center">
            <span style={mono} className="text-[10px] text-[#7B8C99]">{l}</span>
            {i < AIRFRAME_LABELS.length - 1 && (
              <span className="ml-3 inline-block h-px w-6 bg-[#1C2933]" />
            )}
          </div>
        ))}
      </div>
      {/* eyebrow */}
      <div style={mono} className="text-xs uppercase tracking-widest text-[#7B8C99]">
        ELECTRONICS BAY
      </div>
      {/* stack row */}
      <div className="flex w-full max-w-2xl items-center justify-between">
        {STACK_INFO.map((n, i) => (
          <div key={n.id} className="flex flex-1 items-center">
            <div className="text-center">
              <div style={mono} className="text-[11px] font-medium text-[#E9F0F4]">{n.label}</div>
              <div style={mono} className="text-[10px] text-[#7B8C99]">{n.bus}</div>
            </div>
            {i < STACK_INFO.length - 1 && (
              <div className="mx-2 h-px flex-1 bg-[#1C2933]" />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function ExplodedSection3D() {
  const sectionRef = useRef<HTMLDivElement>(null);
  const progressRef = useRef<number>(0);
  const [activePhase, setActivePhase] = useState<Phase>(1);
  const [webgl, setWebgl] = useState<boolean | null>(null);
  const onScreen = useInViewport(sectionRef); // mount Canvas only when visible
  const reduce = useReducedMotion();

  // WebGL capability probe (three throws on a lost context, async → uncatchable)
  useEffect(() => {
    try {
      const c = document.createElement("canvas");
      setWebgl(!!(c.getContext("webgl2") || c.getContext("webgl")));
    } catch {
      setWebgl(false);
    }
  }, []);

  // scroll → progressRef (no setState here — the canvas reads the ref directly)
  useEffect(() => {
    if (reduce) {
      progressRef.current = 1;
      return;
    }
    const onScroll = () => {
      const el = sectionRef.current;
      if (!el) return;
      const top = el.getBoundingClientRect().top + window.scrollY;
      const travel = el.offsetHeight - window.innerHeight;
      progressRef.current =
        travel > 0 ? Math.min(1, Math.max(0, (window.scrollY - top) / travel)) : 0;
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [reduce]);

  // rAF loop derives the discrete phase (separate from the scroll listener)
  useEffect(() => {
    let raf = 0;
    let last: Phase = 1;
    const tick = () => {
      const p = progressRef.current;
      const phase: Phase = p < 0.35 ? 1 : p < 0.65 ? 2 : 3;
      if (phase !== last) {
        last = phase;
        setActivePhase(phase);
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);

  return (
    <section ref={sectionRef} className="relative min-h-[400vh] bg-[#0A0F14]">
      <AuroraBackground />

      <div className="sticky top-0 h-screen w-full overflow-hidden">
        {webgl === false ? (
          <StaticFallback />
        ) : webgl && onScreen ? (
          <CanvasBoundary fallback={<StaticFallback />}>
            <ExplodedCanvas scrollProgress={progressRef} />
          </CanvasBoundary>
        ) : (
          <div className="h-full w-full animate-pulse bg-[#101820]" />
        )}

        {/* phase label — bottom-left */}
        <AnimatePresence mode="wait">
          <motion.div
            key={activePhase}
            initial={{ y: 16, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: -8, opacity: 0 }}
            transition={{ type: "spring", stiffness: 120, damping: 22 }}
            className="pointer-events-none absolute bottom-8 left-8 z-10 max-w-md"
          >
            <p
              style={{ fontFamily: "var(--font-plex-mono), monospace" }}
              className="mb-1 text-xs tracking-widest text-[#7B8C99]"
            >
              {PHASE_COPY[activePhase].eyebrow}
            </p>
            <h2 className="font-display text-2xl text-[#E9F0F4]">
              {PHASE_COPY[activePhase].title}
            </h2>
          </motion.div>
        </AnimatePresence>

        {/* electronics detail panel — bottom-right, phase 3 only */}
        <motion.div
          animate={{
            opacity: activePhase === 3 ? 1 : 0,
            x: activePhase === 3 ? 0 : 20,
          }}
          transition={{ duration: 0.4 }}
          className="pointer-events-none absolute bottom-8 right-8 z-10 max-w-[240px] rounded-lg border border-[#1C2933] bg-[#101820] p-4"
        >
          <div
            style={{ fontFamily: "var(--font-plex-mono), monospace" }}
            className="mb-3 text-[10px] uppercase tracking-widest text-[#7B8C99]"
          >
            Signal flow
          </div>
          <div className="flex flex-col gap-2">
            {STACK_INFO.map((n) => (
              <div key={n.id}>
                <div
                  style={{ fontFamily: "var(--font-plex-sans), sans-serif" }}
                  className="text-sm text-[#E9F0F4]"
                >
                  {n.label}
                </div>
                <div
                  style={{ fontFamily: "var(--font-plex-mono), monospace" }}
                  className="text-xs text-[#7B8C99]"
                >
                  {n.bus}
                </div>
              </div>
            ))}
          </div>
        </motion.div>

        {/* phase progress dots — right rail */}
        <div className="pointer-events-none fixed right-6 top-1/2 z-20 flex -translate-y-1/2 flex-col gap-3">
          {[1, 2, 3].map((n) => (
            <div
              key={n}
              className="h-2 w-2 rounded-full transition-colors duration-300"
              style={{ background: activePhase === n ? "#45B8AC" : "#1C2933" }}
            />
          ))}
        </div>
      </div>
    </section>
  );
}
