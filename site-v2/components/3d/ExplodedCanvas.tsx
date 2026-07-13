'use client'

import { MutableRefObject, Suspense, useMemo, useRef } from "react";
import type { ComponentRef } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Html, Line, RoundedBox, useGLTF } from "@react-three/drei";
import { Bloom, EffectComposer, Vignette } from "@react-three/postprocessing";
import * as THREE from "three";

const clamp01 = (v: number) => Math.min(1, Math.max(0, v));
const easeInOut = (t: number) => (t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t);
// windowed 0→1 ramp: reaches 1 at (start+dur), 0 before start
const ramp = (progress: number, start: number, dur: number) =>
  easeInOut(clamp01((progress - start) / dur));

type Vec3 = [number, number, number];
type ProgRef = MutableRefObject<number>;

// hornet.glb (post auto-fit scale ~2.62×) — nose slides along its own +Z
const NOSE_SLIDE_LOCAL = 0.75; // local units the nose node translates
const NOSE_SLIDE_START = 0.30;
const NOSE_SLIDE_DUR   = 0.28;

const BOARD_REVEAL_START = 0.42;
const BOARD_REVEAL_DUR   = 0.22;
const BOARD_SPREAD_START = 0.60;
const BOARD_SPREAD_DUR   = 0.35;

// ── Electronics stack — sits in the nose bay, spreads once revealed ───────
type StackPart = {
  id: string;
  label: string;
  bus: string;
  restPos: Vec3;
  explodedPos: Vec3;
  boxArgs: Vec3;
  colour: string;
};

const STACK_PARTS: StackPart[] = [
  { id: "cam",   label: "Camera Module 3",  bus: "CSI-2",
    restPos: [0,  0.10, 1.55], explodedPos: [0,  0.55, 2.6],
    boxArgs: [0.20, 0.03, 0.20], colour: "#45B8AC" },
  { id: "hailo", label: "Hailo-8L AI HAT+", bus: "PCIe Gen 3",
    restPos: [0,  0.02, 1.30], explodedPos: [0,  0.18, 2.8],
    boxArgs: [0.52, 0.05, 0.44], colour: "#E8A33D" },
  { id: "pi5",   label: "Raspberry Pi 5",   bus: "uXRCE-DDS",
    restPos: [0, -0.05, 1.05], explodedPos: [0, -0.18, 3.0],
    boxArgs: [0.68, 0.05, 0.44], colour: "#E9F0F4" },
  { id: "px4",   label: "Pixhawk 6C Mini",  bus: "PWM / UART",
    restPos: [0, -0.12, 0.80], explodedPos: [0, -0.55, 3.2],
    boxArgs: [0.30, 0.13, 0.30], colour: "#C2604F" },
];

// ── Meshy GLB, pre-split into "body" / "nose" nodes ───────────────────────
useGLTF.preload('/models/hornet.glb');

function HornetModel({ progress }: { progress: ProgRef }) {
  const wrapRef = useRef<THREE.Group>(null);
  const noseRef = useRef<THREE.Object3D | null>(null);
  const { scene } = useGLTF('/models/hornet.glb');

  const model = useMemo(() => {
    const c = scene.clone(true);
    c.traverse((obj) => {
      if ((obj as THREE.Mesh).isMesh) {
        const mesh = obj as THREE.Mesh;
        const cloneMat = (m: THREE.Material) => {
          const cm = (m as THREE.MeshStandardMaterial).clone();
          cm.side = THREE.DoubleSide; // see cut-face interior once nose slides off
          return cm;
        };
        mesh.material = Array.isArray(mesh.material)
          ? mesh.material.map(cloneMat)
          : cloneMat(mesh.material);
      }
    });
    // Auto-centre + normalise whole (unsplit) assembly to ~5 world units
    const box = new THREE.Box3().setFromObject(c);
    const center = box.getCenter(new THREE.Vector3());
    const size   = box.getSize(new THREE.Vector3());
    const scale  = 5.0 / Math.max(size.x, size.y, size.z);
    c.scale.setScalar(scale);
    c.position.set(-center.x * scale, -center.y * scale, -center.z * scale);
    return c;
  }, [scene]);

  useMemo(() => {
    noseRef.current = model.getObjectByName("nose") ?? null;
  }, [model]);

  useFrame((state) => {
    if (document.hidden || !wrapRef.current) return;
    const pr = progress.current;

    // Rotation settles to zero once the nose starts sliding
    const rotFade = 1 - clamp01((pr - NOSE_SLIDE_START) / 0.15);
    wrapRef.current.rotation.y = state.clock.getElapsedTime() * 0.2 * rotFade;

    // Nose slides forward off the body along its local +Z
    if (noseRef.current) {
      const slide = ramp(pr, NOSE_SLIDE_START, NOSE_SLIDE_DUR);
      noseRef.current.position.z = slide * NOSE_SLIDE_LOCAL;
    }
  });

  return (
    <group ref={wrapRef}>
      <primitive object={model} />
    </group>
  );
}

function AirframeLoading() {
  return (
    <mesh>
      <boxGeometry args={[5, 0.28, 1.2]} />
      <meshStandardMaterial color="#1C2933" transparent opacity={0.35} />
    </mesh>
  );
}

