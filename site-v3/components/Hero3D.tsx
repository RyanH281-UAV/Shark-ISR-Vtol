"use client";

import { Canvas, useFrame } from "@react-three/fiber";
import {
  ContactShadows,
  Environment,
  Grid,
  Html,
  Lightformer,
  useGLTF,
} from "@react-three/drei";
import Radar from "./Radar";
import {
  motion,
  useScroll,
  useTransform,
  useMotionValueEvent,
  useReducedMotion,
  type MotionValue,
} from "motion/react";
import { useEffect, useLayoutEffect, useRef, useState, Suspense } from "react";
import * as THREE from "three";
import Image from "next/image";
import { Counter } from "./Reveal";
import { hasWebGL } from "@/lib/webgl";

// Meshy-textured airframe, draco-compressed (scripts/meshy_retexture.py + gltf-transform)
const MODEL_URL = "/models/hornet_textured.min.glb";
const DRACO = "/draco/";
useGLTF.preload(MODEL_URL, DRACO);

const EASE = [0.22, 1, 0.36, 1] as const;

/* ── scroll → pose maths ─────────────────────────────────────────────────── */

const clamp01 = (v: number) => Math.min(1, Math.max(0, v));
const ramp = (p: number, a: number, b: number) => clamp01((p - a) / (b - a));
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

/* ── the aircraft ────────────────────────────────────────────────────────── */

function Hornet({
  progress,
  pointer,
  frozen,
}: {
  progress: MotionValue<number>;
  pointer: React.RefObject<{ x: number; y: number }>;
  frozen: boolean;
}) {
  const { scene } = useGLTF(MODEL_URL, DRACO);
  const group = useRef<THREE.Group>(null);

  useLayoutEffect(() => {
    const box = new THREE.Box3().setFromObject(scene);
    const size = box.getSize(new THREE.Vector3());
    const centre = box.getCenter(new THREE.Vector3());
    const s = 3.2 / Math.max(size.x, size.y, size.z);
    scene.scale.setScalar(s);
    scene.position.copy(centre.multiplyScalar(-s));

    scene.traverse((o) => {
      if (o instanceof THREE.Mesh && o.material instanceof THREE.MeshStandardMaterial) {
        if (!o.material.map) {
          o.material.metalness = 0.25;
          o.material.roughness = 0.42;
        }
        o.material.envMapIntensity = 1.4;
      }
    });
  }, [scene]);

  useFrame((state, dt) => {
    if (document.hidden) return; // SITE_UPGRADE 3D rule
    if (!group.current) return;
    const p = frozen ? 0.15 : progress.get();
    const t = state.clock.elapsedTime;

    const t1 = ramp(p, 0.05, 0.42);
    const t2 = ramp(p, 0.5, 0.85);

    const pitch = lerp(-0.42, 0.02, t1);
    const yaw =
      lerp(0.65, -0.85, t1) + lerp(0, -0.5, t2) + (frozen ? 0 : t2 * Math.sin(t * 0.25) * 0.15);
    const roll = lerp(0, -0.06, t2);
    const bobY = frozen ? 0 : Math.sin(t * 1.1) * 0.05 * (0.4 + 0.6 * t2);

    const px = frozen ? 0 : pointer.current.x;
    const py = frozen ? 0 : pointer.current.y;

    const d = (a: number, b: number) => THREE.MathUtils.damp(a, b, 4, dt);
    group.current.rotation.x = d(group.current.rotation.x, pitch + py * 0.07);
    group.current.rotation.y = d(group.current.rotation.y, yaw + px * 0.12);
    group.current.rotation.z = d(group.current.rotation.z, roll + px * 0.03);
    group.current.position.y = d(group.current.position.y, bobY);

    const camZ = lerp(6.2, 4.8, t1) + lerp(0, 1.6, t2);
    const camY = lerp(0.9, 0.35, t1);
    state.camera.position.z = d(state.camera.position.z, camZ);
    state.camera.position.y = d(state.camera.position.y, camY);
    state.camera.lookAt(0, 0, 0);
  });

  return (
    <group ref={group}>
      <primitive object={scene} />
    </group>
  );
}

