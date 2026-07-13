"use client";

import Image from "next/image";
import {
  Radar,
  Crosshair,
  Orbit,
  Cpu,
  Camera,
  CircuitBoard,
  Plane,
  ShieldCheck,
  CheckCircle2,
} from "lucide-react";
import { Reveal, Stagger, Item, Counter } from "./Reveal";

/* ── Mission: the autonomy loop ──────────────────────────────────────────── */

const PHASES = [
  {
    icon: Radar,
    tag: "01 — SEARCH",
    state: "text-search-ink",
    bar: "bg-search",
    title: "Persistent patrol, not a one-shot sweep",
    body: "Shore-parallel lawnmower legs over a Bayesian probability map, threat-weighted so the water nearest swimmers is revisited most. A hard revisit bound guarantees no cell goes stale — probability re-grows where a shark could have moved in.",
  },
  {
    icon: Crosshair,
    tag: "02 — DETECT",
    state: "text-track-ink",
    bar: "bg-track",
    title: "Confidence-gated, onboard",
    body: "YOLOv8n compiled to a Hailo .hef runs on the aircraft's 13-TOPS NPU. Detections accumulate confidence across frames and decay on misses; one lucky frame never flies the aircraft. Each hit is geolocated by pinhole ray-casting to the water surface.",
  },
  {
    icon: Orbit,
    tag: "03 — TRACK",
    state: "text-track-ink",
    bar: "bg-track",
    title: "Orbit-on-detect, logged and geolocated",
    body: "A sustained threshold crossing triggers the autonomous SEARCH → TRACK transition: the VTOL banks into a standoff observation orbit around the detection, logging geolocated fixes — then returns to the patrol when the track times out.",
  },
];

export function Mission() {
  return (
    <section id="mission" className="mx-auto max-w-6xl px-6 py-28">
      {/* asymmetric header: display left, argument right */}
      <div className="mb-16 grid items-end gap-8 lg:grid-cols-[1.2fr_1fr]">
        <Reveal>
          <h2 className="font-display text-5xl font-semibold uppercase leading-[0.95] tracking-tight sm:text-6xl">
            Patrol. Detect.
            <br />
            <span className="text-search-ink">Track.</span> Repeat.
          </h2>
        </Reveal>
        <Reveal delay={0.1}>
          <p className="border-l-2 border-search pl-5 leading-relaxed text-mute">
            Small drones already fly search patterns. The gap this system
            closes is the <em className="font-serif italic">decision</em> — the
            aircraft transitions between behaviours itself, gated on onboard
            detection confidence.
          </p>
        </Reveal>
      </div>

      <Stagger className="grid gap-px overflow-hidden rounded border border-line bg-line md:grid-cols-3">
        {PHASES.map((p) => (
          <Item key={p.tag} className="group relative bg-card p-7">
            <span
              aria-hidden
              className={`absolute left-0 top-0 h-1 w-full ${p.bar}`}
            />
            <p.icon
              className={`mb-5 h-7 w-7 ${p.state} transition-transform duration-300 group-hover:-translate-y-1`}
              aria-hidden
            />
            <p className={`mb-2 font-mono text-[11px] tracking-[0.25em] ${p.state}`}>
              {p.tag}
            </p>
            <h3 className="font-display mb-3 text-xl font-semibold uppercase tracking-tight">
              {p.title}
            </h3>
            <p className="text-sm leading-relaxed text-mute">{p.body}</p>
          </Item>
        ))}
      </Stagger>
    </section>
  );
}

/* ── Detector: the numbers ───────────────────────────────────────────────── */

const METRICS = [
  { value: 0.945, decimals: 3, suffix: "", label: "mAP50", note: "223 held-out images" },
  { value: 0.742, decimals: 3, suffix: "", label: "mAP50-95", note: "held-out test set" },
  { value: 95, decimals: 0, suffix: "%", label: "Recall", note: "the mission metric" },
  { value: 89, decimals: 0, suffix: "%", label: "Precision", note: "51 open-water hard negatives" },
];

