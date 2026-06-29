"use client";

import { ArrowRight } from "lucide-react";
import { AnimatedGroup } from "./AnimatedGroup";
import SplitHeading from "./ui/SplitHeading";

const GITHUB_URL = "https://github.com/YOUR-USERNAME/shark-isr-vtol";

// Real platform/build facts only — README forbids unproven capability claims.
const specs = [
  { stat: "2.5", unit: "kg", label: "MTOW ceiling" },
  { stat: "13", unit: "TOPS", label: "Onboard edge AI" },
  { stat: "7", unit: "pkgs", label: "ROS 2 packages" },
  { stat: "65/65", unit: "", label: "Unit tests pass" },
  { stat: "1.1", unit: "m", label: "Tri-tiltrotor" },
];

export function Hero() {
  return (
    <section className="relative overflow-hidden border-b border-line">
      {/* faint instrument grid */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-[0.55]"
        style={{
          backgroundImage:
            "linear-gradient(var(--color-line) 1px, transparent 1px), linear-gradient(90deg, var(--color-line) 1px, transparent 1px)",
          backgroundSize: "56px 56px",
          maskImage:
            "radial-gradient(ellipse 80% 60% at 50% 0%, black 40%, transparent 100%)",
        }}
      />
      <div className="relative mx-auto max-w-6xl px-6 pt-24 pb-16 md:pt-32">
        <div className="max-w-3xl">
          <AnimatedGroup>
            <div className="mb-7 inline-flex items-center gap-2 rounded-sm border border-line2 bg-surface px-3 py-1.5">
              <span className="pulse-dot inline-block h-1.5 w-1.5 rounded-full bg-accent" />
              <span className="font-mono text-[0.68rem] uppercase tracking-[0.22em] text-faint">
                Autonomous Maritime ISR
              </span>
            </div>

            <SplitHeading
              text="The aircraft transitions SEARCH → TRACK on its own."
              as="h1"
              className="text-balance font-display text-5xl font-semibold leading-[1.0] tracking-[-0.03em] text-primary sm:text-6xl lg:text-[4.6rem]"
            />

            <p className="mt-6 max-w-xl text-pretty font-sans text-lg leading-relaxed text-secondary">
              A ROS&nbsp;2 guidance state machine flies a tri-tiltrotor VTOL,
              gated on <strong className="font-medium text-ink">onboard
              detection confidence</strong> — no video downlink in the decision
              loop, no operator watching a screen.
            </p>
          </AnimatedGroup>

          <AnimatedGroup
            delay={0.5}
            className="mt-9 flex flex-col gap-3 sm:flex-row"
          >
            <a
              href="#autonomy-loop"
              className="inline-flex cursor-pointer items-center justify-center gap-2 rounded-sm bg-accent px-6 py-3 font-sans text-sm font-medium text-white transition-colors hover:bg-blue-700"
            >
              Explore the autonomy loop
              <ArrowRight className="h-4 w-4" />
            </a>
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex cursor-pointer items-center justify-center gap-2 rounded-sm border border-line2 bg-surface px-6 py-3 font-sans text-sm font-medium text-primary transition-colors hover:border-faint"
            >
              View on GitHub
            </a>
          </AnimatedGroup>
        </div>

        {/* spec rail */}
        <AnimatedGroup delay={0.7} className="mt-16">
          <div className="grid grid-cols-2 divide-line overflow-hidden rounded-xl border border-line bg-surface sm:grid-cols-3 lg:grid-cols-5">
            {specs.map((s) => (
              <div
                key={s.label}
                className="border-b border-line px-5 py-5 last:border-b-0 sm:[&:nth-last-child(-n+2)]:border-b-0 lg:[&:nth-child(n)]:border-b-0 [&:not(:last-child)]:border-r"
              >
                <div className="flex items-baseline gap-1">
                  <span className="font-display text-2xl font-bold text-primary">
                    {s.stat}
                  </span>
                  {s.unit && (
                    <span className="font-mono text-xs text-faint">
                      {s.unit}
                    </span>
                  )}
                </div>
                <div className="mt-1 font-mono text-[0.62rem] uppercase tracking-[0.16em] text-faint">
                  {s.label}
                </div>
              </div>
            ))}
          </div>
        </AnimatedGroup>
      </div>
    </section>
  );
}
