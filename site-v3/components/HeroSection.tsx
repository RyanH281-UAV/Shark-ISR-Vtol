"use client";

import dynamic from "next/dynamic";

// WebGL hero is client-only; while the chunk loads, hold the layout with a
// dark shell so there's no flash or scroll jump.
const Hero3D = dynamic(() => import("./Hero3D"), {
  ssr: false,
  loading: () => (
    <section className="flex h-screen items-center justify-center bg-navy">
      <div className="skeleton rounded bg-navy-2 px-8 py-4">
        <p className="font-mono text-xs tracking-[0.3em] text-muted">
          INITIALISING…
        </p>
      </div>
    </section>
  ),
});

export default function HeroSection() {
  return <Hero3D />;
}
