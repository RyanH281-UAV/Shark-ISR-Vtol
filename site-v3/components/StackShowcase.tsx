"use client";

import Image from "next/image";
import { Canvas, useFrame } from "@react-three/fiber";
import { Html, Line, OrbitControls, useGLTF } from "@react-three/drei";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import { motion, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState, Suspense } from "react";
import * as THREE from "three";
import {
  Camera,
  Cpu,
  Zap,
  CircuitBoard,
  BatteryCharging,
  ArrowRight,
} from "lucide-react";
import { Reveal } from "./Reveal";
import { hasWebGL, isCoarsePointer } from "@/lib/webgl";

const BOARDS = [
  {
    id: "cam",
    icon: Camera,
    name: "Camera Module 3",
    short: "Sony IMX708 · CSI-2 · nadir mount",
    role: "THE EYE",
    flow: 0,
    specs: [
      ["Sensor", "Sony IMX708, 12 MP"],
      ["Mount", "Nadir, through the nose aperture"],
      ["Ingest", "libcamera → picamera2 → ROS 2 Image"],
      ["Geometry", "~66° diagonal FOV · pinhole geolocation"],
    ],
    detail:
      "Every frame is ray-cast through the camera intrinsics and the aircraft attitude to the water surface — each detection leaves the aircraft already geolocated to a lat/lon.",
  },
  {
    id: "npu",
    icon: Zap,
    name: "AI HAT+ · Hailo-8L",
    short: "13 TOPS INT8 · PCIe Gen 3",
    role: "THE DETECTOR",
    flow: 1,
    specs: [
      ["NPU", "Hailo-8L, 13 TOPS INT8"],
      ["Link", "PCIe Gen 3 to the Pi 5"],
      ["Model", "YOLOv8n fine-tune, compiled to .hef"],
      ["Scored", "0.945 mAP50 · 95% recall, held-out"],
    ],
    detail:
      "Inference happens on the aircraft. Losing every radio link costs situational awareness — never autonomy. There is no video downlink in the decision loop.",
  },
  {
    id: "pi",
    icon: Cpu,
    name: "Raspberry Pi 5",
    short: "ROS 2 Humble · the outer loop",
    role: "THE BRAIN",
    flow: 2,
    specs: [
      ["Compute", "Quad-core Cortex-A76"],
      ["Stack", "7 ROS 2 packages, one responsibility each"],
      ["Transport", "uXRCE-DDS agent to PX4"],
      ["Guidance", "Bayesian search map · SEARCH→TRACK state machine"],
    ],
    detail:
      "Mission, guidance, perception, telemetry — the decisions. Architecturally incapable of overriding a failsafe: it can only ask the autopilot, never command the inner loop.",
  },
  {
    id: "fc",
    icon: CircuitBoard,
    name: "Pixhawk 6C Mini",
    short: "PX4 · inner loop + failsafes",
    role: "THE PILOT",
    flow: 3,
    specs: [
      ["Firmware", "PX4 v1.16"],
      ["Owns", "Attitude, tilt transition, every failsafe"],
      ["Failsafe", "Companion death → RTL, SITL-verified (T07)"],
      ["Link", "uXRCE-DDS over serial"],
    ],
    detail:
      "The safety boundary. Kill the companion computer mid-flight and PX4 exits Offboard on its own and brings the aircraft home. Verified by killing the bridge process in SITL.",
  },
  {
    id: "pwr",
    icon: BatteryCharging,
    name: "Power",
    short: "6S Li-ion · energy is the binding resource",
    role: "THE BUDGET",
    flow: -1,
    specs: [
      ["Pack", "6S2P 21700 Li-ion, 8400 mAh"],
      ["Cruise", "2.2 Wh/km at best-L/D"],
      ["Ceiling", "2.5 kg MTOW — payload competes with battery"],
      ["Discipline", "Every board above earns its watts"],
    ],
    detail:
      "The whole stack is sized against endurance. Loiter near best lift-to-drag, minimise compute draw, and the search feasibility maths (loop time vs revisit bound vs endurance) is checked before launch.",
  },
] as const;

const FLOW = ["FRAMES", "DETECTIONS", "SETPOINTS"];

// fly-to poses per board: [camera position], [look-at / annotation anchor].
// Local coords after the model is normalised to ~3.4 units. Tune by eye.
const POSES: Record<string, { cam: [number, number, number]; target: [number, number, number] }> = {
  cam: { cam: [2.4, 0.5, 2.6], target: [0.3, -0.5, 0.5] },
  npu: { cam: [1.6, 2.6, 1.8], target: [0, 0.35, 0] },
  pi: { cam: [2.9, 1.1, 0.4], target: [0, -0.05, 0] },
  fc: { cam: [-2.3, 1.5, 2.1], target: [-0.4, 0, 0.2] },
  pwr: { cam: [0.4, 0.9, 3.2], target: [0, -0.55, 0] },
};

/** Damped camera fly-to when the selected board changes; hands control back
 *  to OrbitControls after the move settles. */
