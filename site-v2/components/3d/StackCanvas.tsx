'use client'

import { useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import {
  Environment,
  Html,
  MeshTransmissionMaterial,
  RoundedBox,
} from "@react-three/drei";
import { Bloom, EffectComposer, Vignette } from "@react-three/postprocessing";
import * as THREE from "three";

// ── Hardware nodes (signal flow A → B → C → D) ──────────────────────────
type NodeDef = {
  id: string;
  name: string;
  bus: string;
  pos: [number, number, number];
};

const NODES: NodeDef[] = [
  { id: "A", name: "Camera Module 3", bus: "Sony IMX708 · CSI-2", pos: [-3.8, 1.2, 0] },
  { id: "B", name: "Hailo-8L AI HAT+", bus: "13 TOPS · PCIe Gen 3", pos: [-1.2, 0.0, 0] },
  { id: "C", name: "Raspberry Pi 5", bus: "companion · uXRCE-DDS", pos: [1.2, 0.0, 0] },
  { id: "D", name: "Pixhawk 6C Mini", bus: "autopilot · PWM", pos: [3.8, -1.2, 0] },
];

const TEAL = "#45B8AC";
const BRIGHT = new THREE.Color("#E9F0F4");
const AMBER = new THREE.Color("#E8A33D");

function useReduced() {
  const [reduce, setReduce] = useState(false);
  useEffect(() => {
    const m = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduce(m.matches);
    const on = () => setReduce(m.matches);
    m.addEventListener("change", on);
    return () => m.removeEventListener("change", on);
  }, []);
  return reduce;
}

// ── A single board ──────────────────────────────────────────────────────
function Node({
  node,
  selected,
  onSelect,
  reduce,
}: {
  node: NodeDef;
  selected: boolean;
  onSelect: (id: string) => void;
  reduce: boolean;
}) {
  const meshRef = useRef<THREE.Mesh>(null);
  const [hovered, setHovered] = useState(false);

  // start emissive at rest (0); avoids the default-1 flash
  useEffect(() => {
    const m = meshRef.current?.material as THREE.MeshPhysicalMaterial | undefined;
    if (m) m.emissiveIntensity = 0;
  }, []);

  useFrame(() => {
    if (document.hidden || !meshRef.current) return;
    const m = meshRef.current.material as THREE.MeshPhysicalMaterial;
    const target = selected ? 1.0 : hovered ? 0.6 : 0.0;
    m.emissiveIntensity = reduce
      ? target
      : THREE.MathUtils.lerp(m.emissiveIntensity, target, 0.08);
  });

  return (
    <group position={node.pos}>
      <RoundedBox
        ref={meshRef}
        args={[2.6, 1.4, 0.3]}
        radius={0.12}
        smoothness={4}
        onClick={(e) => {
          e.stopPropagation();
          onSelect(node.id);
        }}
        onPointerOver={(e) => {
          e.stopPropagation();
          setHovered(true);
          document.body.style.cursor = "pointer";
        }}
        onPointerOut={() => {
          setHovered(false);
          document.body.style.cursor = "";
        }}
      >
        <MeshTransmissionMaterial
          transmission={0.92}
          roughness={0.08}
          thickness={0.4}
          chromaticAberration={0.02}
          backside
          emissive={TEAL}
        />
      </RoundedBox>
      {/* drei Html is screen-aligned by default (billboarded) */}
      <Html position={[0, 1.0, 0]} center zIndexRange={[1, 10]}>
        <div style={{ textAlign: "center", whiteSpace: "nowrap", pointerEvents: "none" }}>
          <div
            style={{
              color: "#E9F0F4",
              fontFamily: "var(--font-plex-mono), monospace",
              fontSize: "11px",
              fontWeight: 500,
            }}
          >
            {node.name}
          </div>
          <div
            style={{
              color: "#7B8C99",
              fontFamily: "var(--font-plex-mono), monospace",
              fontSize: "10px",
            }}
          >
            {node.bus}
          </div>
        </div>
      </Html>
    </group>
  );
}

// ── A bus tube + its travelling particles ───────────────────────────────
function Tube({
  from,
  to,
  downstreamId,
  selected,
  reduce,
}: {
  from: [number, number, number];
  to: [number, number, number];
  downstreamId: string;
  selected: string | null;
  reduce: boolean;
}) {
  const curve = useMemo(
    () =>
      new THREE.CatmullRomCurve3([
        new THREE.Vector3(...from),
        new THREE.Vector3(...to),
      ]),
    [from, to]
  );

  const matRef = useRef<THREE.MeshStandardMaterial>(null);
  const particles = useRef<THREE.Mesh[]>([]);
  const pulseStart = useRef(-Infinity);

  const isDown = selected === downstreamId;
  useEffect(() => {
    if (isDown) pulseStart.current = performance.now();
  }, [isDown]);

  useFrame((state) => {
    if (document.hidden) return;
    const t = state.clock.getElapsedTime();

    // tube emissive: pulse to 1.2 for 600ms on incoming select, else 0.4
    if (matRef.current) {
      const pulsing = performance.now() - pulseStart.current < 600;
      matRef.current.emissiveIntensity = pulsing
        ? 1.2
        : reduce
          ? 0.4
          : THREE.MathUtils.lerp(matRef.current.emissiveIntensity, 0.4, 0.08);
    }

    // particles travel the curve, amber when downstream node selected
    const targetCol = isDown ? AMBER : BRIGHT;
    particles.current.forEach((p, i) => {
      if (!p) return;
      const u = reduce ? i / 5 : (t * 0.18 + i * 0.2) % 1;
      p.position.copy(curve.getPointAt(u));
      const m = p.material as THREE.MeshStandardMaterial;
      if (reduce) m.color.copy(targetCol);
      else m.color.lerp(targetCol, 0.08);
    });
  });

  return (
    <group>
      <mesh>
        <tubeGeometry args={[curve, 64, 0.025, 8, false]} />
        <meshStandardMaterial
          ref={matRef}
          color={TEAL}
          emissive={TEAL}
          emissiveIntensity={0.4}
        />
      </mesh>
      {Array.from({ length: 5 }).map((_, i) => (
        <mesh
          key={i}
          ref={(el) => {
            if (el) particles.current[i] = el;
          }}
        >
          <sphereGeometry args={[0.06, 12, 12]} />
          <meshStandardMaterial color="#E9F0F4" emissive="#E9F0F4" emissiveIntensity={0.6} />
        </mesh>
      ))}
    </group>
  );
}

// ── Camera follows the selected node ────────────────────────────────────
function CameraRig({
  target,
  reduce,
}: {
  target: [number, number, number] | null;
  reduce: boolean;
}) {
  const { camera } = useThree();
  const def = useMemo(() => new THREE.Vector3(0, 1.5, 9), []);
  useFrame(() => {
    if (document.hidden) return;
    const dest =
      target
        ? new THREE.Vector3(target[0] * 0.4, target[1] * 0.4 + 1.0, 6.5)
        : def;
    if (reduce) camera.position.copy(dest);
    else camera.position.lerp(dest, 0.03);
    camera.lookAt(0, 0, 0);
  });
  return null;
}

export default function StackCanvas({
  selected,
  onSelect,
}: {
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const reduce = useReduced();
  const selectedNode = NODES.find((n) => n.id === selected) ?? null;

  return (
    <Canvas
      style={{ width: "100%", height: "100%" }}
      camera={{ position: [0, 1.5, 9], fov: 45 }}
      gl={{ alpha: true }}
    >
      <Environment preset="night" />
      <ambientLight intensity={0.4} />
      <directionalLight position={[5, 5, 5]} intensity={0.8} />

      {NODES.slice(0, -1).map((n, i) => (
        <Tube
          key={n.id}
          from={n.pos}
          to={NODES[i + 1].pos}
          downstreamId={NODES[i + 1].id}
          selected={selected}
          reduce={reduce}
        />
      ))}

      {NODES.map((n) => (
        <Node
          key={n.id}
          node={n}
          selected={selected === n.id}
          onSelect={onSelect}
          reduce={reduce}
        />
      ))}

      <CameraRig target={selectedNode ? selectedNode.pos : null} reduce={reduce} />

      <EffectComposer>
        <Bloom luminanceThreshold={0.35} intensity={0.9} mipmapBlur />
        <Vignette offset={0.2} darkness={0.65} />
      </EffectComposer>
    </Canvas>
  );
}
