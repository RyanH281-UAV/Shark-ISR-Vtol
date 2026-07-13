"use client";

import { Canvas, useFrame } from "@react-three/fiber";
import { Html, Line, useGLTF } from "@react-three/drei";
import {
  useScroll,
  useReducedMotion,
  type MotionValue,
} from "motion/react";
import Image from "next/image";
import { useEffect, useRef, useState, Suspense } from "react";
import * as THREE from "three";
import { hasWebGL } from "@/lib/webgl";

const DRACO = "/draco/";

/**
 * D — Exploded airframe. Scroll scrubs the breakdown: five Meshy-scanned
 * airframe parts travel from a loose cluster to a labelled technical plate.
 * This is a parts breakdown, not a pretend seamless assembly — each part was
 * reconstructed from its own slicer/CAD view.
 */

const PARTS: {
  id: string;
  file: string;
  label: string;
  spec: string;
  slot: [number, number, number]; // exploded position
  seed: [number, number, number]; // clustered position
  size: number;
  mirror?: boolean;
}[] = [
  {
    id: "nose",
    file: "/models/part_nose.min.glb",
    label: "NOSE",
    spec: "Camera aperture · IMX708 nadir",
    slot: [-3.4, 0.2, 0],
    seed: [-0.6, 0.1, 0.2],
    size: 1.5,
  },
  {
    id: "fuse",
    file: "/models/part_fuse_body.min.glb",
    label: "FUSELAGE",
    spec: "Payload bay · full stack inside · 2.5 kg MTOW",
    slot: [0, 0.2, 0],
    seed: [0, 0, 0],
    size: 2.2,
  },
  {
    id: "tail",
    file: "/models/part_tail.min.glb",
    label: "TAIL",
    spec: "Fixed rear rotor · no tilt",
    slot: [3.4, 0.2, 0],
    seed: [0.6, 0.1, -0.2],
    size: 1.6,
  },
  {
    id: "wing_p",
    file: "/models/part_wing_port.min.glb",
    label: "WING · PORT",
    spec: "NACA 4410 root · 1100 mm span pair",
    slot: [-1.8, 1.8, 0],
    seed: [-0.3, 0.4, 0.1],
    size: 2.0,
  },
  {
    id: "wing_s",
    file: "/models/part_wing_port.min.glb",
    label: "WING · STBD",
    spec: "NACA 2410 tip · L/D 22",
    slot: [1.8, 1.8, 0],
    seed: [0.3, 0.4, -0.1],
    size: 2.0,
    mirror: true,
  },
  {
    id: "nacelle",
    file: "/models/part_nacelle_mount.min.glb",
    label: "TILT NACELLE",
    spec: "Front rotor tilt mount · ×2",
    slot: [0, -1.7, 0],
    seed: [0, -0.4, 0.15],
    size: 1.3,
  },
];

PARTS.forEach((p) => useGLTF.preload(p.file, DRACO));

function Part({
  part,
  progress,
  frozen,
}: {
  part: (typeof PARTS)[number];
  progress: MotionValue<number>;
  frozen: boolean;
}) {
  const { scene } = useGLTF(part.file, DRACO);
  const group = useRef<THREE.Group>(null);
  const inner = useRef<THREE.Object3D | null>(null);
  const [labelOn, setLabelOn] = useState(frozen);

  if (!inner.current) {
    inner.current = scene.clone(true);
    const box = new THREE.Box3().setFromObject(inner.current);
    const size = box.getSize(new THREE.Vector3());
    const centre = box.getCenter(new THREE.Vector3());
    const s = part.size / Math.max(size.x, size.y, size.z);
    inner.current.scale.setScalar(s);
    if (part.mirror) inner.current.scale.x *= -1;
    inner.current.position.copy(centre.multiplyScalar(-s));
  }

  useFrame((state, dt) => {
    if (document.hidden) return; // SITE_UPGRADE 3D rule
    if (!group.current) return;
    const k = frozen ? 1 : progress.get();
    const e = k * k * (3 - 2 * k); // smoothstep
    const p = part.slot.map((v, i) => part.seed[i] + (v - part.seed[i]) * e);
    const d = (a: number, b: number) => THREE.MathUtils.damp(a, b, 6, dt);
    group.current.position.set(
      d(group.current.position.x, p[0]),
      d(group.current.position.y, p[1]),
      d(group.current.position.z, p[2]),
    );
    // slow individual turn so every part reads as 3D
    group.current.rotation.y = frozen ? 0.4 : state.clock.elapsedTime * 0.15;
    const on = e > 0.65;
    if (on !== labelOn) setLabelOn(on);
  });

  return (
    <group ref={group} position={part.seed}>
      <primitive object={inner.current} />
      {labelOn && (
        <>
          <Line
            points={[
              [0, 0, 0],
              [0, -part.size * 0.55 - 0.25, 0],
            ]}
            color="#45b8ac"
            lineWidth={1}
            transparent
            opacity={0.6}
          />
          <Html position={[0, -part.size * 0.55 - 0.4, 0]} center distanceFactor={8}>
            <div className="pointer-events-none whitespace-nowrap text-center">
              <p className="font-mono text-[10px] tracking-[0.25em] text-search">
                {part.label}
              </p>
              <p className="font-mono text-[9px] tracking-wider text-muted">
                {part.spec}
              </p>
            </div>
          </Html>
        </>
      )}
    </group>
  );
}