function CameraRig({
  boardId,
  role,
  controls,
}: {
  boardId: string;
  role: string;
  controls: React.RefObject<OrbitControlsImpl | null>;
}) {
  const focusUntil = useRef(0);
  const prev = useRef(boardId);

  useFrame((state, dt) => {
    if (document.hidden) return; // SITE_UPGRADE 3D rule
    if (prev.current !== boardId) {
      prev.current = boardId;
      focusUntil.current = state.clock.elapsedTime + 1.6;
    }
    if (state.clock.elapsedTime > focusUntil.current) return;
    const pose = POSES[boardId];
    const ctl = controls.current;
    if (!pose || !ctl) return;
    const d = (a: number, b: number) => THREE.MathUtils.damp(a, b, 5, dt);
    state.camera.position.set(
      d(state.camera.position.x, pose.cam[0]),
      d(state.camera.position.y, pose.cam[1]),
      d(state.camera.position.z, pose.cam[2]),
    );
    ctl.target.set(
      d(ctl.target.x, pose.target[0]),
      d(ctl.target.y, pose.target[1]),
      d(ctl.target.z, pose.target[2]),
    );
    ctl.update();
  });

  const pose = POSES[boardId];
  if (!pose) return null;
  const [ax, ay, az] = pose.target;
  return (
    <group>
      {/* annotation: pulsing anchor + leader line + role tag */}
      <mesh position={[ax, ay, az]}>
        <sphereGeometry args={[0.035, 16, 16]} />
        <meshBasicMaterial color="#45b8ac" />
      </mesh>
      <Line
        points={[
          [ax, ay, az],
          [ax, ay + 0.55, az],
        ]}
        color="#45b8ac"
        lineWidth={1}
        transparent
        opacity={0.7}
      />
      <Html position={[ax, ay + 0.62, az]} center distanceFactor={6}>
        <span className="whitespace-nowrap rounded border border-search/60 bg-navy/85 px-2 py-0.5 font-mono text-[10px] tracking-[0.2em] text-search backdrop-blur-sm">
          {role}
        </span>
      </Html>
    </group>
  );
}

const DRACO = "/draco/";

function StackModel() {
  const { scene } = useGLTF("/models/stack.min.glb", DRACO);
  const norm = useRef(false);
  if (!norm.current) {
    const box = new THREE.Box3().setFromObject(scene);
    const size = box.getSize(new THREE.Vector3());
    const centre = box.getCenter(new THREE.Vector3());
    const s = 3.4 / Math.max(size.x, size.y, size.z);
    scene.scale.setScalar(s);
    scene.position.copy(centre.multiplyScalar(-s));
    norm.current = true;
  }
  return <primitive object={scene} />;
}

useGLTF.preload("/models/stack.min.glb", DRACO);

