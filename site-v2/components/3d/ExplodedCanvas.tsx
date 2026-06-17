'use client'

import { MutableRefObject, useMemo, useRef } from "react";
import type { ComponentRef } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Html, Line } from "@react-three/drei";
import { Bloom, EffectComposer, Vignette } from "@react-three/postprocessing";
import * as THREE from "three";

// ── helpers ─────────────────────────────────────────────────────────────
const clamp01 = (v: number) => Math.min(1, Math.max(0, v));
const easeInOut = (t: number) => (t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t);

function phases(progress: number) {
  return {
    p1: clamp01((progress - 0.0) / 0.35),
    p2: clamp01((progress - 0.35) / 0.3),
    p3: clamp01((progress - 0.65) / 0.35),
  };
}

type Vec3 = [number, number, number];
type ProgRef = MutableRefObject<number>;

// ── airframe (STL → BoxGeometry fallback) ───────────────────────────────
type AirPart = {
  id: string;
  label: string;
  stlPath: string;
  restPos: Vec3;
  explodedPos: Vec3;
  fallbackArgs: Vec3;
  colour: string;
};

const HORNET_PARTS: AirPart[] = [
  { id: "fuse_top", label: "Fuselage — upper", stlPath: "/models/hornet/fuse_top.stl", restPos: [0, 0.18, 0], explodedPos: [0, 2.8, 0], fallbackArgs: [5.6, 0.36, 0.9], colour: "#C6D3DC" },
  { id: "fuse_bot", label: "Fuselage — lower", stlPath: "/models/hornet/fuse_bot.stl", restPos: [0, -0.18, 0], explodedPos: [0, -1.6, 0], fallbackArgs: [5.6, 0.36, 0.9], colour: "#C6D3DC" },
  { id: "wing_l", label: "Port wing", stlPath: "/models/hornet/wing_l.stl", restPos: [-2.8, 0, 0], explodedPos: [-6.4, 0.8, 0], fallbackArgs: [4.2, 0.11, 2.0], colour: "#B0BEC8" },
  { id: "wing_r", label: "Starboard wing", stlPath: "/models/hornet/wing_r.stl", restPos: [2.8, 0, 0], explodedPos: [6.4, 0.8, 0], fallbackArgs: [4.2, 0.11, 2.0], colour: "#B0BEC8" },
  { id: "tail", label: "Tail assembly", stlPath: "/models/hornet/tail.stl", restPos: [0, 0, -3.0], explodedPos: [0, 0.5, -6.0], fallbackArgs: [0.6, 0.11, 1.8], colour: "#B0BEC8" },
  { id: "nacelle_fl", label: "Front-left nacelle", stlPath: "/models/hornet/nacelle_fl.stl", restPos: [-2.5, 0, 1.6], explodedPos: [-5.0, 2.2, 2.8], fallbackArgs: [0.9, 0.9, 0.36], colour: "#7B8C99" },
  { id: "nacelle_fr", label: "Front-right nacelle", stlPath: "/models/hornet/nacelle_fr.stl", restPos: [2.5, 0, 1.6], explodedPos: [5.0, 2.2, 2.8], fallbackArgs: [0.9, 0.9, 0.36], colour: "#7B8C99" },
  { id: "nacelle_rear", label: "Rear nacelle", stlPath: "/models/hornet/nacelle_rear.stl", restPos: [0, 0, -2.2], explodedPos: [0, 2.4, -4.5], fallbackArgs: [0.9, 0.9, 0.36], colour: "#7B8C99" },
];

// ── electronics stack (always BoxGeometry) ──────────────────────────────
type StackPart = {
  id: string;
  label: string;
  bus: string;
  restPos: Vec3;
  explodedPos: Vec3;
  boxArgs: Vec3;
  colour: string;
  description: string;
};

const STACK_PARTS: StackPart[] = [
  { id: "cam", label: "Camera Module 3", bus: "CSI-2", restPos: [0, 0.4, 0.55], explodedPos: [0, 3.2, 0], boxArgs: [0.23, 0.03, 0.23], colour: "#45B8AC", description: "Sony IMX708 · 30 FPS at 1080p into Hailo via CSI-2" },
  { id: "hailo", label: "Hailo-8L AI HAT+", bus: "PCIe Gen 3", restPos: [0, 0.4, 0], explodedPos: [0, 1.8, 0], boxArgs: [0.59, 0.04, 0.51], colour: "#E8A33D", description: "13 TOPS INT8 · YOLOv8n compiled to .hef · ~30 FPS" },
  { id: "pi5", label: "Raspberry Pi 5", bus: "uXRCE-DDS", restPos: [0, 0.4, -0.12], explodedPos: [0, 0.4, 0], boxArgs: [0.77, 0.04, 0.51], colour: "#E9F0F4", description: "Companion · ROS 2 guidance state machine · SEARCH→TRACK" },
  { id: "px4", label: "Pixhawk 6C Mini", bus: "PWM / UART", restPos: [0, 0.4, -0.4], explodedPos: [0, -0.9, 0], boxArgs: [0.35, 0.13, 0.35], colour: "#C2604F", description: "PX4 autopilot · owns inner loop + all failsafes" },
];

