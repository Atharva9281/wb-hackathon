import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { ArrowRight } from "lucide-react";
import { Navbar } from "@/components/Navbar";
import { useQueryStore } from "@/store/useQueryStore";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "QueryMind — Stop overpaying for AI queries" },
      { name: "description", content: "Multi-agent orchestration that picks the cheapest execution plan automatically." },
      { property: "og:title", content: "QueryMind — Stop overpaying for AI queries" },
      { property: "og:description", content: "Multi-agent orchestration that picks the cheapest execution plan automatically." },
    ],
  }),
  component: Landing,
});

const EXAMPLES = [
  "Which bank has the most unresolved complaints?",
  "Find complaints threatening legal action",
  "Which state has the most mortgage complaints?",
  "What are the top issues with credit cards in 2019?",
  "Which companies take longest to respond to consumers?",
  "Find all fraud complaints filed in 2018",
];

function Landing() {
  const navigate = useNavigate();
  const setQuestion = useQueryStore((s) => s.setQuestion);

  const pickExample = (q: string) => {
    setQuestion(q);
    navigate({ to: "/dashboard" });
  };

  return (
    <div className="min-h-screen bg-white">
      <Navbar />

      {/* HERO — full viewport */}
      <section className="relative flex min-h-[calc(100vh-56px)] flex-col items-center justify-center px-6">
        <div className="mx-auto max-w-[900px] text-center">
          <span className="inline-block rounded-full border border-primary bg-white px-3 py-1 text-[11px] font-medium uppercase tracking-[0.12em] text-primary">
            Multi-Agent Orchestration
          </span>

          <h1
            className="font-display mt-8 text-charcoal"
            style={{
              fontSize: "clamp(56px, 8vw, 120px)",
              lineHeight: 1.05,
              letterSpacing: "-0.03em",
            }}
          >
            Stop Overpaying
            <br />
            <em className="italic">for AI Queries.</em>
          </h1>

          <p className="mx-auto mt-6 max-w-[560px] text-[18px] leading-[1.6] text-muted-foreground">
            QueryMind automatically routes your data questions through multiple
            specialized agents — picking the cheapest execution plan without
            sacrificing accuracy.
          </p>

          <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
            <Link
              to="/dashboard"
              className="rounded-lg bg-primary px-6 py-3 text-sm font-medium text-primary-foreground transition hover:bg-[#1d4ed8]"
            >
              Open Dashboard →
            </Link>
            <Link
              to="/economics"
              className="rounded-lg border border-border bg-white px-6 py-3 text-sm font-medium text-charcoal transition hover:bg-panel"
            >
              View Economics
            </Link>
          </div>
        </div>
      </section>

      {/* COST COMPARISON */}
      <section className="border-t border-border bg-white py-20">
        <div className="mx-auto max-w-[1100px] px-6">
          <div className="label-eyebrow text-center">Why it matters</div>
          <div className="mt-10 grid grid-cols-1 gap-5 md:grid-cols-3">
            <CostCard
              badge={{ label: "NAIVE", bg: "#fef2f2", fg: "#dc2626" }}
              cost="$14.20"
              costColor="#dc2626"
              title="Brute Force"
              description="Send everything to the most expensive model. No filtering."
              footer="45s latency · 80,000 tokens"
            />
            <CostCard
              badge={{ label: "AGENT PICKS THIS", bg: "#f0fdf4", fg: "#16a34a" }}
              cost="$1.15"
              costColor="#16a34a"
              title="Smart Filter"
              description="Filter with cheap model first. Only relevant data reaches the expensive model."
              footer="12s latency · 18,432 tokens"
              elevated
              extra="92% cost reduction"
            />
            <CostCard
              badge={{ label: "FASTEST", bg: "#eff6ff", fg: "#2563eb" }}
              cost="$2.30"
              costColor="#2563eb"
              title="Parallel"
              description="Multiple agents work simultaneously. Optimized for speed."
              footer="8s latency · 22,000 tokens"
            />
          </div>
          <p className="mx-auto mt-12 max-w-[640px] text-center text-[16px] text-muted-foreground">
            QueryMind's optimizer agent automatically picks the right strategy.
            You just ask the question.
          </p>
        </div>
      </section>

      {/* EXAMPLES */}
      <section className="border-t border-border bg-panel py-20">
        <div className="mx-auto max-w-[900px] px-6">
          <div className="label-eyebrow text-center">Try these questions</div>
          <div className="mt-10 grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {EXAMPLES.map((q) => (
              <button
                key={q}
                onClick={() => pickExample(q)}
                className="group relative border border-border bg-white px-6 py-5 text-left transition hover:border-l-[3px] hover:border-l-primary hover:bg-[#f5f8ff]"
                style={{ borderRadius: 10 }}
              >
                <ArrowRight className="absolute right-4 top-4 h-4 w-4 text-primary opacity-0 transition group-hover:opacity-100" />
                <div className="pr-6 text-[14px] font-medium leading-snug text-charcoal">
                  {q}
                </div>
                <div className="mt-3 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                  CFPB Data · 2018–2019
                </div>
              </button>
            ))}
          </div>
        </div>
      </section>

      <footer className="border-t border-border bg-white py-10 text-center text-xs text-muted-foreground">
        QueryMind · Built at AGI House Hackathon · May 2026
      </footer>
    </div>
  );
}

function CostCard({
  badge,
  cost,
  costColor,
  title,
  description,
  footer,
  elevated,
  extra,
}: {
  badge: { label: string; bg: string; fg: string };
  cost: string;
  costColor: string;
  title: string;
  description: string;
  footer: string;
  elevated?: boolean;
  extra?: string;
}) {
  return (
    <div
      className={`flex flex-col p-6 ${elevated ? "border-primary" : "border-border"} border bg-white`}
      style={{ borderRadius: 12, borderWidth: 1 }}
    >
      <span
        className="self-start rounded-sm px-2 py-0.5 text-[10px] font-semibold tracking-wider"
        style={{ backgroundColor: badge.bg, color: badge.fg }}
      >
        {badge.label}
      </span>
      <div
        className="mt-5 font-mono"
        style={{ fontSize: 48, lineHeight: 1, fontWeight: 500, color: costColor }}
      >
        {cost}
      </div>
      <div className="mt-4 text-[16px] font-bold text-charcoal">{title}</div>
      <div className="mt-1.5 text-[13.5px] leading-relaxed text-muted-foreground">
        {description}
      </div>
      <div className="mt-5 font-mono text-[11px] text-muted-foreground">{footer}</div>
      {extra && (
        <div className="mt-3 text-[12px] font-semibold text-success">{extra}</div>
      )}
    </div>
  );
}

