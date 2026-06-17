'use client'

import { useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Line, Trail } from "@react-three/drei";
import { Bloom, EffectComposer } from "@react-three/postprocessing";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import * as THREE from "three";
import {
  CFG,
  DECAY,
  GAIN,
  K_SUSTAIN,
  STATE_COLOR,
  TAU,
  clamp,
  type State,
} from "@/lib/guidance";

const OCEAN = new THREE.Color("#0D1820");
const TEAL = new THREE.Color("#45B8AC");
const TILE_W = CFG.oceanW / CFG.gridCols;
const TILE_D = CFG.oceanD / CFG.gridRows;
const N = CFG.gridCols * CFG.gridRows;
const LANES = 10; // lawnmower sweep lanes across the patrol depth

function cellCenter(c: number, r: number) {
  return {
    x: -CFG.oceanW / 2 + (c + 0.5) * TILE_W,
    z: -CFG.oceanD / 2 + (r + 0.5) * TILE_D,
  };
}

// ── Ocean with a gentle sine ripple ─────────────────────────────────────
function Ocean() {
  const ref = useRef<THREE.Mesh>(null);
  const base = useRef<Float32Array | null>(null);

  useFrame((state) => {
    if (document.hidden) return;
    const geo = ref.current?.geometry as THREE.PlaneGeometry | undefined;
    if (!geo) return;
    const pos = geo.attributes.position as THREE.BufferAttribute;
    if (!base.current) base.current = Float32Array.from(pos.array as Float32Array);
    const t = state.clock.getElapsedTime() * 0.4; // speed
    for (let i = 0; i < pos.count; i++) {
      const x = base.current[i * 3];
      const y = base.current[i * 3 + 1];
      pos.setZ(i, Math.sin(x * 0.3 + t) * 0.08 + Math.cos(y * 0.3 + t) * 0.08);
    }
    pos.needsUpdate = true;
    geo.computeVertexNormals();
  });

  return (
    <mesh ref={ref} rotation={[-Math.PI / 2, 0, 0]}>
      <planeGeometry args={[CFG.oceanW, CFG.oceanD, 32, 32]} />
      <meshStandardMaterial color="#0D1820" roughness={0.85} metalness={0.05} />
    </mesh>
  );
}