export function Detector() {
  return (
    <section id="detector" className="border-y border-line bg-card">
      <div className="mx-auto max-w-6xl px-6 py-28">
        <div className="grid items-start gap-12 lg:grid-cols-[1fr_1.15fr]">
          {/* sticky editorial rail */}
          <div className="lg:sticky lg:top-28">
            <Reveal>
              <p className="mb-3 font-mono text-xs tracking-[0.3em] text-track-ink">
                PERCEPTION · DETECTION EVENTS
              </p>
              <h2 className="font-display text-4xl font-semibold uppercase leading-[0.95] tracking-tight sm:text-5xl">
                A detector scored
                <br />
                the honest way
              </h2>
              <p className="mt-5 leading-relaxed text-mute">
                Fine-tuned on 3,261 aerial images from four datasets with a
                group-disjoint split — augmentation siblings and video frames
                can never straddle train and test. Every number here comes from
                images the model has never seen.
              </p>
              <p className="mt-6 max-w-sm font-serif text-xl italic leading-snug text-ink">
                Recall is the mission metric: a missed shark is the operational
                failure. A false positive costs one extra orbit.
              </p>
            </Reveal>
          </div>

          <div>
            <Stagger className="grid grid-cols-2 gap-px overflow-hidden rounded border border-line bg-line">
              {METRICS.map((m) => (
                <Item key={m.label} className="bg-paper p-6">
                  <p className="font-mono text-3xl font-medium text-ink">
                    <Counter to={m.value} decimals={m.decimals} suffix={m.suffix} />
                  </p>
                  <p className="mt-1 font-mono text-xs tracking-wider text-track-ink">
                    {m.label.toUpperCase()}
                  </p>
                  <p className="mt-1 text-xs text-mute">{m.note}</p>
                </Item>
              ))}
            </Stagger>
            <Reveal delay={0.15} className="mt-6">
              <figure className="overflow-hidden rounded border border-line">
                <Image
                  src="/img/detections.jpg"
                  alt="YOLOv8n predictions on held-out aerial frames — sharks flagged at 0.4–0.9 confidence"
                  width={1280}
                  height={960}
                  className="w-full object-cover"
                  sizes="(min-width: 1024px) 55vw, 100vw"
                />
                <figcaption className="border-t border-line bg-paper px-5 py-3 font-mono text-xs text-mute">
                  HELD-OUT FRAMES · SHARKS FLAGGED 0.4–0.9 CONF · OPEN WATER IGNORED
                </figcaption>
              </figure>
            </Reveal>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ── Hardware ────────────────────────────────────────────────────────────── */

const HW = [
  {
    icon: Plane,
    name: "Titan Dynamics Hornet",
    spec: "1.1 m tri-tiltrotor VTOL · 2.5 kg MTOW · 50–75 kph cruise · L/D 22 · 2.2 Wh/km",
  },
  {
    icon: Cpu,
    name: "Raspberry Pi 5 + AI HAT+",
    spec: "Hailo-8L NPU, 13 TOPS INT8 over PCIe Gen 3 — full detector inference onboard",
  },
  {
    icon: Camera,
    name: "Camera Module 3",
    spec: "Sony IMX708, nadir-mounted through the nose aperture, libcamera/picamera2 ingest",
  },
  {
    icon: CircuitBoard,
    name: "Pixhawk 6C Mini · PX4",
    spec: "Owns the inner loop, the tilt transition and every failsafe · uXRCE-DDS to ROS 2",
  },
];

export function Hardware() {
  return (
    <section id="hardware" className="mx-auto max-w-6xl px-6 py-28">
      <Reveal className="mb-12 max-w-2xl">
        <p className="mb-3 font-mono text-xs tracking-[0.3em] text-transit-ink">
          AIRFRAME + PAYLOAD
        </p>
        <h2 className="font-display text-4xl font-semibold uppercase leading-[0.95] tracking-tight sm:text-5xl">
          Everything it needs,
          <br />
          nothing it can&apos;t lift
        </h2>
      </Reveal>
      <div className="grid items-start gap-10 lg:grid-cols-5">
        <Reveal className="lg:col-span-3">
          <figure className="overflow-hidden rounded border border-line bg-card">
            <Image
              src="/img/stack-installed.jpg"
              alt="Autonomy stack — Pi 5, AI HAT+, Camera Module 3 and Pixhawk 6C Mini installed in the Hornet fuselage"
              width={1600}
              height={1200}
              className="w-full object-cover"
              sizes="(min-width: 1024px) 60vw, 100vw"
            />
            <figcaption className="border-t border-line px-5 py-3 font-mono text-xs text-mute">
              THE STACK INSTALLED · CAMERA DOWN THROUGH THE NOSE · 2.5 KG MTOW BUDGET
            </figcaption>
          </figure>
        </Reveal>
        <Stagger className="flex flex-col gap-px overflow-hidden rounded border border-line bg-line lg:col-span-2">
          {HW.map((h) => (
            <Item key={h.name} className="flex gap-4 bg-card p-5">
              <h.icon className="mt-0.5 h-6 w-6 shrink-0 text-transit-ink" aria-hidden />
              <div>
                <h3 className="font-display text-base font-semibold uppercase tracking-tight">
                  {h.name}
                </h3>
                <p className="mt-1 text-sm leading-relaxed text-mute">{h.spec}</p>
              </div>
            </Item>
          ))}
        </Stagger>
      </div>
    </section>
  );
}

/* ── Safety: the responsibility boundary ─────────────────────────────────── */

export function Safety() {
  return (
    <section id="safety" className="border-y border-line bg-card">
      <div className="mx-auto max-w-6xl px-6 py-28">
        <div className="grid items-center gap-12 lg:grid-cols-2">
          <div>
            <Reveal>
              <p className="mb-3 font-mono text-xs tracking-[0.3em] text-rtl-ink">
                FAILSAFE · RTL
              </p>
              <h2 className="font-display text-4xl font-semibold uppercase leading-[0.95] tracking-tight sm:text-5xl">
                The companion computer cannot crash the aircraft
              </h2>
              <p className="mt-5 leading-relaxed text-mute">
                The responsibility boundary <em className="font-serif italic">is</em>{" "}
                the design. PX4 owns the inner loop, the hover-to-cruise tilt
                transition and every failsafe — ROS 2 can only ask. If the
                companion computer, the link or the software stack fails
                entirely, the autopilot degrades to return-to-launch on its
                own. Verified in SITL: kill the bridge process mid-flight and
                PX4 exits Offboard within its configured loss window.
              </p>
            </Reveal>
            <Stagger className="mt-8 flex flex-col gap-3">
              {[
                "PX4: inner loop · tilt transition · RTL, battery and link failsafes",
                "ROS 2: mission, guidance, perception, telemetry — outer loop only",
                "One package (shark_isr_autopilot) is the sole PX4 boundary",
                "Seven frozen interfaces, frames and units explicit on every field",
              ].map((line) => (
                <Item key={line} className="flex items-start gap-3">
                  <ShieldCheck
                    className="mt-0.5 h-5 w-5 shrink-0 text-rtl-ink"
                    aria-hidden
                  />
                  <p className="text-sm text-mute">{line}</p>
                </Item>
              ))}
            </Stagger>
          </div>
          <Reveal delay={0.2}>
            <figure className="overflow-hidden rounded border border-line">
              <Image
                src="/img/full_front.jpg"
                alt="Hornet VTOL head-on, front tilt rotors vertical"
                width={1200}
                height={900}
                className="w-full object-cover"
                sizes="(min-width: 1024px) 50vw, 100vw"
              />
            </figure>
          </Reveal>
        </div>
      </div>
    </section>
  );
}

/* ── Proof: SITL verification ────────────────────────────────────────────── */

const TESTS = [
  ["T06", "Orbit setpoint geometry", "20/20 setpoints on the 30 m circle — min = max = mean = 30.00 m"],
  ["T07", "Companion death failsafe", "Bridge killed mid-flight → PX4 exits Offboard on its own"],
  ["T08", "Abort → RTL", "CMD_ABORT drives PX4 into return-to-launch"],
  ["T09", "Low-battery failsafe", "Threshold crossing triggers autonomous return"],
  ["T10", "End-to-end rehearsal", "START → ARM → SEARCH → detection → TRACK → RETURN"],
  ["T11", "Perception pipeline", "Camera → detector → guidance TRACK, no test injection"],
];

export function Proof() {
  return (
    <section id="proof" className="mx-auto max-w-6xl px-6 py-28">
      <div className="mb-12 flex flex-wrap items-end justify-between gap-6">
        <Reveal>
          <p className="mb-3 font-mono text-xs tracking-[0.3em] text-search-ink">
            SITL · PX4 + GAZEBO · SIMULATED COTTESLOE BEACH
          </p>
          <h2 className="font-display max-w-xl text-4xl font-semibold uppercase leading-[0.95] tracking-tight sm:text-5xl">
            No code touches the aircraft before SITL says yes
          </h2>
        </Reveal>
        <Reveal delay={0.1}>
          <p className="font-mono text-sm text-search-ink">6 / 6 PASS</p>
        </Reveal>
      </div>
      <Stagger className="overflow-hidden rounded border border-line">
        {TESTS.map(([id, name, desc]) => (
          <Item
            key={id}
            className="flex items-center gap-5 border-b border-line bg-card px-6 py-4 last:border-b-0"
          >
            <span className="font-mono text-xs text-mute">{id}</span>
            <span className="font-display min-w-44 text-base font-semibold uppercase tracking-tight">
              {name}
            </span>
            <span className="hidden flex-1 text-sm text-mute md:block">{desc}</span>
            <CheckCircle2
              className="ml-auto h-5 w-5 shrink-0 text-search-ink"
              aria-label="pass"
            />
          </Item>
        ))}
      </Stagger>
    </section>
  );
}

/* ── CTA + footer ────────────────────────────────────────────────────────── */

export function Footer() {
  return (
    <footer className="bg-navy">
      <div className="mx-auto max-w-6xl px-6 py-24 text-center">
        <Reveal>
          <p className="mb-3 font-mono text-xs tracking-[0.3em] text-search">
            SHARK MONITORING IS THE APPLICATION
          </p>
          <h2 className="font-display mx-auto max-w-2xl text-4xl font-semibold uppercase leading-[0.95] tracking-tight text-fgd sm:text-5xl">
            The engineering is persistent ISR autonomy.
          </h2>
          <p className="mx-auto mt-5 max-w-xl font-serif text-lg italic text-muted">
            Search-and-rescue, marine survey, coastal patrol — the
            detection-gated guidance loop is domain-agnostic. The detector is a
            config choice.
          </p>
          <div className="mt-8 flex justify-center gap-4">
            <a
              href="https://github.com/RyanH281-UAV/Shark-ISR-Vtol"
              className="rounded bg-search px-6 py-3 font-mono text-xs font-medium tracking-wider text-navy transition-colors duration-200 hover:bg-search/85"
            >
              READ THE SOURCE
            </a>
            <a
              href="mailto:ryanhughes281@yahoo.com"
              className="rounded border border-lined px-6 py-3 font-mono text-xs font-medium tracking-wider text-fgd transition-colors duration-200 hover:border-search/60 hover:text-search"
            >
              GET IN TOUCH
            </a>
          </div>
        </Reveal>
        <p className="mt-16 font-mono text-xs text-muted">
          ROS 2 HUMBLE · PX4 uXRCE-DDS · HAILO-8L · BUILT BY RYAN HUGHES · FLIGHT CAMPAIGN PENDING
        </p>
      </div>
    </footer>
  );
}
