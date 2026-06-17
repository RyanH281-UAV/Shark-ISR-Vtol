'use client'

import { motion, useReducedMotion } from "framer-motion";

// Ambient animated glow for DARK sections only. CSS blobs, no Canvas.
export default function AuroraBackground() {
  const reduce = useReducedMotion();

  return (
    <div className="absolute inset-0 overflow-hidden">
      {/* Blob 1 — teal #45B8AC @ 8%, 600px, 12s loop */}
      <motion.div
        aria-hidden
        className="pointer-events-none absolute z-0 rounded-full blur-[120px]"
        style={{
          width: 600,
          height: 600,
          top: "-15%",
          left: "-10%",
          backgroundColor: "rgba(69,184,172,0.08)",
        }}
        animate={
          reduce
            ? undefined
            : { x: [0, 220, 80, 0], y: [0, 120, 260, 0] }
        }
        transition={
          reduce
            ? undefined
            : { duration: 12, repeat: Infinity, ease: "easeInOut" }
        }
      />
      {/* Blob 2 — amber #E8A33D @ 5%, 500px, 15s loop, offset phase */}
      <motion.div
        aria-hidden
        className="pointer-events-none absolute z-0 rounded-full blur-[120px]"
        style={{
          width: 500,
          height: 500,
          bottom: "-20%",
          right: "-5%",
          backgroundColor: "rgba(232,163,61,0.05)",
        }}
        animate={
          reduce
            ? undefined
            : { x: [0, -180, -60, 0], y: [0, -140, -40, 0] }
        }
        transition={
          reduce
            ? undefined
            : { duration: 15, repeat: Infinity, ease: "easeInOut", delay: 2 }
        }
      />
    </div>
  );
}
