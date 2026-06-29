import SplitHeading from "@/components/ui/SplitHeading";
import ShapeGrid from "@/components/ui/ShapeGrid";

// All numbers verified against actual training artifacts 2026-06-22.
// Do NOT add a FPS/latency figure — on-device throughput is unmeasured.
// Do NOT reference the old 0.987 mAP50 — it was a train/val leakage artifact.

const metrics = [
  { stat: "0.945", unit: "mAP50",   label: "Held-out test" },
  { stat: "0.742", unit: "mAP50‑95", label: "Held-out test" },
  { stat: "95%",   unit: "recall",   label: "Mission metric" },
  { stat: "89%",   unit: "precision",label: "Hard-negative set" },
  { stat: "223",   unit: "imgs",     label: "Held-out test set" },
];

// 80/10/10 group-disjoint split — actual counted image files
const splits = [
  { label: "Train", count: 2847, bg: 657,  pct: 87.3, color: "bg-accent"   },
  { label: "Val",   count: 191,  bg: 44,   pct: 5.9,  color: "bg-ok"       },
  { label: "Test",  count: 223,  bg: 51,   pct: 6.8,  color: "bg-track"    },
];

const datasets = [
  { name: "uav_shark",      license: "MIT" },
  { name: "shark_ml",       license: "CC BY 4.0" },
  { name: "shark_tracking", license: "CC BY 4.0" },
  { name: "salo_levy",      license: "CC BY 4.0" },
];

const pipeline = [
  { label: ".pt",   note: "PyTorch weights" },
  { label: ".onnx", note: "opset 11, fixed batch" },
  { label: ".har",  note: "Hailo parse" },
  { label: "INT8",  note: "64-img calibration" },
  { label: ".hef",  note: "9 MB · hailo8l · 3-ctx" },
];

