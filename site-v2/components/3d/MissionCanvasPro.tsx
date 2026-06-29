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

// Telemetry the scene emits each (throttled) frame so DOM overlays can render
// the perception math that already drives SCAN → TRACK.
export type Telemetry = {
  state: State;
  conf: number; // 0..1 integrated detection confidence
  sustain: number; // frames held above τ (0..K_SUSTAIN)
  frameHit: boolean; // detector fired this frame
  geoloc: { lat: number; lon: number } | null; // produced on TRACK commit
};

const OCEAN = new THREE.Color("#0D1820");
const TEAL = new THREE.Color("#45B8AC");
const AZURE = new THREE.Color("#3FA7D6");
const TILE_W = CFG.oceanW / CFG.gridCols;
const TILE_D = CFG.oceanD / CFG.gridRows;
const N = CFG.gridCols * CFG.gridRows;
const LANES = 10;

// Map a target's world position to a plausible WGS-84 coord near a patrol box.
// This is the geolocation transform's *output* (pixel + attitude + AGL → lat/lon);
// the real math lives in geolocate.py. Labelled "modelled" in the UI.
const GEO_ORIGIN = { lat: -27.9943, lon: 153.4312 }; // Gold Coast patrol box
function geolocate(x: number, z: number) {
  // ~1 world unit ≈ 1.4 m ground; convert metres → degrees
  const mPerUnit = 1.4;
  const dLat = (z * mPerUnit) / 111_320;
  const dLon =
    (x * mPerUnit) / (111_320 * Math.cos((GEO_ORIGIN.lat * Math.PI) / 180));
  return { lat: GEO_ORIGIN.lat + dLat, lon: GEO_ORIGIN.lon + dLon };
}

function cellCenter(c: number, r: number) {
  return {
    x: -CFG.oceanW / 2 + (c + 0.5) * TILE_W,
    z: -CFG.oceanD / 2 + (r + 0.5) * TILE_D,
  };
}

