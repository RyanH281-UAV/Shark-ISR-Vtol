"use client";

import { Canvas, useFrame } from "@react-three/fiber";
import {
  Grid,
  Html,
  Line,
  OrbitControls,
  useGLTF,
} from "@react-three/drei";
import { useEffect, useRef, useState, Suspense } from "react";
import * as THREE from "three";
import { Reveal } from "./Reveal";
import { hasWebGL, isCoarsePointer } from "@/lib/webgl";

const DRACO = "/draco/";
useGLTF.preload("/models/shark.min.glb", DRACO);

/**
 * Live miniature of the autonomy loop. The drone flies a real boustrophedon
 * over the swim zone; a shark wanders beneath the surface; when the drone's
 * sensor footprint crosses the shark, the sim transitions SEARCH → TRACK,
 * orbits the contact, then resumes the pattern — the same state machine the
 * real guidance node runs.
 */

// Boustrophedon waypoints over the patrol strip (mirrors search_pattern.py:
// shore-parallel legs, alternating direction, fixed lane spacing).
const LANES = [-1.9, -0.63, 0.63, 1.9];
const HALF = 4.2;
const WPS: [number, number][] = LANES.flatMap((z, i) => {
  const pair: [number, number][] =
    i % 2 === 0
      ? [
          [-HALF, z],
          [HALF, z],
        ]
      : [
          [HALF, z],
          [-HALF, z],
        ];
  return pair;
});

const ALT = 1.7;
const SPEED = 1.5; // world units / s
const DETECT_R = 1.25;
const ORBIT_R = 1.15;
const TRACK_S = 9;
const COOLDOWN_S = 7;

// total path length + segment table for constant-speed traversal
const SEGS = WPS.map((p, i) => {
  const q = WPS[(i + 1) % WPS.length];
  return Math.hypot(q[0] - p[0], q[1] - p[1]);
});
const TOTAL = SEGS.reduce((a, b) => a + b, 0);

function pathPos(dist: number): [number, number] {
  let d = dist % TOTAL;
  for (let i = 0; i < WPS.length; i++) {
    if (d <= SEGS[i]) {
      const p = WPS[i];
      const q = WPS[(i + 1) % WPS.length];
      const t = SEGS[i] === 0 ? 0 : d / SEGS[i];
      return [p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t];
    }
    d -= SEGS[i];
  }
  return WPS[0];
}

function Shark({ sharkRef }: { sharkRef: React.RefObject<THREE.Group | null> }) {
  const { scene } = useGLTF("/models/shark.min.glb", DRACO);
  const norm = useRef(false);
  if (!norm.current) {
    const box = new THREE.Box3().setFromObject(scene);
    const size = box.getSize(new THREE.Vector3());
    const centre = box.getCenter(new THREE.Vector3());
    const s = 1.4 / Math.max(size.x, size.y, size.z);
    scene.scale.setScalar(s);
    scene.position.copy(centre.multiplyScalar(-s));
    norm.current = true;
  }
  return (
    <group ref={sharkRef} position={[0, -0.32, 0]}>
      <primitive object={scene} />
    </group>
  );
}

function Drone({ droneRef }: { droneRef: React.RefObject<THREE.Group | null> }) {
  // Reuse the hero airframe (Meshy-textured), small.
  const { scene } = useGLTF("/models/hornet_textured.min.glb", DRACO);
  const clone = useRef<THREE.Object3D | null>(null);
  if (!clone.current) {
    clone.current = scene.clone(true);
    const box = new THREE.Box3().setFromObject(clone.current);
    const size = box.getSize(new THREE.Vector3());
    const centre = box.getCenter(new THREE.Vector3());
    const s = 0.85 / Math.max(size.x, size.y, size.z);
    clone.current.scale.setScalar(s);
    clone.current.position.copy(centre.multiplyScalar(-s));
  }
  return (
    <group ref={droneRef} position={[WPS[0][0], ALT, WPS[0][1]]}>
      <primitive object={clone.current} />
    </group>
  );
}

const TRAIL_N = 48;

