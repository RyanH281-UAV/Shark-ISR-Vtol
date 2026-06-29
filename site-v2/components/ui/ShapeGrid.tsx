'use client'

// Subtle dot-grid texture for light/white sections.
// Parent must be `relative isolate` so the -z-10 keeps dots behind content.
export default function ShapeGrid() {
  return (
    <div
      aria-hidden
      className="pointer-events-none absolute inset-0 -z-10 opacity-40"
      style={{
        backgroundImage:
          "radial-gradient(circle, rgba(10,15,20,0.06) 1px, transparent 1px)",
        backgroundSize: "28px 28px",
      }}
    />
  );
}