function Ocean() {
  const ref = useRef<THREE.Mesh>(null);
  const base = useRef<Float32Array | null>(null);
  useFrame((state) => {
    if (document.hidden) return;
    const geo = ref.current?.geometry as THREE.PlaneGeometry | undefined;
    if (!geo) return;
    const pos = geo.attributes.position as THREE.BufferAttribute;
    if (!base.current) base.current = Float32Array.from(pos.array as Float32Array);
    const t = state.clock.getElapsedTime() * 0.4;
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

function Scene({
  onTelemetry,
  showCallouts,
}: {
  onTelemetry: (t: Telemetry) => void;
  showCallouts: boolean;
}) {
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
  const ringRef = useRef<THREE.Mesh>(null); // confidence ring (SCAN)
  const rayRef = useRef<THREE.Group>(null); // detection ray drone→target
  const camTarget = useRef(new THREE.Vector3(14, 14, 14));

  const [state, setLocalState] = useState<State>("TRANSIT");
  const [detPoint, setDetPoint] = useState<THREE.Vector3 | null>(null);

  const prob = useRef<Float32Array>(new Float32Array(N).fill(0.85));
  const emitAcc = useRef(0);

  const sim = useRef({
    pos: new THREE.Vector3(-CFG.oceanW / 2 + 1, CFG.flyY, -CFG.oceanD / 2 + 1),
    vel: new THREE.Vector3(1, 0, 0),
    conf: 0,
    sustain: 0,
    frameHit: false,
    lane: 0,
    dir: 1,
    state: "TRANSIT" as State,
    target: cellCenter(
      Math.floor(CFG.gridCols * 0.62),
      Math.floor(CFG.gridRows * 0.5)
    ),
    geoloc: null as { lat: number; lon: number } | null,
    detT: 0,
    t0: 0,
    orbitAngle: 0,
  });

  const setState = (s: State) => {
    sim.current.state = s;
    setLocalState(s);
  };

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

  useEffect(() => {
    if (reduce) {
      camTarget.current.set(0, 22, 0);
      return;
    }
    gsap.registerPlugin(ScrollTrigger);
    const st = ScrollTrigger.create({
      trigger: "#mission-3d-pro",
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
    if (s.state === "TRANSIT" && now - s.t0 > 0.8) setState("SEARCH");

    camera.position.lerp(camTarget.current, reduce ? 1 : 0.03);
    camera.lookAt(0, 0, 0);

    let speed = 14;
    let desired: THREE.Vector3;

    if (s.state === "TRACK") {
      const cx = detPoint?.x ?? s.target.x;
      const cz = detPoint?.z ?? s.target.z;
      s.orbitAngle += 0.3 * dt;
      s.pos.x = cx + Math.cos(s.orbitAngle) * CFG.orbitR;
      s.pos.y = CFG.flyY;
      s.pos.z = cz + Math.sin(s.orbitAngle) * CFG.orbitR;
      // velocity used only for heading — tangent to circle
      s.vel.set(-Math.sin(s.orbitAngle), 0, Math.cos(s.orbitAngle));
      desired = s.pos; // skip chase block below
    } else if (s.state === "SCAN") {
      speed = 7;
      desired = new THREE.Vector3(s.target.x, CFG.flyY, s.target.z);
    } else {
      const laneZ =
        -CFG.oceanD / 2 + 2 + (s.lane / (LANES - 1)) * (CFG.oceanD - 4);
      const endX = s.dir > 0 ? CFG.oceanW / 2 - 2 : -CFG.oceanW / 2 + 2;
      desired = new THREE.Vector3(endX, CFG.flyY, laneZ);
      if (s.pos.distanceTo(desired) < 1.2) {
        s.lane = Math.min(s.lane + 1, LANES - 1);
        s.dir *= -1;
        if (s.lane >= LANES - 1 && s.state === "SEARCH") s.lane = 0;
      }
    }

    const toGo = desired.clone().sub(s.pos);
    if (toGo.length() > 0.001) {
      s.vel.lerp(toGo.normalize(), 0.1);
      s.pos.addScaledVector(s.vel, speed * dt);
    }

    if (s.state === "SEARCH" || s.state === "SCAN") {
      const sensor = 3.5;
      const grid = gridRef.current;
      let i = 0;
      for (let r = 0; r < CFG.gridRows; r++) {
        for (let c = 0; c < CFG.gridCols; c++, i++) {
          const { x, z } = cellCenter(c, r);
          const d2 = (x - s.pos.x) ** 2 + (z - s.pos.z) ** 2;
          if (d2 < sensor * sensor) prob.current[i] *= 0.96;
          if (grid) {
            const col = OCEAN.clone().lerp(TEAL, prob.current[i]);
            grid.setColorAt(i, col);
          }
        }
      }
      if (grid?.instanceColor) grid.instanceColor.needsUpdate = true;
    }

    const dist2 = (s.pos.x - s.target.x) ** 2 + (s.pos.z - s.target.z) ** 2;

    if (s.state === "SEARCH" && dist2 < 36) {
      s.sustain = 0;
      setState("SCAN");
    }

    s.frameHit = false;
    if (s.state === "SCAN") {
      const near = dist2 < 25;
      const hit = near && Math.random() < 0.9;
      s.frameHit = hit;
      s.conf = clamp(s.conf + (hit ? GAIN : -DECAY));
      if (s.conf >= TAU) {
        s.sustain++;
        if (s.sustain >= K_SUSTAIN) {
          s.detT = now;
          s.geoloc = geolocate(s.target.x, s.target.z);
          s.orbitAngle = Math.atan2(s.pos.z - s.target.z, s.pos.x - s.target.x);
          setDetPoint(new THREE.Vector3(s.target.x, CFG.flyY, s.target.z));
          setState("TRACK");
        }
      } else {
        s.sustain = 0;
        if (!near && s.conf <= 0) setState("SEARCH");
      }
    }

    // ── in-scene callouts: confidence ring + detection ray (SCAN) ──
    if (ringRef.current) {
      const onScan = s.state === "SCAN" && showCallouts;
      ringRef.current.visible = onScan;
      if (onScan) {
        ringRef.current.position.set(s.target.x, 0.9, s.target.z);
        const fill = clamp(s.conf / TAU);
        const sc = 1.4 + fill * 1.1;
        ringRef.current.scale.set(sc, sc, sc);
        const mat = ringRef.current.material as THREE.MeshBasicMaterial;
        mat.opacity = 0.25 + fill * 0.6;
      }
    }
    if (rayRef.current) {
      const onScan = s.state === "SCAN" && showCallouts;
      rayRef.current.visible = onScan;
      if (onScan) {
        const from = s.pos.clone();
        const to = new THREE.Vector3(s.target.x, 0.9, s.target.z);
        const mid = from.clone().add(to).multiplyScalar(0.5);
        rayRef.current.position.copy(mid);
        const len = from.distanceTo(to);
        rayRef.current.scale.set(1, 1, len);
        rayRef.current.lookAt(to);
      }
    }

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

    if (sphereRef.current && s.state === "TRACK") {
      const mat = sphereRef.current.material as THREE.MeshStandardMaterial;
      const k = Math.min((rs.clock.getElapsedTime() - s.detT) / 2, 1);
      mat.emissiveIntensity = THREE.MathUtils.lerp(2.0, 0.3, k);
    }

    // ── throttled telemetry emit (~12 Hz) ──
    emitAcc.current += dt;
    if (emitAcc.current >= 0.08) {
      emitAcc.current = 0;
      onTelemetry({
        state: s.state,
        conf: s.conf,
        sustain: s.sustain,
        frameHit: s.frameHit,
        geoloc: s.state === "TRACK" ? s.geoloc : null,
      });
    }
  });

  const color = STATE_COLOR[state];
  const triangle = useMemo(() => {
    const shape = new THREE.Shape();
    shape.moveTo(0, -0.5);
    shape.lineTo(-0.35, 0.4);
    shape.lineTo(0.35, 0.4);
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

      {/* confidence ring (fills toward τ during SCAN) */}
      <mesh ref={ringRef} rotation={[-Math.PI / 2, 0, 0]} visible={false}>
        <ringGeometry args={[1.0, 1.18, 48]} />
        <meshBasicMaterial
          color={AZURE}
          transparent
          opacity={0}
          toneMapped={false}
          side={THREE.DoubleSide}
        />
      </mesh>

      {/* detection ray drone → candidate (SCAN) */}
      <group ref={rayRef} visible={false}>
        <mesh>
          <cylinderGeometry args={[0.03, 0.03, 1, 6]} />
          <meshBasicMaterial color={AZURE} transparent opacity={0.5} toneMapped={false} />
        </mesh>
      </group>

      <Trail width={0.3} length={20} color={color} attenuation={(w) => w}>
        <group ref={droneRef}>
          <mesh rotation={[-Math.PI / 2, 0, 0]}>
            <extrudeGeometry args={[triangle, { depth: 0.15, bevelEnabled: false }]} />
            <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.5} />
          </mesh>
        </group>
      </Trail>

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

export default function MissionCanvasPro({
  onTelemetry,
  showCallouts = true,
}: {
  onTelemetry: (t: Telemetry) => void;
  showCallouts?: boolean;
}) {
  return (
    <Canvas
      style={{ width: "100%", height: "100%" }}
      camera={{ position: [14, 14, 14], fov: 45 }}
      gl={{ alpha: true }}
      shadows={false}
    >
      <Scene onTelemetry={onTelemetry} showCallouts={showCallouts} />
      <EffectComposer>
        <Bloom luminanceThreshold={0.4} intensity={0.6} mipmapBlur />
      </EffectComposer>
    </Canvas>
  );
}
