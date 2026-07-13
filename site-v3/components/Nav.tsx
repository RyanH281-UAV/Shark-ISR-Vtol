"use client";

import { motion, useScroll, useMotionValueEvent } from "motion/react";
import { useState } from "react";

const LINKS = [
  { href: "#mission", label: "Mission" },
  { href: "#detector", label: "Detector" },
  { href: "#gate", label: "Gate" },
  { href: "#hardware", label: "Hardware" },
  { href: "#stack", label: "Stack" },
  { href: "#airframe", label: "Airframe" },
  { href: "#safety", label: "Safety" },
  { href: "#proof", label: "Proof" },
];

export default function Nav() {
  const { scrollY } = useScroll();
  const [solid, setSolid] = useState(false);
  useMotionValueEvent(scrollY, "change", (y) => setSolid(y > 40));

  return (
    <motion.header
      initial={{ y: -80, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
      className={`fixed top-4 left-4 right-4 z-50 mx-auto max-w-6xl rounded-lg border px-4 transition-colors duration-300 ${
        solid
          ? "border-line bg-card/95 shadow-sm backdrop-blur-md"
          : "border-transparent bg-transparent"
      }`}
    >
      <nav
        className="flex h-14 items-center justify-between"
        aria-label="Primary"
      >
        <a
          href="#top"
          className={`font-display text-base font-semibold tracking-[0.2em] transition-colors duration-300 ${
            solid ? "text-ink" : "text-fgd"
          }`}
        >
          SHARK-ISR<span className="text-search"> / VTOL</span>
        </a>
        <div className="hidden items-center gap-6 md:flex">
          {LINKS.map((l) => (
            <a
              key={l.href}
              href={l.href}
              className={`font-mono text-xs tracking-wider transition-colors duration-200 ${
                solid
                  ? "text-mute hover:text-ink"
                  : "text-muted hover:text-fgd"
              }`}
            >
              {l.label.toUpperCase()}
            </a>
          ))}
          <a
            href="https://github.com/RyanH281-UAV/Shark-ISR-Vtol"
            className="rounded bg-navy px-4 py-1.5 font-mono text-xs tracking-wider text-fgd transition-colors duration-200 hover:bg-navy-2"
          >
            SOURCE
          </a>
        </div>
      </nav>
    </motion.header>
  );
}