function ExplodedFallback() {
  return (
    <div className="grid grid-cols-2 gap-px overflow-hidden rounded border border-lined bg-lined sm:grid-cols-3">
      {PARTS.filter((p) => !p.mirror).map((p) => (
        <div key={p.id} className="bg-navy-2 p-5">
          <p className="font-mono text-[10px] tracking-[0.25em] text-search">
            {p.label}
          </p>
          <p className="mt-1 font-mono text-[10px] text-muted">{p.spec}</p>
        </div>
      ))}
    </div>
  );
}

export default function ExplodedView() {
  const sectionRef = useRef<HTMLElement>(null);
  const reduce = useReducedMotion() ?? false;
  const [webgl, setWebgl] = useState(true);
  useEffect(() => setWebgl(hasWebGL()), []);

  const { scrollYProgress } = useScroll({
    target: sectionRef,
    offset: ["start 0.7", "end end"],
  });

  return (
    <section
      ref={sectionRef}
      id="airframe"
      className={`relative bg-navy ${reduce || !webgl ? "" : "h-[220vh]"}`}
    >
      <div className={reduce || !webgl ? "" : "sticky top-0 h-screen"}>
        <div className="mx-auto flex h-full max-w-6xl flex-col px-6 py-20">
          <div className="mb-6">
            <p className="mb-3 font-mono text-xs tracking-[0.3em] text-search">
              AIRFRAME · PARTS BREAKDOWN
            </p>
            <h2 className="font-display text-4xl font-semibold uppercase leading-[0.95] tracking-tight text-fgd sm:text-5xl">
              Scroll to take it apart
            </h2>
            <p className="mt-3 max-w-xl text-sm leading-relaxed text-muted">
              Each part reconstructed with photogrammetry-style scanning from
              its own slicer view. Six printed sections, two tilt nacelles, one
              fixed rear rotor — 1.1 m of span at 2.5 kg MTOW.
            </p>
          </div>

          {!webgl ? (
            <ExplodedFallback />
          ) : (
            <div className="relative min-h-0 flex-1 overflow-hidden rounded border border-lined">
              <Canvas
                camera={{ position: [0, 0.4, 8.2], fov: 42 }}
                dpr={[1, 2]}
                gl={{ antialias: true, alpha: true }}
                onCreated={({ gl }) => {
                  gl.toneMapping = THREE.ACESFilmicToneMapping;
                }}
              >
                <ambientLight intensity={0.45} />
                <directionalLight position={[4, 6, 5]} intensity={2} color="#eef2ff" />
                <directionalLight position={[-5, 2, -4]} intensity={1.1} color="#45b8ac" />
                <Suspense
                  fallback={
                    <Html center>
                      <div className="skeleton rounded bg-navy-2 px-6 py-3">
                        <p className="whitespace-nowrap font-mono text-xs tracking-[0.3em] text-muted">
                          SCANNING PARTS…
                        </p>
                      </div>
                    </Html>
                  }
                >
                  {PARTS.map((p) => (
                    <Part
                      key={p.id}
                      part={p}
                      progress={scrollYProgress}
                      frozen={reduce}
                    />
                  ))}
                </Suspense>
                <fog attach="fog" args={["#0b1e33", 11, 22]} />
              </Canvas>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