export default function StackShowcase() {
  const [active, setActive] = useState<(typeof BOARDS)[number]>(BOARDS[2]);
  const reduce = useReducedMotion();
  const [webgl, setWebgl] = useState(true);
  const [coarse, setCoarse] = useState(false);
  const [touched, setTouched] = useState(false);
  const controls = useRef<OrbitControlsImpl | null>(null);
  useEffect(() => {
    setWebgl(hasWebGL());
    setCoarse(isCoarsePointer());
  }, []);

  return (
    <section id="stack" className="mx-auto max-w-6xl px-6 py-28">
      <div>
        <Reveal className="mb-14 max-w-2xl">
          <p className="mb-3 font-mono text-xs tracking-[0.3em] text-search-ink">
            THE ELECTRONICS
          </p>
          <h2 className="font-display text-4xl font-semibold uppercase leading-[0.95] tracking-tight sm:text-5xl">
            Five boards.
            <br />
            One decision loop.
          </h2>
          <p className="mt-4 leading-relaxed text-mute">
            Frames become detections, detections become setpoints — all inside
            the fuselage. Select a board to see what it owns.
          </p>
        </Reveal>

        <div className="grid items-start gap-10 lg:grid-cols-2">
          {/* interactive 3D stack — Meshy image-to-3D from the real hardware photo */}
          <Reveal>
            <figure className="relative">
              <div
                aria-hidden
                className="absolute inset-x-8 bottom-8 h-16 rounded-[50%] bg-search/25 blur-3xl"
              />
              <div className="relative h-[380px] cursor-grab overflow-hidden rounded border border-lined bg-navy active:cursor-grabbing">
                {!webgl && (
                  <Image
                    src="/img/stack_cutout.png"
                    alt="The assembled autonomy stack — Pi 5, AI HAT+, Camera Module 3, Pixhawk 6C Mini"
                    fill
                    className="object-contain p-6"
                    sizes="(min-width: 1024px) 50vw, 100vw"
                  />
                )}
                {webgl && (
                <Canvas
                  camera={{ position: [0, 1.6, 4.4], fov: 40 }}
                  dpr={[1, 2]}
                  onCreated={({ gl }) => {
                    gl.toneMapping = THREE.ACESFilmicToneMapping;
                  }}
                >
                  <ambientLight intensity={0.5} />
                  <directionalLight position={[4, 6, 4]} intensity={2} color="#eef2ff" />
                  <directionalLight position={[-5, 2, -4]} intensity={1.1} color="#45b8ac" />
                  <Suspense
                    fallback={
                      <Html center>
                        <Image
                          src="/img/stack_cutout.png"
                          alt="The assembled autonomy stack"
                          width={420}
                          height={315}
                          className="opacity-70"
                        />
                      </Html>
                    }
                  >
                    <StackModel />
                  </Suspense>
                  <CameraRig boardId={active.id} role={active.role} controls={controls} />
                  <OrbitControls
                    ref={controls}
                    enablePan={false}
                    enableZoom={false}
                    minPolarAngle={0.5}
                    maxPolarAngle={1.5}
                    autoRotate={!reduce && !touched}
                    autoRotateSpeed={0.8}
                    enabled={!coarse}
                  />
                </Canvas>
                )}
              </div>
              <figcaption className="mt-2 text-center font-mono text-[11px] tracking-widest text-mute">
                THE STACK · SCANNED FROM THE FLOWN HARDWARE · DRAG TO INSPECT
              </figcaption>
            </figure>

            {/* signal flow */}
            <div className="mt-8 rounded border border-line bg-card p-5">
              <div className="flex items-center justify-between gap-1">
                {BOARDS.filter((b) => b.flow >= 0).map((b, i, arr) => (
                  <div key={b.id} className="flex flex-1 items-center gap-1">
                    <button
                      onClick={() => {
                        setActive(b);
                        setTouched(true);
                      }}
                      className={`cursor-pointer rounded border px-2.5 py-2 font-mono text-[10px] tracking-wider transition-colors duration-200 ${
                        active.id === b.id
                          ? "border-accent bg-search/10 text-ink"
                          : "border-line text-mute hover:border-search/60 hover:text-ink"
                      }`}
                    >
                      {b.role}
                    </button>
                    {i < arr.length - 1 && (
                      <div className="relative min-w-6 flex-1 overflow-hidden">
                        <div className="h-px w-full bg-line" />
                        {!reduce && (
                          <span
                            className="absolute top-1/2 h-[3px] w-[3px] -translate-y-1/2 rounded-full bg-accent-2"
                            style={{
                              animation: `flow 2.4s linear ${i * 0.8}s infinite`,
                            }}
                          />
                        )}
                        <span className="absolute -top-3.5 left-1/2 hidden -translate-x-1/2 font-mono text-[8px] tracking-widest text-mute sm:block">
                          {FLOW[i]}
                        </span>
                      </div>
                    )}
                  </div>
                ))}
              </div>
              <style>{`@keyframes flow { from { left: 0% } to { left: 100% } }`}</style>
            </div>
          </Reveal>

          {/* board selector + detail */}
          <div>
            <div className="flex flex-col gap-2" role="tablist" aria-label="Stack components">
              {BOARDS.map((b) => (
                <button
                  key={b.id}
                  role="tab"
                  aria-selected={active.id === b.id}
                  onClick={() => {
                    setActive(b);
                    setTouched(true);
                  }}
                  className={`flex cursor-pointer items-center gap-4 rounded border px-5 py-3.5 text-left transition-colors duration-200 ${
                    active.id === b.id
                      ? "border-search bg-card"
                      : "border-line bg-transparent hover:border-search/50 hover:bg-card"
                  }`}
                >
                  <b.icon
                    className={`h-5 w-5 shrink-0 transition-colors duration-200 ${
                      active.id === b.id ? "text-search-ink" : "text-mute"
                    }`}
                    aria-hidden
                  />
                  <span className="flex-1">
                    <span className="font-display block text-sm font-semibold">
                      {b.name}
                    </span>
                    <span className="block text-xs text-mute">{b.short}</span>
                  </span>
                  <ArrowRight
                    className={`h-4 w-4 transition-all duration-200 ${
                      active.id === b.id
                        ? "translate-x-0 text-search-ink opacity-100"
                        : "-translate-x-1 opacity-0"
                    }`}
                    aria-hidden
                  />
                </button>
              ))}
            </div>

            <motion.div
              key={active.id}
              initial={reduce ? { opacity: 0 } : { opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
              className="mt-4 rounded border border-line bg-card p-6"
            >
              <p className="mb-3 font-mono text-[10px] tracking-[0.3em] text-search-ink">
                {active.role}
              </p>
              <dl className="grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2">
                {active.specs.map(([k, v]) => (
                  <div key={k} className="flex flex-col border-b border-line/60 pb-2">
                    <dt className="font-mono text-[10px] tracking-widest text-mute">
                      {k.toUpperCase()}
                    </dt>
                    <dd className="text-sm text-ink">{v}</dd>
                  </div>
                ))}
              </dl>
              <p className="mt-4 text-sm leading-relaxed text-mute">
                {active.detail}
              </p>
            </motion.div>
          </div>
        </div>
      </div>
    </section>
  );
}