// ── Individual board (RoundedBox — no flat cube placeholders) ─────────────
function StackMesh({ part, progress }: { part: StackPart; progress: ProgRef }) {
  const ref      = useRef<THREE.Mesh>(null);
  const labelRef = useRef<HTMLDivElement>(null);
  const rest     = useMemo(() => new THREE.Vector3(...part.restPos), [part]);
  const exp      = useMemo(() => new THREE.Vector3(...part.explodedPos), [part]);

  useFrame(() => {
    if (document.hidden || !ref.current) return;
    const pr = progress.current;
    const reveal = ramp(pr, BOARD_REVEAL_START, BOARD_REVEAL_DUR);
    const spread = ramp(pr, BOARD_SPREAD_START, BOARD_SPREAD_DUR);

    ref.current.position.lerpVectors(rest, exp, spread);
    ref.current.scale.setScalar(0.6 + reveal * 0.4);

    const m = ref.current.material as THREE.MeshStandardMaterial;
    m.opacity = reveal;
    m.emissiveIntensity = 0.25 + spread * 0.55;

    if (labelRef.current) labelRef.current.style.opacity = String(spread);
  });

  return (
    <RoundedBox ref={ref} args={part.boxArgs} radius={0.015} smoothness={3}>
      <meshStandardMaterial
        color={part.colour}
        emissive={part.colour}
        emissiveIntensity={0.25}
        roughness={0.25}
        metalness={0.5}
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
          <div style={{ fontSize: "11px", fontWeight: 500, color: "#E9F0F4" }}>{part.label}</div>
          <div style={{ fontSize: "10px", color: "#7B8C99" }}>{part.bus}</div>
        </div>
      </Html>
    </RoundedBox>
  );
}

const C_LINE = new THREE.Color("#1C2933");
const C_TEAL = new THREE.Color("#45B8AC");

function Wire({ from, to, progress }: { from: Vec3; to: Vec3; progress: ProgRef }) {
  const ref = useRef<ComponentRef<typeof Line>>(null);
  useFrame(() => {
    if (document.hidden || !ref.current) return;
    const spread = ramp(progress.current, BOARD_SPREAD_START, BOARD_SPREAD_DUR);
    const mat = ref.current.material as THREE.Material & { opacity: number; color: THREE.Color };
    mat.opacity = spread;
    mat.color.copy(C_LINE).lerp(C_TEAL, spread);
  });
  return <Line ref={ref} points={[from, to]} color="#1C2933" lineWidth={1.5} transparent />;
}

function CameraRig({ progress }: { progress: ProgRef }) {
  const { camera } = useThree();
  const P_WIDE   = useMemo(() => new THREE.Vector3(1.6, 1.1, 8.5), []); // phase 1 — full airframe, 3/4
  const P_REVEAL = useMemo(() => new THREE.Vector3(0.8, 0.7, 5.5), []); // phase 2 — pushing toward nose gap
  const P_ZOOM   = useMemo(() => new THREE.Vector3(0.3, 0.5, 3.0), []); // phase 3 — tight on the stack

  const lookWide   = useMemo(() => new THREE.Vector3(0, 0,   0.9), []);
  const lookZoom   = useMemo(() => new THREE.Vector3(0, 0.1, 2.9), []);

  useFrame(() => {
    if (document.hidden) return;
    const pr = progress.current;
    const toReveal = ramp(pr, 0.20, 0.25); // wide → reveal
    const toZoom   = ramp(pr, BOARD_SPREAD_START, BOARD_SPREAD_DUR); // reveal → zoom

    const posA = P_WIDE.clone().lerp(P_REVEAL, toReveal);
    const posB = posA.lerp(P_ZOOM, toZoom);
    camera.position.lerp(posB, 0.045);

    const look = lookWide.clone().lerp(lookZoom, toZoom);
    camera.lookAt(look);
  });
  return null;
}

export default function ExplodedCanvas({ scrollProgress }: { scrollProgress: ProgRef }) {
  const byId = (id: string) => STACK_PARTS.find((p) => p.id === id)!.explodedPos;

  return (
    <Canvas
      style={{ width: "100%", height: "100%" }}
      camera={{ position: [1.6, 1.1, 8.5], fov: 40 }}
      gl={{ alpha: true, antialias: true }}
      shadows={false}
    >
      <ambientLight intensity={0.45} />
      <directionalLight position={[5, 12, 8]}  intensity={1.3} color="#E9F0F4" />
      <directionalLight position={[-4, -2, -6]} intensity={0.3} color="#45B8AC" />
      <pointLight position={[0, 0.3, 2.2]} intensity={2.5} color="#45B8AC" distance={4} decay={2} />

      <Suspense fallback={<AirframeLoading />}>
        <HornetModel progress={scrollProgress} />
      </Suspense>

      {STACK_PARTS.map((p) => (
        <StackMesh key={p.id} part={p} progress={scrollProgress} />
      ))}

      <Wire from={byId("cam")}   to={byId("hailo")} progress={scrollProgress} />
      <Wire from={byId("hailo")} to={byId("pi5")}   progress={scrollProgress} />
      <Wire from={byId("pi5")}   to={byId("px4")}   progress={scrollProgress} />

      <CameraRig progress={scrollProgress} />

      <EffectComposer>
        <Bloom luminanceThreshold={0.28} intensity={1.0} mipmapBlur />
        <Vignette offset={0.2} darkness={0.6} />
      </EffectComposer>
    </Canvas>
  );
}
