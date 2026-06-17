'use client'

import { Component, ReactNode, useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { motion, useInView } from "framer-motion";
import AuroraBackground from "@/components/ui/AuroraBackground";
import { useInViewport } from "@/lib/useInViewport";

const StackCanvas = dynamic(() => import("./StackCanvas"), {
  ssr: false,
  loading: () => (
    <div className="h-full w-full animate-pulse rounded-lg bg-[#101820]" />
  ),
});

// ── Node copy (detail panel + static fallback) ──────────────────────────
type Detail = { id: string; name: string; bus: string; desc: string };

const DETAILS: Detail[] = [
  {
    id: "A",
    name: "Camera Module 3",
    bus: "Sony IMX708 · CSI-2",
    desc: "Sony IMX708 feeds frames to the NPU via CSI-2",
  },
  {
    id: "B",
    name: "Hailo-8L AI HAT+",
    bus: "13 TOPS · PCIe Gen 3",
    desc: "13-TOPS NPU runs YOLOv8n compiled to .hef at ~30 FPS",
  },
  {
    id: "C",
    name: "Raspberry Pi 5",
    bus: "companion · uXRCE-DDS",
    desc: "Companion computer hosts the ROS 2 guidance state machine",
  },
  {
    id: "D",
    name: "Pixhawk 6C Mini",
    bus: "autopilot · PWM",
    desc: "PX4 autopilot executes setpoints; owns all safety failsafes",
  },
];

// ── WebGL / render fallback boundary ────────────────────────────────────
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
    <div className="flex h-full w-full items-center justify-center px-4">
      <div className="flex w-full max-w-2xl items-center justify-between">
        {DETAILS.map((d, i) => (
          <div key={d.id} className="flex flex-1 items-center">
            <div className="text-center">
              <div
                style={{ fontFamily: "var(--font-plex-mono), monospace" }}
                className="text-[11px] font-medium text-[#E9F0F4]"
              >
                {d.name}
              </div>
              <div
                style={{ fontFamily: "var(--font-plex-mono), monospace" }}
                className="text-[10px] text-[#7B8C99]"
              >
                {d.bus}
              </div>
            </div>
            {i < DETAILS.length - 1 && (
              <div className="mx-2 h-px flex-1 bg-[#1C2933]" />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function DetailPanel({ selected }: { selected: string | null }) {
  const node = DETAILS.find((d) => d.id === selected) ?? null;
  return (
    <motion.div
      key={node?.id ?? "none"}
      initial={{ x: 20, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      transition={{ duration: 0.4, ease: [0.25, 0.1, 0.25, 1] }}
      className="static mt-4 w-full rounded-lg border border-[#1C2933] bg-[#101820] p-4 md:absolute md:right-4 md:top-4 md:mt-0 md:w-64"
    >
      {node ? (
        <>
          <div
            style={{ fontFamily: "'Saira Condensed', var(--font-plex-sans), sans-serif" }}
            className="text-lg text-[#E9F0F4]"
          >
            {node.name}
          </div>
          <div
            style={{ fontFamily: "var(--font-plex-mono), monospace" }}
            className="mb-3 text-xs text-[#7B8C99]"
          >
            {node.bus}
          </div>
          <p
            style={{ fontFamily: "var(--font-plex-sans), sans-serif" }}
            className="text-sm leading-relaxed text-[#C6D3DC]"
          >
            {node.desc}
          </p>
        </>
      ) : (
        <div
          style={{ fontFamily: "var(--font-plex-mono), monospace" }}
          className="text-xs text-[#7B8C99]"
        >
          Select a node to inspect
        </div>
      )}
    </motion.div>
  );
}

export default function StackSection3D() {
  const [selected, setSelected] = useState<string | null>(null);
  // null = probing, then true/false. three throws on null WebGL context, and
  // that throw is async (outside render) so an ErrorBoundary can't catch it —
  // probe up front and fall back to the static diagram if WebGL is missing.
  const [webgl, setWebgl] = useState<boolean | null>(null);
  const headRef = useRef<HTMLDivElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const inView = useInView(headRef, { once: true });
  const onScreen = useInViewport(rootRef); // mount Canvas only when visible

  useEffect(() => {
    try {
      const c = document.createElement("canvas");
      setWebgl(!!(c.getContext("webgl2") || c.getContext("webgl")));
    } catch {
      setWebgl(false);
    }
  }, []);

  return (
    <div ref={rootRef} className="relative">
      <AuroraBackground />

      <motion.div
        ref={headRef}
        initial={{ y: 30, opacity: 0 }}
        animate={inView ? { y: 0, opacity: 1 } : undefined}
        transition={{ duration: 0.6, ease: [0.25, 0.1, 0.25, 1] }}
        style={{ fontFamily: "var(--font-plex-mono), monospace" }}
        className="relative z-10 mb-4 text-[0.7rem] uppercase tracking-[0.22em] text-[#7B8C99]"
      >
        Signal path · A → B → C → D
      </motion.div>

      <div className="relative z-10">
        <div className="relative h-[480px] w-full overflow-hidden rounded-lg border border-[#1C2933] md:h-[520px]">
          {webgl === false ? (
            <StaticFallback />
          ) : webgl && onScreen ? (
            <CanvasBoundary fallback={<StaticFallback />}>
              <StackCanvas selected={selected} onSelect={setSelected} />
            </CanvasBoundary>
          ) : (
            <div className="h-full w-full animate-pulse rounded-lg bg-[#101820]" />
          )}
        </div>
        <DetailPanel selected={selected} />
      </div>
    </div>
  );
}
