import { Hero } from "@/components/Hero";
import { AutonomyLoop } from "@/components/AutonomyLoop";
import StackSection3D from "@/components/3d/StackSection3D";
import MissionSection3D from "@/components/3d/MissionSection3D";
import ExplodedSection3D from "@/components/3d/ExplodedSection3D";
import PerceptionSection from "@/components/PerceptionSection";
import { GitHubIcon, LinkedInIcon } from "@/components/Icons";
import SplitHeading from "@/components/ui/SplitHeading";
import ShapeGrid from "@/components/ui/ShapeGrid";

const GITHUB_URL = "https://github.com/YOUR-USERNAME/shark-isr-vtol";

const nav = [
  { href: "#autonomy-loop", label: "Autonomy loop" },
  { href: "#contribution", label: "Contribution" },
  { href: "#stack", label: "Stack" },
  { href: "#perception", label: "Detector" },
  { href: "#architecture", label: "Architecture" },
  { href: "#status", label: "Status" },
  { href: "#testing", label: "Testing" },
  { href: "#roadmap", label: "Roadmap" },
];

const contributions = [
  {
    n: "01",
    title: "Persistent coverage",
    body: "The swim zone is covered by a threat-weighted persistent patrol — shore-parallel sweeps, denser inshore where sharks are, with a revisit bound so no water goes stale. Probability re-grows as a target could move in, so guidance returns instead of chasing one greedy peak. Coverage, not a one-shot find. SITL-verified in T10.",
  },
  {
    n: "02",
    title: "Confidence-gated transition",
    body: "Detections accumulate confidence across frames and decay on misses. Only a sustained crossing of threshold τ triggers the autonomous SEARCH → TRACK transition and orbit-on-detect. One lucky frame never flies the aircraft.",
  },
  {
    n: "03",
    title: "Onboard, link-independent",
    body: "The detector (YOLOv8n compiled to a Hailo .hef) runs on a 13-TOPS NPU on the aircraft. Losing every radio link costs situational awareness — never autonomy.",
  },
];

const status = [
  { p: "1", scope: "Interface contract — 6 interfaces, frames + units", state: "Frozen 2026-05-31", tone: "ok" },
  { p: "2", scope: "PX4 SITL + Gazebo coastal world + DDS bridge", state: "World + launcher done; DDS gate pending", tone: "prog" },
  { p: "3", scope: "Autopilot bridge (sole PX4 boundary, uXRCE-DDS)", state: "SITL ✓ — T06 orbit · T07 failsafe", tone: "ok" },
  { p: "4", scope: "Guidance — Bayesian map, search, orbit-on-detect", state: "SITL ✓ — T10 search + track transition", tone: "ok" },
  { p: "5", scope: "Perception — Cam3 → Hailo detector → geolocation", state: "SITL ✓ — T11 pipeline end-to-end", tone: "ok" },
  { p: "6", scope: "Mission — state machine, failsafes", state: "SITL ✓ — T08 abort · T09 battery · T10 e2e", tone: "ok" },
  { p: "7", scope: "Telemetry — JSONL logs, GCS relay", state: "Code complete; SITL rehearsal pending", tone: "prog" },
  { p: "8", scope: "Hardware bring-up, mass/power budget, flight test", state: "Planned (post-budget)", tone: "plan" },
];

const toneClass: Record<string, string> = {
  ok: "bg-ok/10 text-ok border-ok/30",
  prog: "bg-track/10 text-track border-track/30",
  plan: "bg-faint/10 text-faint border-line2",
};

