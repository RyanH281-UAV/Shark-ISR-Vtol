'use client'

import { useEffect, useRef, useState } from "react";
import { motion, useMotionValue, useSpring } from "framer-motion";

const DOT = 8;
const RING = 32;
const SPRING = { stiffness: 150, damping: 18, mass: 0.8 };

// Global custom cursor: instant dot + spring-lagged ring.
export default function SplashCursor() {
  const dotRef = useRef<HTMLDivElement>(null);
  const [enabled, setEnabled] = useState(false);
  const [hover, setHover] = useState(false);
  const [onCanvas, setOnCanvas] = useState(false);

  // ring target (top-left coord), spring-smoothed
  const ringX = useMotionValue(-100);
  const ringY = useMotionValue(-100);
  const springX = useSpring(ringX, SPRING);
  const springY = useSpring(ringY, SPRING);

  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const coarse = window.matchMedia("(pointer: coarse)").matches;
    if (reduce || coarse) return; // no custom cursor for touch / reduced motion

    setEnabled(true);
    document.documentElement.style.cursor = "none";

    const move = (e: MouseEvent) => {
      // dot tracks exactly via direct transform — no React/spring lag
      if (dotRef.current) {
        dotRef.current.style.transform =
          `translate3d(${e.clientX - DOT / 2}px, ${e.clientY - DOT / 2}px, 0)`;
      }
      ringX.set(e.clientX - RING / 2);
      ringY.set(e.clientY - RING / 2);

      const t = e.target as Element | null;
      setHover(!!t?.closest?.('button, a, [role="button"], canvas'));
      setOnCanvas(!!t?.closest?.("canvas"));
    };

    window.addEventListener("mousemove", move);
    return () => {
      window.removeEventListener("mousemove", move);
      document.documentElement.style.cursor = "";
    };
  }, [ringX, ringY]);

  if (!enabled) return null;

  const ringFill = onCanvas
    ? "rgba(69,184,172,0.30)" // #45B8AC @ 30% on canvas
    : hover
      ? "rgba(69,184,172,0.15)" // #45B8AC @ 15% on interactive
      : "rgba(69,184,172,0)";

  return (
    <>
      <div
        ref={dotRef}
        aria-hidden
        className="pointer-events-none fixed left-0 top-0 z-[9999]"
        style={{ width: DOT, height: DOT }}
      >
        <motion.span
          className="block h-full w-full rounded-full"
          style={{ background: "#E9F0F4" }}
          animate={{ scale: hover ? 0 : 1 }}
          transition={{ type: "spring", stiffness: 250, damping: 20 }}
        />
      </div>
      <motion.div
        aria-hidden
        className="pointer-events-none fixed left-0 top-0 z-[9999] rounded-full"
        style={{
          x: springX,
          y: springY,
          width: RING,
          height: RING,
          border: "1.5px solid #45B8AC",
        }}
        animate={{ scale: hover ? 1.5 : 1, backgroundColor: ringFill }}
        transition={{ type: "spring", stiffness: 250, damping: 20 }}
      />
    </>
  );
}