function LoadingTag() {
  return (
    <Html center>
      <div className="skeleton rounded bg-navy-2 px-6 py-3">
        <p className="whitespace-nowrap font-mono text-xs tracking-[0.3em] text-muted">
          ACQUIRING AIRFRAME…
        </p>
      </div>
    </Html>
  );
}

/* ── HUD copy per beat ───────────────────────────────────────────────────── */

const BEATS = [
  {
    mode: "HOVER",
    kicker: "PHASE 01 · VTOL",
    title: ["Launches from a", "patch of sand."],
    body: "Tri-tiltrotor lift — no runway, no catapult, no net. Straight up off the beach it will patrol.",
  },
  {
    mode: "TRANSITION",
    kicker: "PHASE 02 · TILT TRANSITION",
    title: ["Tilts. Becomes", "an airplane."],
    body: "The front rotors swing forward and the wing takes the load. PX4 owns this manoeuvre end-to-end — the autonomy stack never touches it.",
  },
  {
    mode: "CRUISE",
    kicker: "PHASE 03 · PERSISTENT PATROL",
    title: ["Hours on station.", "Deciding alone."],
    body: "22:1 lift-to-drag cruise while the onboard NPU watches the water. Detect → track happens on the aircraft, not on a screen.",
  },
];

const STATS = [
  { value: 95, suffix: "%", decimals: 0, label: "Detection recall" },
  { value: 13, suffix: " TOPS", decimals: 0, label: "Onboard NPU" },
  { value: 0.945, suffix: "", decimals: 3, label: "mAP50, held-out" },
  { value: 22, suffix: ":1", decimals: 0, label: "Max lift-to-drag" },
];

function BeatCopy({
  beat,
  opacity,
}: {
  beat: (typeof BEATS)[number];
  opacity: MotionValue<number>;
}) {
  return (
    <motion.div
      style={{ opacity }}
      className="pointer-events-none absolute inset-x-6 top-[22vh] mx-auto max-w-6xl"
    >
      <p className="mb-4 font-mono text-xs tracking-[0.3em] text-search">
        {beat.kicker}
      </p>
      <h2 className="font-display max-w-xl text-5xl font-semibold uppercase leading-[0.95] tracking-tight text-fgd sm:text-7xl">
        {beat.title[0]}
        <br />
        <span className="text-search">{beat.title[1]}</span>
      </h2>
      <p className="mt-5 max-w-md leading-relaxed text-muted">{beat.body}</p>
    </motion.div>
  );
}

/* ── static fallback (no WebGL) ──────────────────────────────────────────── */

function HeroFallback() {
  return (
    <section id="top" className="relative min-h-screen overflow-hidden bg-navy">
      <Image
        src="/img/full_3q.jpg"
        alt="Titan Dynamics Hornet tri-tiltrotor VTOL"
        fill
        priority
        className="object-cover opacity-40"
        sizes="100vw"
      />
      <div className="relative mx-auto flex min-h-screen max-w-6xl flex-col justify-center px-6">
        <p className="mb-4 font-mono text-xs tracking-[0.3em] text-search">
          AUTONOMOUS PERSISTENT ISR · ROS 2 + PX4 · EDGE AI
        </p>
        <h1 className="font-display max-w-2xl text-5xl font-semibold uppercase leading-[0.95] text-fgd sm:text-7xl">
          The aircraft that decides
          <span className="text-search"> search → track</span> on its own.
        </h1>
        <dl className="mt-10 grid max-w-3xl grid-cols-2 gap-px overflow-hidden rounded border border-lined bg-lined sm:grid-cols-4">
          {STATS.map((s) => (
            <div key={s.label} className="bg-navy-2 px-5 py-4">
              <dd className="font-mono text-2xl text-fgd">
                {s.value}
                {s.suffix}
              </dd>
              <dt className="mt-1 text-xs text-muted">{s.label}</dt>
            </div>
          ))}
        </dl>
      </div>
    </section>
  );
}