export default function PerceptionSection() {
  return (
    <section id="perception" className="border-b border-line">
      <div className="relative isolate mx-auto max-w-6xl px-6 py-20">
        <ShapeGrid />

        {/* kicker + heading */}
        <span className="mb-3 block font-mono text-[0.7rem] uppercase tracking-[0.22em] text-faint">
          <span className="text-accent">// </span>Perception — the detector
        </span>
        <SplitHeading
          text="The number that survives a held-out test."
          as="h2"
          className="max-w-3xl text-4xl font-semibold tracking-tight text-primary sm:text-5xl"
        />
        <p className="mt-4 max-w-2xl text-secondary">
          YOLOv8n fine-tuned on 3,261 aerial images from four datasets and compiled to
          a Hailo <code className="font-mono text-xs text-faint">.hef</code> that runs
          on the onboard 13-TOPS NPU. Performance scored on 223 images the model
          never saw — including 51 open-water hard negatives.
        </p>

        {/* stat rail — same markup as Hero spec rail */}
        <div className="mt-10 grid grid-cols-2 overflow-hidden rounded-xl border border-line bg-surface sm:grid-cols-3 lg:grid-cols-5">
          {metrics.map((m, i) => (
            <div
              key={m.label + i}
              className="border-b border-line px-5 py-5 last:border-b-0 sm:[&:nth-last-child(-n+2)]:border-b-0 lg:[&:nth-child(n)]:border-b-0 [&:not(:last-child)]:border-r"
            >
              <div className="flex items-baseline gap-1">
                <span className="font-display text-2xl font-bold text-primary">
                  {m.stat}
                </span>
                <span className="font-mono text-xs text-faint">{m.unit}</span>
              </div>
              <div className="mt-1 font-mono text-[0.62rem] uppercase tracking-[0.16em] text-faint">
                {m.label}
              </div>
            </div>
          ))}
        </div>

        {/* ISR framing — 2 cards */}
        <div className="mt-12 grid gap-6 lg:grid-cols-2">
          <div className="rounded-sm border border-line bg-surface p-6">
            <h3 className="font-mono text-xs uppercase tracking-wider text-ok">
              Recall is the mission metric
            </h3>
            <p className="mt-3 text-sm leading-relaxed text-secondary">
              For persistent aerial ISR, missing a detection is the operational
              failure — the shark goes unlogged, the patrol wasted. A 95% recall
              rate means the system finds 19 of every 20 real targets.
            </p>
          </div>
          <div className="rounded-sm border border-line bg-surface p-6">
            <h3 className="font-mono text-xs uppercase tracking-wider text-track">
              A false alarm is cheap
            </h3>
            <p className="mt-3 text-sm leading-relaxed text-secondary">
              An 89% precision rate means ~1-in-9 detections is a false positive.
              In ISR the cost is a second orbit over that patch of water — minor,
              recoverable. The 0.95/0.89 split is the <em>correct</em> operating
              point for the application, not a trade-off accepted.
            </p>
          </div>
        </div>

        {/* VIZ 1 — recall | precision bars */}
        <div
          role="img"
          aria-label="Recall 95% and Precision 89% performance comparison"
          className="mt-6 space-y-2.5 rounded-sm border border-line bg-surface p-5"
        >
          {[
            { metric: "Recall",    pct: 95, colorBar: "bg-ok",     colorText: "text-ok" },
            { metric: "Precision", pct: 89, colorBar: "bg-accent",  colorText: "text-accent" },
          ].map((r) => (
            <div key={r.metric} className="flex items-center gap-3">
              <div className="w-20 shrink-0 font-mono text-xs text-faint">{r.metric}</div>
              <div className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-line">
                <div
                  className={`absolute inset-y-0 left-0 rounded-full ${r.colorBar}`}
                  style={{ width: `${r.pct}%` }}
                />
              </div>
              <div className={`w-10 shrink-0 text-right font-mono text-xs ${r.colorText}`}>
                {r.pct}%
              </div>
            </div>
          ))}
          <p className="pt-1 font-mono text-[0.6rem] uppercase tracking-wider text-faint">
            223 held-out images · 51 open-water negatives · recall leads by design
          </p>
        </div>

        {/* leakage story */}
        <div className="mt-12 border-t border-line pt-10">
          <h3 className="font-mono text-xs uppercase tracking-wider text-faint">
            Why this number is honest
          </h3>
          <p className="mt-3 max-w-2xl text-sm leading-relaxed text-secondary">
            The initial pipeline reported mAP50 0.987 — a number that failed a
            plausibility check. Investigation found the merge script had pooled
            source-level train and validation sets, shuffled, and re-split 90/10,
            scattering Roboflow augmentation siblings and consecutive video frames
            across both sides. Roughly 67% of the validation set shared a source
            image with train. The model was scoring near-copies of images it had
            already memorised.
          </p>
          <p className="mt-3 max-w-2xl text-sm leading-relaxed text-secondary">
            The merge pipeline was rewritten with a{" "}
            <strong className="font-medium text-ink">group-disjoint split</strong>:
            siblings and clips are grouped by source image, and entire groups land
            on one side only. A held-out test split (never touched during training
            or validation) was added, along with background negatives — open water,
            boats, non-shark — to make false-positive rate measurable. The model
            was retrained from scratch. Val ≈ Test (0.949 vs 0.945) confirms it
            generalises.
          </p>

          {/* VIZ 2 — dataset split bar */}
          <div className="mt-8">
            <div className="mb-2 font-mono text-[0.6rem] uppercase tracking-wider text-faint">
              3,261 images · group-disjoint 80 / 10 / 10 split
            </div>
            <div
              role="img"
              aria-label="Dataset split: 2847 train, 191 val, 223 test"
              className="flex h-5 w-full overflow-hidden rounded-sm"
            >
              {splits.map((s) => (
                <div
                  key={s.label}
                  className={`${s.color} flex items-center justify-center`}
                  style={{ width: `${s.pct}%` }}
                  title={`${s.label}: ${s.count} images (${s.bg} backgrounds)`}
                />
              ))}
            </div>
            <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1">
              {splits.map((s) => (
                <div key={s.label} className="flex items-center gap-1.5">
                  <div className={`h-2 w-2 rounded-sm ${s.color}`} />
                  <span className="font-mono text-[0.62rem] text-faint">
                    {s.label} {s.count.toLocaleString()}
                    <span className="text-faint/60"> ({s.bg} bg)</span>
                  </span>
                </div>
              ))}
            </div>
            <div className="mt-4 flex flex-wrap gap-x-4 gap-y-0.5">
              {datasets.map((d) => (
                <span key={d.name} className="font-mono text-[0.6rem] text-faint/70">
                  {d.name} · {d.license}
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* VIZ 3 — compile pipeline strip */}
        <div className="mt-12 border-t border-line pt-10">
          <div className="flex items-center justify-between gap-3">
            <h3 className="font-mono text-xs uppercase tracking-wider text-faint">
              Compile pipeline
            </h3>
            <span className="inline-block rounded border border-track/30 bg-track/10 px-2 py-0.5 font-mono text-[0.65rem] text-track">
              On-device SITL pending
            </span>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-1">
            {pipeline.map((step, i) => (
              <span key={step.label} className="flex items-center gap-1">
                <span
                  className="rounded-sm border border-line bg-surface px-2.5 py-1 font-mono text-xs text-primary"
                  title={step.note}
                >
                  {step.label}
                </span>
                {i < pipeline.length - 1 && (
                  <span className="font-mono text-[0.7rem] text-faint" aria-hidden>
                    →
                  </span>
                )}
              </span>
            ))}
          </div>
          <p className="mt-3 font-mono text-[0.6rem] uppercase tracking-wider text-faint">
            Hailo-8L · hailo8l arch · 3-context · DFL decode + NMS on Pi 5 CPU ·
            confidence threshold 0.45 · 640 px input · 10 Hz target
          </p>
        </div>
      </div>
    </section>
  );
}