function Sim({
  onMode,
  onHud,
}: {
  onMode: (m: string) => void;
  onHud: (coverage: number, contacts: number) => void;
}) {
  const droneRef = useRef<THREE.Group>(null);
  const sharkRef = useRef<THREE.Group>(null);
  const ringRef = useRef<THREE.Mesh>(null);
  const orbitRef = useRef<THREE.Mesh>(null);
  const trailRef = useRef<THREE.InstancedMesh>(null);
  const trail = useRef<THREE.Vector3[]>([]);
  const trailTick = useRef(0);
  const hudTick = useRef(0);
  const contacts = useRef(0);
  const mat4 = useRef(new THREE.Matrix4());
  const st = useRef({
    mode: "SEARCH" as "SEARCH" | "TRACK" | "COOLDOWN",
    dist: 0,
    until: 0,
    theta: 0,
    detectAt: -99,
  });

  useFrame((state, dt) => {
    if (document.hidden) return; // SITE_UPGRADE 3D rule
    const t = state.clock.elapsedTime;
    const s = st.current;
    const drone = droneRef.current;
    const shark = sharkRef.current;
    if (!drone || !shark) return;

    // shark wanders beneath the surface
    const sx = 2.6 * Math.sin(t * 0.11);
    const sz = 1.7 * Math.sin(t * 0.073 + 1.3);
    const heading = Math.atan2(
      2.6 * 0.11 * Math.cos(t * 0.11),
      1.7 * 0.073 * Math.cos(t * 0.073 + 1.3),
    );
    shark.position.set(sx, -0.32 + Math.sin(t * 0.5) * 0.04, sz);
    shark.rotation.y = heading;

    if (s.mode === "SEARCH" || s.mode === "COOLDOWN") {
      s.dist += SPEED * dt;
      const [x, z] = pathPos(s.dist);
      const [nx, nz] = pathPos(s.dist + 0.12);
      drone.position.set(x, ALT + Math.sin(t * 1.3) * 0.04, z);
      drone.rotation.y = Math.atan2(nx - x, nz - z);

      if (s.mode === "COOLDOWN" && t > s.until) s.mode = "SEARCH";
      if (
        s.mode === "SEARCH" &&
        Math.hypot(x - sx, z - sz) < DETECT_R
      ) {
        s.mode = "TRACK";
        s.until = t + TRACK_S;
        s.theta = Math.atan2(z - sz, x - sx);
        s.detectAt = t;
        contacts.current += 1;
        onMode("TRACK");
      }
    } else {
      // TRACK: orbit the shark, camera-facing tangent
      s.theta += dt * 0.9;
      const x = sx + ORBIT_R * Math.cos(s.theta);
      const z = sz + ORBIT_R * Math.sin(s.theta);
      drone.position.set(x, ALT - 0.25, z);
      drone.rotation.y = Math.atan2(sx - x, sz - z);
      if (t > s.until) {
        s.mode = "COOLDOWN";
        s.until = t + COOLDOWN_S;
        onMode("SEARCH");
      }
    }

    // swept trail: ring buffer of recent drone positions, shrinking with age
    trailTick.current += dt;
    if (trailTick.current > 0.12) {
      trailTick.current = 0;
      trail.current.push(drone.position.clone());
      if (trail.current.length > TRAIL_N) trail.current.shift();
    }
    if (trailRef.current) {
      const n = trail.current.length;
      for (let i = 0; i < TRAIL_N; i++) {
        if (i < n) {
          const pos = trail.current[i];
          const k = (i + 1) / n; // newest → 1
          mat4.current.makeScale(k, k, k);
          mat4.current.setPosition(pos.x, pos.y - 0.06, pos.z);
        } else {
          mat4.current.makeScale(0, 0, 0);
        }
        trailRef.current.setMatrixAt(i, mat4.current);
      }
      trailRef.current.instanceMatrix.needsUpdate = true;
    }

    // TRACK orbit ring around the contact
    if (orbitRef.current) {
      orbitRef.current.visible = s.mode === "TRACK";
      if (s.mode === "TRACK") {
        orbitRef.current.position.set(sx, ALT - 0.27, sz);
      }
    }

    // HUD telemetry ~4 Hz: lap coverage + contact count
    hudTick.current += dt;
    if (hudTick.current > 0.25) {
      hudTick.current = 0;
      onHud(Math.min(1, (s.dist % TOTAL) / TOTAL), contacts.current);
    }

    // detection ping ring
    if (ringRef.current) {
      const age = t - s.detectAt;
      const vis = age < 2.5;
      ringRef.current.visible = vis;
      if (vis) {
        const k = age / 2.5;
        ringRef.current.position.set(sx, 0.02, sz);
        ringRef.current.scale.setScalar(0.3 + k * 2.2);
        (ringRef.current.material as THREE.MeshBasicMaterial).opacity =
          0.7 * (1 - k);
      }
    }
  });

  return (
    <>
      <Drone droneRef={droneRef} />
      <Suspense fallback={null}>
        <Shark sharkRef={sharkRef} />
      </Suspense>
      <mesh ref={ringRef} rotation={[-Math.PI / 2, 0, 0]} visible={false}>
        <ringGeometry args={[0.9, 1, 48]} />
        {/* detection event = amber per the state token system */}
        <meshBasicMaterial color="#e8a33d" transparent opacity={0.7} />
      </mesh>
      {/* standoff orbit ring while tracking */}
      <mesh ref={orbitRef} rotation={[-Math.PI / 2, 0, 0]} visible={false}>
        <ringGeometry args={[ORBIT_R - 0.02, ORBIT_R + 0.02, 64]} />
        <meshBasicMaterial color="#e8a33d" transparent opacity={0.35} />
      </mesh>
      {/* swept-coverage trail */}
      <instancedMesh ref={trailRef} args={[undefined, undefined, TRAIL_N]}>
        <sphereGeometry args={[0.05, 8, 8]} />
        <meshBasicMaterial color="#45b8ac" transparent opacity={0.35} />
      </instancedMesh>
    </>
  );
}