/* ── hero ────────────────────────────────────────────────────────────────── */

export default function Hero3D() {
  const sectionRef = useRef<HTMLElement>(null);
  const pointer = useRef({ x: 0, y: 0 });
  const pointerPx = useRef<{ x: number; y: number } | null>(null);
  const reduce = useReducedMotion() ?? false;
  const [mode, setMode] = useState("HOVER");
  const [webgl, setWebgl] = useState<boolean | null>(null);

  useEffect(() => setWebgl(hasWebGL()), []);

  const { scrollYProgress } = useScroll({
    target: sectionRef,
    offset: ["start start", "end end"],
  });

  const beat1 = useTransform(scrollYProgress, [0, 0.28, 0.4], [1, 1, 0]);
  const beat2 = useTransform(scrollYProgress, [0.38, 0.48, 0.62, 0.72], [0, 1, 1, 0]);
  const beat3 = useTransform(scrollYProgress, [0.72, 0.84], [0, 1]);
  const railY = useTransform(scrollYProgress, [0, 1], ["0%", "200%"]);

  useMotionValueEvent(scrollYProgress, "change", (p) => {
    setMode(p < 0.42 ? "HOVER" : p < 0.72 ? "TRANSITION" : "CRUISE");
  });

  if (webgl === false) return <HeroFallback />;

  const beatOpacities = [beat1, beat2, beat3];

  return (
    <section
      ref={sectionRef}
      id="top"
      className={`relative bg-navy ${reduce ? "h-screen" : "h-[300vh]"}`}
      onPointerMove={(e) => {
        const w = window.innerWidth;
        const h = window.innerHeight;
        pointer.current = {
          x: (e.clientX / w - 0.5) * 2,
          y: (e.clientY / h - 0.5) * 2,
        };
        pointerPx.current = { x: e.clientX, y: e.clientY };
      }}
      onPointerLeave={() => {
        pointerPx.current = null;
      }}
    >
      <div className="sticky top-0 h-screen overflow-hidden">
        {/* live radar backdrop — contacts flare as the beam sweeps them */}
        <Radar pointerPx={pointerPx} frozen={reduce} />

        {webgl && (
          <Canvas
            className="absolute inset-0"
            camera={{ position: [0, 0.9, 6.2], fov: 38 }}
            dpr={[1, 2]}
            gl={{ antialias: true, alpha: true }}
            onCreated={({ gl }) => {
              gl.toneMapping = THREE.ACESFilmicToneMapping;
              gl.toneMappingExposure = 1.15;
            }}
          >
            <ambientLight intensity={0.25} />
            <directionalLight position={[4, 6, 4]} intensity={2.0} color="#eef2ff" />
            <directionalLight position={[-6, 2, -5]} intensity={1.4} color="#45b8ac" />
            <directionalLight position={[0, -3, -4]} intensity={0.4} color="#5a7a94" />
            <Environment resolution={64}>
              <Lightformer
                intensity={1.6}
                position={[0, 5, 0]}
                rotation={[Math.PI / 2, 0, 0]}
                scale={[10, 10, 1]}
                color="#dbeafe"
              />
              <Lightformer
                intensity={0.8}
                position={[-5, 1, -1]}
                rotation={[0, Math.PI / 2, 0]}
                scale={[6, 2, 1]}
                color="#45b8ac"
              />
              <Lightformer
                intensity={0.6}
                position={[5, 0, 1]}
                rotation={[0, -Math.PI / 2, 0]}
                scale={[6, 1.5, 1]}
                color="#5a7a94"
              />
            </Environment>
            <Suspense fallback={<LoadingTag />}>
              <Hornet progress={scrollYProgress} pointer={pointer} frozen={reduce} />
            </Suspense>
            <ContactShadows
              position={[0, -1.6, 0]}
              opacity={0.5}
              blur={2.4}
              scale={12}
              far={4}
              color="#000000"
            />
            <Grid
              position={[0, -1.62, 0]}
              args={[30, 30]}
              cellColor="#16324e"
              sectionColor="#1d4066"
              fadeDistance={18}
              fadeStrength={2.5}
              infiniteGrid
            />
            <fog attach="fog" args={["#0b1e33", 9, 20]} />
          </Canvas>
        )}

        {/* HUD frame */}
        <div aria-hidden className="pointer-events-none absolute inset-5">
          <span className="absolute left-0 top-0 h-6 w-6 border-l border-t border-muted/40" />
          <span className="absolute right-0 top-0 h-6 w-6 border-r border-t border-muted/40" />
          <span className="absolute bottom-0 left-0 h-6 w-6 border-b border-l border-muted/40" />
          <span className="absolute bottom-0 right-0 h-6 w-6 border-b border-r border-muted/40" />
        </div>

        <motion.p
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.2, ease: EASE }}
          style={{ opacity: beat1 }}
          className="absolute inset-x-6 top-[15vh] mx-auto max-w-6xl font-mono text-xs tracking-[0.3em] text-search"
        >
          AUTONOMOUS PERSISTENT ISR · ROS 2 + PX4 · EDGE AI
        </motion.p>

        {BEATS.map((b, i) => (
          <BeatCopy key={b.mode} beat={b} opacity={beatOpacities[i]} />
        ))}

        {/* beat-3 CTAs + stats */}
        <motion.div
          style={{ opacity: beat3 }}
          className="pointer-events-none absolute inset-x-6 bottom-[16vh] mx-auto max-w-6xl"
        >
          <div className="flex flex-wrap gap-4">
            <a
              href="#mission"
              className="pointer-events-auto rounded bg-search px-6 py-3 font-mono text-xs font-medium tracking-wider text-navy transition-colors duration-200 hover:bg-search/85"
            >
              SEE HOW IT HUNTS
            </a>
            <a
              href="#proof"
              className="pointer-events-auto rounded border border-lined bg-navy/60 px-6 py-3 font-mono text-xs font-medium tracking-wider text-fgd backdrop-blur-sm transition-colors duration-200 hover:border-search/60 hover:text-search"
            >
              SITL EVIDENCE
            </a>
          </div>
          <dl className="mt-8 grid max-w-3xl grid-cols-2 gap-px overflow-hidden rounded border border-lined bg-lined sm:grid-cols-4">
            {STATS.map((s) => (
              <div key={s.label} className="bg-navy-2/85 px-5 py-4 backdrop-blur-sm">
                <dd className="font-mono text-2xl font-medium text-fgd">
                  <Counter to={s.value} decimals={s.decimals} suffix={s.suffix} />
                </dd>
                <dt className="mt-1 block text-xs text-muted">{s.label}</dt>
              </div>
            ))}
          </dl>
        </motion.div>

        {/* telemetry strip */}
        <div className="absolute inset-x-6 bottom-6 mx-auto flex max-w-6xl items-center justify-between font-mono text-[11px] tracking-widest text-muted">
          <span>
            MODE <span className="text-search">{mode}</span>
          </span>
          <span className="hidden sm:block">HORNET · 1.1 M TRI-TILTROTOR</span>
          <span className="flex items-center gap-2">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-search motion-safe:animate-pulse" />
            LINK NOMINAL
          </span>
        </div>

        {/* scroll rail */}
        {!reduce && (
          <div
            aria-hidden
            className="absolute right-6 top-1/2 hidden h-24 w-px -translate-y-1/2 bg-lined md:block"
          >
            <motion.span
              style={{ y: railY }}
              className="absolute left-1/2 top-0 h-8 w-[3px] -translate-x-1/2 rounded bg-search"
            />
          </div>
        )}
      </div>
    </section>
  );
}