// ── components ──────────────────────────────────────────────────────────
function AirframeMesh({ part, progress }: { part: AirPart; progress: ProgRef }) {
  const ref = useRef<THREE.Mesh>(null);
  const labelRef = useRef<HTMLDivElement>(null);
  const rest = useMemo(() => new THREE.Vector3(...part.restPos), [part]);
  const exp = useMemo(() => new THREE.Vector3(...part.explodedPos), [part]);

  useFrame(() => {
    if (document.hidden || !ref.current) return;
    const { p1, p2 } = phases(progress.current);
    ref.current.position.lerpVectors(rest, exp, easeInOut(p1));
    const m = ref.current.material as THREE.MeshStandardMaterial;
    m.opacity = clamp01(p1 / 0.05); // fade in at start
    if (labelRef.current) {
      labelRef.current.style.opacity = String(
        clamp01(p1) * (1 - clamp01(p2 / 0.5)) // fade out before p2 → 0.5
      );
    }
  });

  return (
    <mesh ref={ref}>
      <boxGeometry args={part.fallbackArgs} />
      <meshStandardMaterial
        color={part.colour}
        roughness={0.55}
        metalness={0.05}
        transparent
        opacity={0}
      />
      <Html position={[0, 0.5, 0]} center>
        <div
          ref={labelRef}
          style={{
            fontFamily: "var(--font-plex-mono), monospace",
            fontSize: "10px",
            color: "#7B8C99",
            whiteSpace: "nowrap",
            pointerEvents: "none",
            opacity: 0,
          }}
        >
          {part.label}
        </div>
      </Html>
    </mesh>
  );
}

function StackMesh({ part, progress }: { part: StackPart; progress: ProgRef }) {
  const ref = useRef<THREE.Mesh>(null);
  const labelRef = useRef<HTMLDivElement>(null);
  const rest = useMemo(() => new THREE.Vector3(...part.restPos), [part]);
  const exp = useMemo(() => new THREE.Vector3(...part.explodedPos), [part]);

  useFrame(() => {
    if (document.hidden || !ref.current) return;
    const { p2, p3 } = phases(progress.current);
    ref.current.position.lerpVectors(rest, exp, easeInOut(p3));
    const m = ref.current.material as THREE.MeshStandardMaterial;
    m.opacity = clamp01((p2 - 0.1) / 0.2); // invisible until p2 > 0.1
    m.emissiveIntensity = clamp01((p3 - 0.5) / 0.5) * 0.5; // glow late phase 3
    if (labelRef.current) labelRef.current.style.opacity = String(clamp01(p3));
  });

  return (
    <mesh ref={ref}>
      <boxGeometry args={part.boxArgs} />
      <meshStandardMaterial
        color={part.colour}
        emissive={part.colour}
        emissiveIntensity={0}
        roughness={0.3}
        metalness={0.4}
        transparent
        opacity={0}
      />
      <Html position={[0.4, 0, 0]}>
        <div
          ref={labelRef}
          style={{
            fontFamily: "var(--font-plex-mono), monospace",
            whiteSpace: "nowrap",
            pointerEvents: "none",
            opacity: 0,
          }}
        >
          <div style={{ fontSize: "11px", fontWeight: 500, color: "#E9F0F4" }}>
            {part.label}
          </div>
          <div style={{ fontSize: "10px", color: "#7B8C99" }}>{part.bus}</div>
        </div>
      </Html>
    </mesh>
  );
}

const C_LINE = new THREE.Color("#1C2933");
const C_TEAL = new THREE.Color("#45B8AC");

function Wire({ from, to, progress }: { from: Vec3; to: Vec3; progress: ProgRef }) {
  const ref = useRef<ComponentRef<typeof Line>>(null);
  useFrame(() => {
    if (document.hidden || !ref.current) return;
    const { p3 } = phases(progress.current);
    const mat = ref.current.material as THREE.Material & {
      opacity: number;
      color: THREE.Color;
    };
    mat.opacity = p3;
    mat.color.copy(C_LINE).lerp(C_TEAL, p3);
  });
  return (
    <Line ref={ref} points={[from, to]} color="#1C2933" lineWidth={1.5} transparent />
  );
}

function CameraRig({ progress }: { progress: ProgRef }) {
  const { camera } = useThree();
  const P1 = useMemo(() => new THREE.Vector3(0, 8, 14), []);
  const P2 = useMemo(() => new THREE.Vector3(0, 5, 6), []);
  const P3 = useMemo(() => new THREE.Vector3(0, 4, 5), []);
  useFrame(() => {
    if (document.hidden) return;
    const pr = progress.current;
    const target = pr >= 0.65 ? P3 : pr >= 0.35 ? P2 : P1;
    camera.position.lerp(target, 0.04);
    camera.lookAt(0, 0, 0);
  });
  return null;
}

export default function ExplodedCanvas({
  scrollProgress,
}: {
  scrollProgress: ProgRef;
}) {
  const byId = (id: string) => STACK_PARTS.find((p) => p.id === id)!.explodedPos;

  return (
    <Canvas
      style={{ width: "100%", height: "100%" }}
      camera={{ position: [0, 8, 14], fov: 40 }}
      gl={{ alpha: true, antialias: true }}
      shadows={false}
    >
      <ambientLight intensity={0.3} />
      <directionalLight position={[5, 12, 8]} intensity={1.1} color="#E9F0F4" />
      <directionalLight position={[-4, -2, -6]} intensity={0.25} color="#45B8AC" />

      {HORNET_PARTS.map((p) => (
        <AirframeMesh key={p.id} part={p} progress={scrollProgress} />
      ))}

      {STACK_PARTS.map((p) => (
        <StackMesh key={p.id} part={p} progress={scrollProgress} />
      ))}

      <Wire from={byId("cam")} to={byId("hailo")} progress={scrollProgress} />
      <Wire from={byId("hailo")} to={byId("pi5")} progress={scrollProgress} />
      <Wire from={byId("pi5")} to={byId("px4")} progress={scrollProgress} />

      <CameraRig progress={scrollProgress} />

      <EffectComposer>
        <Bloom luminanceThreshold={0.3} intensity={0.7} mipmapBlur />
        <Vignette offset={0.2} darkness={0.6} />
      </EffectComposer>
    </Canvas>
  );
}