export default function Mission3D() {
  const [mode, setMode] = useState("SEARCH");
  const [hud, setHud] = useState({ coverage: 0, contacts: 0 });
  const [webgl, setWebgl] = useState(true);
  const [coarse, setCoarse] = useState(false);
  useEffect(() => {
    setWebgl(hasWebGL());
    setCoarse(isCoarsePointer());
  }, []);

  return (
    <section className="mx-auto max-w-6xl px-6 pb-28">
      <Reveal className="mb-8 max-w-2xl">
        <p className="mb-3 font-mono text-xs tracking-[0.3em] text-search-ink">
          LIVE SIMULATION
        </p>
        <h3 className="font-display text-3xl font-semibold uppercase leading-[0.95] tracking-tight sm:text-4xl">
          Watch the loop run.
        </h3>
        <p className="mt-3 leading-relaxed text-mute">
          The same state machine the guidance node flies: a shore-parallel
          search pattern until the sensor footprint crosses a shark, then an
          observation orbit, then back to the pattern. Drag to look around.
        </p>
      </Reveal>

      <Reveal className="relative overflow-hidden rounded border border-lined bg-navy">
        <div className="h-[520px] cursor-grab active:cursor-grabbing">
          {!webgl && (
            // static fallback: same information, no Canvas dependency
            <div className="flex h-full flex-col items-center justify-center gap-4 px-8 text-center">
              <p className="font-mono text-xs tracking-[0.3em] text-search">
                SEARCH → TRACK LOOP
              </p>
              <p className="max-w-md text-sm leading-relaxed text-muted">
                The aircraft sweeps four shore-parallel lanes at patrol
                altitude. When the sensor footprint crosses a shark, guidance
                transitions to TRACK, orbits the contact at standoff radius,
                then resumes the sweep where it left off.
              </p>
              <p className="font-mono text-[11px] tracking-widest text-muted">
                SEARCH <span className="text-search">━━━</span> DETECT{" "}
                <span className="text-track">◉</span> TRACK{" "}
                <span className="text-track">⟳</span> RESUME
              </p>
            </div>
          )}
          {webgl && (
          <Canvas
            camera={{ position: [6.5, 5.2, 7], fov: 40 }}
            dpr={[1, 2]}
            onCreated={({ gl }) => {
              gl.toneMapping = THREE.ACESFilmicToneMapping;
            }}
          >
            <ambientLight intensity={0.45} />
            <directionalLight position={[5, 8, 3]} intensity={1.8} color="#eef2ff" />
            <directionalLight position={[-5, 3, -4]} intensity={0.9} color="#45b8ac" />

            {/* water surface — shark ghosts beneath it */}
            <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]}>
              <planeGeometry args={[13, 8]} />
              <meshStandardMaterial
                color="#0d2237"
                transparent
                opacity={0.72}
                roughness={0.25}
                metalness={0.1}
              />
            </mesh>
            <Grid
              position={[0, 0.01, 0]}
              args={[13, 8]}
              cellColor="#1b3350"
              sectionColor="#24425f"
              fadeDistance={22}
              fadeStrength={2}
            />

            {/* patrol path */}
            <Line
              points={WPS.map(([x, z]) => [x, ALT - 0.02, z])}
              color="#45b8ac"
              lineWidth={1}
              transparent
              opacity={0.5}
            />

            <Suspense
              fallback={
                <Html center>
                  <p className="whitespace-nowrap font-mono text-xs tracking-[0.3em] text-muted">
                    LOADING SCENARIO…
                  </p>
                </Html>
              }
            >
              <Sim onMode={setMode} onHud={(coverage, contacts) => setHud({ coverage, contacts })} />
            </Suspense>

            <fog attach="fog" args={["#0b1e33", 14, 26]} />
            <OrbitControls
              enablePan={false}
              enableZoom={false}
              minPolarAngle={0.4}
              maxPolarAngle={1.25}
              autoRotate
              autoRotateSpeed={0.4}
              enabled={!coarse}
            />
          </Canvas>
          )}
        </div>

        {/* HUD */}
        <div className="pointer-events-none absolute inset-x-5 top-4 flex items-center justify-between font-mono text-[11px] tracking-widest">
          <span className="text-muted">
            GUIDANCE{" "}
            <span className={mode === "TRACK" ? "text-track" : "text-search"}>
              {mode}
            </span>
          </span>
          <span className="hidden text-muted sm:block">
            LAP {Math.round(hud.coverage * 100)}% · CONTACTS {hud.contacts}
          </span>
          <span className="flex items-center gap-2 text-muted">
            <span
              className={`inline-block h-1.5 w-1.5 rounded-full ${
                mode === "TRACK" ? "bg-track motion-safe:animate-pulse" : "bg-search"
              }`}
            />
            {mode === "TRACK" ? "CONTACT · ORBITING" : "PATTERN · SWEEPING"}
          </span>
        </div>
      </Reveal>
    </section>
  );
}