// ── Everything that moves: grid, drone, detection ───────────────────────
function Scene({ onState }: { onState: (s: State) => void }) {
  const { camera } = useThree();
  const reduce = useMemo(
    () =>
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    []
  );

  const gridRef = useRef<THREE.InstancedMesh>(null);
  const droneRef = useRef<THREE.Group>(null);
  const sphereRef = useRef<THREE.Mesh>(null);
  const camTarget = useRef(new THREE.Vector3(14, 14, 14));

  const [state, setLocalState] = useState<State>("TRANSIT");
  const [detPoint, setDetPoint] = useState<THREE.Vector3 | null>(null);

  // probability field — high (teal) where unobserved, decays as searched
  const prob = useRef<Float32Array>(new Float32Array(N).fill(0.85));

  const sim = useRef({
    pos: new THREE.Vector3(-CFG.oceanW / 2 + 1, CFG.flyY, -CFG.oceanD / 2 + 1),
    vel: new THREE.Vector3(1, 0, 0),
    conf: 0,
    sustain: 0,
    lane: 0,
    dir: 1,
    state: "TRANSIT" as State,
    // hidden target the search must find (drives confidence accumulation)
    target: cellCenter(
      Math.floor(CFG.gridCols * 0.62),
      Math.floor(CFG.gridRows * 0.5)
    ),
    detT: 0, // time of TRACK transition (for sphere falloff)
    t0: 0, // first-frame timestamp (TRANSIT → SEARCH delay)
  });

  const setState = (s: State) => {
    sim.current.state = s;
    setLocalState(s);
    onState(s);
  };

  // place grid tiles once
  useEffect(() => {
    const m = gridRef.current;
    if (!m) return;
    const dummy = new THREE.Object3D();
    let i = 0;
    for (let r = 0; r < CFG.gridRows; r++) {
      for (let c = 0; c < CFG.gridCols; c++) {
        const { x, z } = cellCenter(c, r);
        dummy.position.set(x, 0.01, z);
        dummy.rotation.set(-Math.PI / 2, 0, 0);
        dummy.scale.set(TILE_W * 0.9, TILE_D * 0.9, 1);
        dummy.updateMatrix();
        m.setMatrixAt(i, dummy.matrix);
        m.setColorAt(i, OCEAN);
        i++;
      }
    }
    m.instanceMatrix.needsUpdate = true;
    if (m.instanceColor) m.instanceColor.needsUpdate = true;
  }, []);

  // camera: GSAP ScrollTrigger swings iso → top-down on scroll entry
  useEffect(() => {
    if (reduce) {
      camTarget.current.set(0, 22, 0);
      return;
    }
    gsap.registerPlugin(ScrollTrigger);
    const st = ScrollTrigger.create({
      trigger: "#mission-3d",
      start: "top center",
      end: "bottom center",
      onEnter: () => camTarget.current.set(0, 22, 0),
      onLeaveBack: () => camTarget.current.set(14, 14, 14),
    });
    return () => st.kill();
  }, [reduce]);

  useFrame((rs, delta) => {
    if (document.hidden) return;
    const s = sim.current;
    const dt = Math.min(delta, 0.05);
    const now = rs.clock.getElapsedTime();
    if (s.t0 === 0) s.t0 = now;
    // brief TRANSIT entry, then begin Bayesian search
    if (s.state === "TRANSIT" && now - s.t0 > 1.2) setState("SEARCH");

    // ── camera lerp toward target ──
    camera.position.lerp(camTarget.current, reduce ? 1 : 0.03);
    camera.lookAt(0, 0, 0);

    // ── flight: TRANSIT in → lawnmower SEARCH → close-in SCAN → orbit TRACK ──
    let speed = 9;
    let desired: THREE.Vector3;

    if (s.state === "TRACK") {
      // orbit the detection point at CFG.orbitR
      const a = rs.clock.getElapsedTime() * 0.8;
      const cx = (detPoint?.x ?? s.target.x);
      const cz = (detPoint?.z ?? s.target.z);
      desired = new THREE.Vector3(
        cx + Math.cos(a) * CFG.orbitR,
        CFG.flyY,
        cz + Math.sin(a) * CFG.orbitR
      );
    } else if (s.state === "SCAN") {
      // slow down and close in on the candidate to inspect
      speed = 4.5;
      desired = new THREE.Vector3(s.target.x, CFG.flyY, s.target.z);
    } else {
      // serpentine waypoint
      const laneZ =
        -CFG.oceanD / 2 + 2 + (s.lane / (LANES - 1)) * (CFG.oceanD - 4);
      const endX = s.dir > 0 ? CFG.oceanW / 2 - 2 : -CFG.oceanW / 2 + 2;
      desired = new THREE.Vector3(endX, CFG.flyY, laneZ);
      if (s.pos.distanceTo(desired) < 1.2) {
        s.lane = Math.min(s.lane + 1, LANES - 1);
        s.dir *= -1;
        if (s.lane >= LANES - 1 && s.state === "SEARCH") s.lane = 0; // loop sweep
      }
    }

    // move toward desired
    const toGo = desired.clone().sub(s.pos);
    if (toGo.length() > 0.001) {
      s.vel.lerp(toGo.normalize(), 0.1);
      s.pos.addScaledVector(s.vel, speed * dt);
    }

    // ── observation: lower probability of swept cells (SEARCH + SCAN) ──
    if (s.state === "SEARCH" || s.state === "SCAN") {
      const sensor = 3.5;
      const grid = gridRef.current;
      let i = 0;
      for (let r = 0; r < CFG.gridRows; r++) {
        for (let c = 0; c < CFG.gridCols; c++, i++) {
          const { x, z } = cellCenter(c, r);
          const d2 = (x - s.pos.x) ** 2 + (z - s.pos.z) ** 2;
          if (d2 < sensor * sensor) prob.current[i] *= 0.96; // observed → lower
          if (grid) {
            const col = OCEAN.clone().lerp(TEAL, prob.current[i]);
            grid.setColorAt(i, col);
          }
        }
      }
      if (grid?.instanceColor) grid.instanceColor.needsUpdate = true;
    }

    const dist2 = (s.pos.x - s.target.x) ** 2 + (s.pos.z - s.target.z) ** 2;

    // SEARCH: a candidate inside sensor range promotes to SCAN
    if (s.state === "SEARCH" && dist2 < 36) {
      s.sustain = 0;
      setState("SCAN");
    }

    // SCAN: accumulate confidence. A sustained τ crossing (K_SUSTAIN) commits
    // to TRACK; a fizzled candidate falls back to SEARCH. One lucky frame never
    // commits — that's the whole point of the SCAN phase.
    if (s.state === "SCAN") {
      const near = dist2 < 25;
      const hit = near && Math.random() < 0.9;
      s.conf = clamp(s.conf + (hit ? GAIN : -DECAY));
      if (s.conf >= TAU) {
        s.sustain++;
        if (s.sustain >= K_SUSTAIN) {
          s.detT = now;
          setDetPoint(new THREE.Vector3(s.target.x, CFG.flyY, s.target.z));
          setState("TRACK");
        }
      } else {
        s.sustain = 0;
        if (!near && s.conf <= 0) setState("SEARCH");
      }
    }

    // ── drone transform: face direction of travel (quaternion) ──
    if (droneRef.current) {
      droneRef.current.position.copy(s.pos);
      const dir = s.vel.clone().setY(0);
      if (dir.lengthSq() > 1e-4) {
        const q = new THREE.Quaternion().setFromUnitVectors(
          new THREE.Vector3(0, 0, 1),
          dir.normalize()
        );
        droneRef.current.quaternion.slerp(q, 0.2);
      }
    }

    // ── detection sphere falloff: 2.0 → 0.3 over 2s ──
    if (sphereRef.current && s.state === "TRACK") {
      const mat = sphereRef.current.material as THREE.MeshStandardMaterial;
      const k = Math.min((rs.clock.getElapsedTime() - s.detT) / 2, 1);
      mat.emissiveIntensity = THREE.MathUtils.lerp(2.0, 0.3, k);
    }
  });

  const color = STATE_COLOR[state];
  const triangle = useMemo(() => {
    const shape = new THREE.Shape();
    shape.moveTo(0, 0.5);
    shape.lineTo(-0.35, -0.4);
    shape.lineTo(0.35, -0.4);
    shape.closePath();
    return shape;
  }, []);

  return (
    <>
      <ambientLight intensity={0.5} />
      <directionalLight position={[10, 18, 8]} intensity={1.1} />

      <Ocean />

      <instancedMesh ref={gridRef} args={[undefined, undefined, N]}>
        <planeGeometry args={[1, 1]} />
        <meshBasicMaterial transparent opacity={0.4} toneMapped={false} />
      </instancedMesh>

      {/* drone + trail */}
      <Trail width={0.3} length={20} color={color} attenuation={(w) => w}>
        <group ref={droneRef}>
          <mesh rotation={[-Math.PI / 2, 0, 0]}>
            <extrudeGeometry args={[triangle, { depth: 0.15, bevelEnabled: false }]} />
            <meshStandardMaterial
              color={color}
              emissive={color}
              emissiveIntensity={0.5}
            />
          </mesh>
        </group>
      </Trail>

      {/* detection + orbit (TRACK only) */}
      {detPoint && (
        <>
          <mesh ref={sphereRef} position={detPoint}>
            <sphereGeometry args={[0.4, 16, 16]} />
            <meshStandardMaterial
              color="#E8A33D"
              emissive="#E8A33D"
              emissiveIntensity={2.0}
              toneMapped={false}
            />
          </mesh>
          <Line
            points={Array.from({ length: 65 }, (_, i) => {
              const a = (i / 64) * Math.PI * 2;
              return [
                detPoint.x + Math.cos(a) * CFG.orbitR,
                0.85,
                detPoint.z + Math.sin(a) * CFG.orbitR,
              ] as [number, number, number];
            })}
            color="#E8A33D"
            lineWidth={1.5}
          />
        </>
      )}
    </>
  );
}

export default function MissionCanvas({
  onState,
}: {
  onState: (s: State) => void;
}) {
  return (
    <Canvas
      style={{ width: "100%", height: "100%" }}
      camera={{ position: [14, 14, 14], fov: 45 }}
      gl={{ alpha: true }}
      shadows={false}
    >
      <Scene onState={onState} />
      <EffectComposer>
        <Bloom luminanceThreshold={0.4} intensity={0.6} mipmapBlur />
      </EffectComposer>
    </Canvas>
  );
}