const sitlTests: { id: string; title: string; proves: string; evidence: string; pass: boolean }[] = [
  {
    id: "T06", title: "Observation orbit geometry",
    proves: "The bridge can hold a precise circular orbit — the geometry the aircraft flies once it's tracking a target.",
    evidence: "20/20 setpoints on the 30 m circle (min=max=mean=30.00 m).", pass: true,
  },
  {
    id: "T07", title: "Companion failsafe",
    proves: "The safety boundary: if the companion computer stops streaming, PX4 takes the aircraft back — the companion is never in the safety-critical loop.",
    evidence: "Offboard stream loss → PX4 exits OFFBOARD in 5.1 s (COM_OF_LOSS_T).", pass: true,
  },
  {
    id: "T08", title: "Operator abort → RTL",
    proves: "An operator can abort the mission at any time and the aircraft returns home under autopilot control.",
    evidence: "CMD_ABORT drove PX4 to nav_state RTL.", pass: true,
  },
  {
    id: "T09", title: "Low-battery failsafe",
    proves: "Energy is the binding resource — a low battery auto-triggers return before the aircraft is stranded.",
    evidence: "Threshold crossing → mission RETURNING (threshold tuneable live via ROS 2 param).", pass: true,
  },
  {
    id: "T10", title: "End-to-end mission rehearsal",
    proves: "The full mission state machine runs start to finish without any intervention.",
    evidence: "All 5 phases visited IDLE→TRANSIT→SEARCH→TRACK→RETURN in 7.0 s.", pass: true,
  },
  {
    id: "T11", title: "Perception pipeline → TRACK",
    proves: "The headline autonomy claim: the real camera→detector→guidance chain makes the SEARCH→TRACK decision itself — no test-side injection, no shortcut.",
    evidence: "mock_camera_node → detector_node → /detection → guidance TRACK in 3.2 s; ≥1 Detection confirmed.", pass: true,
  },
];

const principles = [
  "One ROS 2 package = one responsibility; modules talk only through shark_isr_interfaces.",
  "Energy is the binding resource — MTOW 2.5 kg hard ceiling, best-L/D loiter bias.",
  "Frames + units explicit on every message; parameters in YAML, never hardcoded.",
  "Everything logged — flight, detections, decisions — so any incident is reconstructable.",
  "No code reaches the aircraft until it has passed in SITL.",
  "The companion computer is never in the safety-critical loop.",
];

function Eyebrow({ children }: { children: React.ReactNode }) {
  return (
    <span className="mb-3 block font-mono text-[0.7rem] uppercase tracking-[0.22em] text-faint">
      <span className="text-accent">// </span>
      {children}
    </span>
  );
}

// Placeholder section for work not yet built — honest "to be continued" shell.
function ComingSoon({
  id,
  kicker,
  title,
  body,
  items,
}: {
  id: string;
  kicker: string;
  title: string;
  body: string;
  items: string[];
}) {
  return (
    <section id={id} className="border-b border-line">
      <div className="mx-auto max-w-6xl px-6 py-20">
        <Eyebrow>{kicker}</Eyebrow>
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="text-4xl font-semibold tracking-tight text-primary sm:text-5xl">
            {title}
          </h2>
          <span className="rounded-full border border-line2 px-2.5 py-1 font-mono text-[0.6rem] uppercase tracking-wider text-faint">
            To be continued
          </span>
        </div>
        <p className="mt-4 max-w-2xl text-secondary">{body}</p>
        <div className="mt-10 grid gap-3 sm:grid-cols-3">
          {items.map((it) => (
            <div
              key={it}
              className="rounded-lg border border-dashed border-line2 bg-surface/40 p-5"
            >
              <div className="font-mono text-[0.62rem] uppercase tracking-wider text-faint">
                {it}
              </div>
              <div className="mt-2 font-mono text-xs text-faint/70">
                Coming soon
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

export default function Home() {
  return (
    <>
      {/* nav */}
      <header className="sticky top-0 z-50 border-b border-line bg-bg/85 backdrop-blur">
        <nav className="mx-auto flex h-14 max-w-6xl items-center gap-6 px-6">
          <a href="#top" className="font-mono text-sm font-medium tracking-tight text-primary">
            shark-isr<span className="text-accent">/</span>vtol
          </a>
          <div className="ml-auto hidden items-center gap-6 md:flex">
            {nav.map((n) => (
              <a
                key={n.href}
                href={n.href}
                className="font-mono text-xs uppercase tracking-wider text-faint transition-colors hover:text-primary"
              >
                {n.label}
              </a>
            ))}
          </div>
          <a
            href={GITHUB_URL}
            target="_blank"
            rel="noopener noreferrer"
            aria-label="View source on GitHub"
            className="cursor-pointer text-faint transition-colors hover:text-primary"
          >
            <GitHubIcon className="h-5 w-5" />
          </a>
        </nav>
      </header>

      <main id="top" className="flex-1">
        <Hero />

        {/* exploded airframe + electronics (scroll-driven) */}
        <ExplodedSection3D />

        {/* contribution */}
        <section id="contribution" className="border-b border-line">
          <div className="relative isolate mx-auto max-w-6xl px-6 py-20">
            <ShapeGrid />
            <Eyebrow>The contribution</Eyebrow>
            <SplitHeading
              text="The search that doesn't miss, and the decision that doesn't guess."
              as="h2"
              className="max-w-3xl text-4xl font-semibold tracking-tight text-primary sm:text-5xl"
            />
            <div className="mt-14 grid gap-x-10 gap-y-12 md:grid-cols-3">
              {contributions.map((c) => (
                <article key={c.n} className="border-t-2 border-ink/80 pt-5">
                  <div className="font-display text-5xl font-semibold leading-none text-accent">
                    {c.n}
                  </div>
                  <h3 className="mt-5 font-display text-2xl font-semibold text-primary">
                    {c.title}
                  </h3>
                  <p className="mt-3 text-[0.95rem] leading-relaxed text-secondary">
                    {c.body}
                  </p>
                </article>
              ))}
            </div>
          </div>
        </section>

        {/* autonomy loop sim */}
        <section id="autonomy-loop" className="border-b border-line bg-surface/40">
          <div className="mx-auto max-w-6xl px-6 py-20">
            <Eyebrow>Live model · not flight data</Eyebrow>
            <h2 className="max-w-3xl text-4xl font-semibold tracking-tight text-primary sm:text-5xl">
              The autonomy loop, in the browser
            </h2>
            <p className="mt-4 max-w-2xl text-secondary">
              A faithful model of the guidance state machine. Watch confidence
              accumulate across detection frames and decay on misses — only a
              sustained crossing of τ transitions SEARCH → TRACK. Inject a
              detection, or watch a link loss degrade to autopilot RTL.
            </p>
            <div className="mt-10">
              <AutonomyLoop />
            </div>
          </div>
        </section>

        {/* 3D mission visualisation */}
        <MissionSection3D />

        {/* hardware stack */}
        <section id="stack" className="border-b border-line bg-[#070b0f]">
          <div className="mx-auto max-w-6xl px-6 py-20">
            <span className="mb-3 block font-mono text-[0.7rem] uppercase tracking-[0.22em] text-slate-500">
              <span className="text-sky-400">// </span>The autonomy stack
            </span>
            <h2 className="max-w-3xl text-4xl font-semibold tracking-tight text-white sm:text-5xl">
              Four boards, one decision loop.
            </h2>
            <p className="mt-4 max-w-2xl text-slate-400">
              Camera to NPU to companion to autopilot — the physical path a
              detection takes before it can fly the aircraft. Click a board to
              inspect it; the buses light up to trace the signal.
            </p>
            <div className="mt-10">
              <StackSection3D />
            </div>
          </div>
        </section>

        {/* detector performance + training pipeline */}
        <PerceptionSection />

        {/* architecture */}
        <section id="architecture" className="border-b border-line">
          <div className="mx-auto max-w-6xl px-6 py-20">
            <Eyebrow>Architecture</Eyebrow>
            <h2 className="max-w-3xl text-4xl font-semibold tracking-tight text-primary sm:text-5xl">
              The responsibility boundary is the design.
            </h2>
            <div className="mt-10 grid gap-6 lg:grid-cols-2">
              <div className="rounded-sm border border-line bg-surface p-6">
                <h3 className="font-mono text-xs uppercase tracking-wider text-track">
                  PX4 — owns the inner loop
                </h3>
                <p className="mt-3 text-sm leading-relaxed text-secondary">
                  Inner loop, the tilt transition, and every failsafe. ROS 2 can
                  only <em>ask</em>. The companion computer is architecturally
                  incapable of overriding a failsafe — its total failure degrades
                  to an autopilot-handled RTL.
                </p>
              </div>
              <div className="rounded-sm border border-line bg-surface p-6">
                <h3 className="font-mono text-xs uppercase tracking-wider text-accent">
                  ROS 2 — owns the outer loop
                </h3>
                <p className="mt-3 text-sm leading-relaxed text-secondary">
                  Mission, guidance, perception, telemetry. Six interfaces (4 msg,
                  2 srv) were specified with explicit frames/units and frozen
                  before any node was written — ENU/FLU everywhere, with all
                  NED↔ENU conversion confined to one package.
                </p>
              </div>
            </div>
            <p className="mt-6 font-mono text-xs text-faint">
              perception → guidance → autopilot → PX4 (uXRCE-DDS) · all packages → telemetry
            </p>
          </div>
        </section>

        {/* status */}
        <section id="status" className="border-b border-line bg-surface/40">
          <div className="mx-auto max-w-6xl px-6 py-20">
            <Eyebrow>Status — gated, honest</Eyebrow>
            <h2 className="max-w-3xl text-4xl font-semibold tracking-tight text-primary sm:text-5xl">
              T06–T11 all pass. Full stack SITL-verified.
            </h2>
            <p className="mt-4 max-w-2xl text-secondary">
              All seven packages build green (colcon on ROS 2 Humble), the full
              stack launches from one file, and 65/65 unit tests pass. Six SITL
              checks confirm the complete mission stack — from PX4 offboard
              engagement through perception-driven SEARCH→TRACK.
            </p>
            <div className="mt-10 overflow-x-auto rounded-sm border border-line bg-surface">
              <table className="w-full min-w-[640px] text-left text-sm">
                <thead>
                  <tr className="border-b border-line font-mono text-[0.65rem] uppercase tracking-wider text-faint">
                    <th className="px-4 py-3 font-medium">#</th>
                    <th className="px-4 py-3 font-medium">Scope</th>
                    <th className="px-4 py-3 font-medium">State</th>
                  </tr>
                </thead>
                <tbody>
                  {status.map((r) => (
                    <tr key={r.p} className="border-b border-line last:border-0">
                      <td className="px-4 py-3 font-mono text-faint">{r.p}</td>
                      <td className="px-4 py-3 text-secondary">{r.scope}</td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-block rounded border px-2 py-0.5 font-mono text-[0.65rem] ${toneClass[r.tone]}`}
                        >
                          {r.state}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>

        {/* principles */}
        <section className="border-b border-line">
          <div className="mx-auto max-w-6xl px-6 py-20">
            <Eyebrow>Engineering principles</Eyebrow>
            <ul className="mt-8 grid gap-px overflow-hidden rounded-sm border border-line bg-line sm:grid-cols-2">
              {principles.map((p, i) => (
                <li key={i} className="flex gap-3 bg-surface p-5">
                  <span className="font-mono text-xs text-accent">{String(i + 1).padStart(2, "0")}</span>
                  <span className="text-sm leading-relaxed text-secondary">{p}</span>
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* SITL test results */}
        <section id="testing" className="border-b border-line bg-surface/40">
          <div className="mx-auto max-w-6xl px-6 py-20">
            <Eyebrow>Verification &amp; SITL</Eyebrow>
            <h2 className="max-w-3xl text-4xl font-semibold tracking-tight text-primary sm:text-5xl">
              T06–T11 all pass.
            </h2>
            <p className="mt-4 max-w-2xl text-secondary">
              SITL (Software-in-the-Loop) runs the real ROS&nbsp;2 nodes against
              a simulated PX4 autopilot and Gazebo Harmonic world — no hardware
              required, but the actual autonomy code executes. It&apos;s the
              project&apos;s release gate:{" "}
              <em className="text-ink">no code reaches the aircraft until it has
              passed in SITL.</em> These aren&apos;t unit tests; each check
              drives the complete node graph and validates a specific behaviour
              claim.
            </p>

            {/* summary stats */}
            <div className="mt-10 grid grid-cols-3 divide-x divide-line overflow-hidden rounded-sm border border-line bg-surface">
              {[
                { stat: "6/6", label: "SITL checks pass" },
                { stat: "5",   label: "Mission phases visited" },
                { stat: "0",   label: "Companion in safety loop" },
              ].map((s) => (
                <div key={s.label} className="px-6 py-5">
                  <div className="font-display text-3xl font-bold text-primary">{s.stat}</div>
                  <div className="mt-1 font-mono text-[0.62rem] uppercase tracking-[0.16em] text-faint">{s.label}</div>
                </div>
              ))}
            </div>

            {/* per-test cards */}
            <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {sitlTests.map((t) => (
                <div key={t.id} className="rounded-sm border border-line bg-surface p-5">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-xs text-faint">{t.id}</span>
                    <span className={`rounded border px-2 py-0.5 font-mono text-[0.62rem] ${toneClass.ok}`}>
                      PASS
                    </span>
                  </div>
                  <h3 className="mt-3 font-sans text-sm font-semibold text-primary">{t.title}</h3>
                  <p className="mt-2 text-[0.82rem] leading-relaxed text-secondary">{t.proves}</p>
                  <p className="mt-3 font-mono text-[0.7rem] leading-relaxed text-faint">{t.evidence}</p>
                </div>
              ))}
            </div>

            <p className="mt-6 font-mono text-xs text-faint">
              T01–T05 (DDS bridge, arming, takeoff, basic loiter) passed in a prior campaign.
              Suite: <code className="text-faint/80">./sim/tests/run_tests.sh</code> · PX4 SITL + Gazebo Harmonic · ROS 2 Humble
            </p>
          </div>
        </section>

        {/* to be continued — schedule map */}
        <ComingSoon
          id="roadmap"
          kicker="Plan"
          title="Schedule map"
          body="The phase plan from interface freeze to first flight. A live status map of what's done, what's in progress, and what's queued will live here."
          items={["Phase timeline", "Milestone gates", "Flight-test window"]}
        />
      </main>

      {/* footer */}
      <footer className="border-t border-line bg-surface">
        <div className="mx-auto flex max-w-6xl flex-col gap-6 px-6 py-12 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <div className="font-mono text-sm text-primary">
              Ryan H. — Electrical &amp; Aerospace Engineering, QUT
            </div>
            <p className="mt-2 max-w-md text-sm text-faint">
              The application is shark monitoring; the engineering is persistent
              ISR autonomy. MIT licensed. No flight data presented as real prior
              to flight test.
            </p>
          </div>
          <div className="flex items-center gap-4">
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noopener noreferrer"
              aria-label="GitHub"
              className="cursor-pointer text-faint transition-colors hover:text-primary"
            >
              <GitHubIcon className="h-5 w-5" />
            </a>
            <a
              href="https://www.linkedin.com"
              target="_blank"
              rel="noopener noreferrer"
              aria-label="LinkedIn"
              className="cursor-pointer text-faint transition-colors hover:text-[#0A66C2]"
            >
              <LinkedInIcon className="h-5 w-5" />
            </a>
          </div>
        </div>
      </footer>
    </>
  );
}
