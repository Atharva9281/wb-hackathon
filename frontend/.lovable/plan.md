## Goal

Rebuild the visual layer of QueryMind across all three routes (`/`, `/dashboard`, `/economics`) and the shared Navbar to match the new editorial-minimal spec (Instrument Serif hero + DM Sans UI + IBM Plex Mono data, white surfaces, 1px borders, no gradients/shadows, electric-blue accent only). Keep routing, store, and runQuery logic intact. Also extend the store so the agent *chooses* the mode (user only picks an optimization goal) and surfaces a decision rationale.

## Scope

Visual + small state shape additions only. No backend/SSE changes, no new routes, no removal of existing data flow.

## Files to change

### 1. `src/styles.css` — design tokens
- Import Instrument Serif, DM Sans, IBM Plex Mono via `<link>` in `__root.tsx` (Google Fonts).
- Add `--font-display: "Instrument Serif", serif`.
- Strip all gradient-based `card-soft*` rules. Replace with a single flat `.card` = `bg-white border border-border rounded-lg` and `.card-elevated` = same + `border-primary`.
- Tighten shadows to only `0 1px 2px rgba(0,0,0,0.06)` available as `.shadow-hairline`.
- Add `.label-eyebrow` (11px uppercase, tracking 0.08em, `#9ca3af`).
- Add `.mode-dot-{a|b|c}` and `.agent-dot-{planner|optimizer|executor|reducer}` swatches.

### 2. `src/routes/__root.tsx` — inject Google Fonts links in `head()`.

### 3. `src/components/Navbar.tsx`
- White, sticky, 1px bottom border.
- Left: "QueryMind" in DM Sans 600.
- Right: `Dashboard`, `Economics` gray links; `Try it →` blue filled pill.

### 4. `src/routes/index.tsx` — Landing
- Full-viewport hero (`min-h-[calc(100vh-56px)]`), centered, max-w-[900px].
- Eyebrow pill: blue border, blue text, white bg, "Multi-Agent Orchestration".
- Hero `<h1>` in Instrument Serif, `clamp(56px, 8vw, 120px)`, line-height 1.05, tracking -0.03em. Text: `Stop Overpaying` / `for AI Queries.` (second line italic).
- Subtext (560px, #6b7280, 18px/1.6), CTA row (blue primary + outline secondary).
- Scroll indicator pinned bottom: animated chevron + "scroll to explore".
- Cost comparison section: 3 cards (Brute / Smart Filter elevated / Parallel) with badges, huge IBM Plex Mono cost numbers in red/green/blue, description, footer stats. "92% cost reduction" line on Smart card. Closing sentence centered below.
- Example questions section: `bg:#f8f9fa`, 3×2 grid of 6 CFPB questions; each card has → arrow top-right, question text, "CFPB Data · 2018-2019" footer. Hover: 3px blue left border + subtle blue tint. Clicking sets question in store and navigates to `/dashboard`.
- Footer: white, top border, centered gray "QueryMind · Built at AGI House Hackathon · May 2026".

### 5. `src/routes/dashboard.tsx` — 3-column layout
- LEFT (280px, `#f8f9fa`, scrollable):
  - QUERY label + textarea (white, focus border blue).
  - OPTIMIZATION GOAL label + 3 pills `⚡ Fastest`, `⚖️ Balanced`, `💰 Cheapest` (default Balanced).
  - Run Query button (blue filled). Loading: spinner + "Agents working…".
  - Divider.
  - RECENT QUERIES list: 64px rows = colored mode dot + 2-line text block (question + mono meta `$cost · latency · mode · relative time`) + chevron. Hover/active states per spec.
- MIDDLE (flex-1, white): EXECUTION GRAPH label, vertical DAG (Planner → Optimizer → Executor → Reducer) with 1px gray connectors that turn blue when upstream done. Executor node shows 3 tool pills (Filter / Aggregator / Joiner) that light blue when called. Each node card: white, 1px border, name, status dot (gray/blue-pulse/green/red), running state = blue border + `#eff6ff` bg, done state shows mono meta line.
  - After completion: Agent Decision card (3px blue left border) — "Agent selected: {mode}" + rationale.
  - Execution Timeline below: Gantt rows per agent, bars colored by agent, width ∝ latency, mono labels.
- RIGHT (280px, `#f8f9fa`, scrollable): ANSWER label, empty state, streaming text, then Cost Summary card with mono rows (Agent chose / Model / Tokens / Cost / Latency / Rows filtered), then blue "View full breakdown →" link to `/economics`.

### 6. `src/routes/economics.tsx` — 2-column layout
- Replace existing card grid + current detail panel with the spec layout. Keep `selectedId` selection logic from prior turn.
- LEFT (300px, `#f8f9fa`): Page title "Economics" + subtitle, 4 stacked stat cards (Total Queries / Total Tokens / Total Cost / Avg Cost) with mono values, filter pills `All / Brute / Smart / Parallel`, then the same 64px row list as dashboard. Selected row gets blue left border.
- RIGHT (flex-1, white): Header with question + green mode badge + timestamp + mono `COST · TOKENS · LATENCY`. Green savings banner when chosen mode beats Brute Force baseline. Tabs `Cost Breakdown` / `Raw Logs` with thin border + 2px blue underline on active.
  - Breakdown: mode comparison table (winning column highlighted blue), Recharts BarChart "Cost per Agent" (agent-colored bars, horizontal grid only), agent breakdown table.
  - Raw Logs: per-agent expandable rows (collapsed 48px, expanded shows PROMPT/RESPONSE boxes in IBM Plex Mono, footer with mono stats).

### 7. `src/store/useQueryStore.ts` — small extensions
- Add `goal: "fastest" | "balanced" | "cheapest"` and `setGoal`.
- Add `modeChosen?: Mode` and `modeReason?: string` to current run + each `HistoryItem`.
- Rename agent set to `{ planner, optimizer, executor, reducer }` IF current store uses different keys; keep backward-compatible alias if needed (verify on read).
- No persistence changes beyond adding the new fields to the existing localStorage shape.

### 8. `src/lib/runQuery.ts` — mock the chosen mode
- After run completes, derive `modeChosen` from `goal` (cheapest→Smart, fastest→Parallel, balanced→Smart by default) and write a one-line `modeReason` (e.g. "Large dataset detected (20,000 rows). Filtering reduces token cost by 92%."). No SSE wiring changes.

### 9. Small reusable bits (kept inline to avoid new files unless reused 3+ times)
- `relativeTime(ts)` helper already added previously — reuse.
- `Pill`, `StatCard`, `QueryRow`, `AgentNode`, `LogRow` defined inline in their route files; promote to `src/components/` only if shared across routes.

## Out of scope

- Real SSE/backend integration changes.
- Auth, persistence migrations, or new routes.
- Animations beyond the spec'd pulse dot, flow line, and bar fill.
- Dark mode.
- Replacing Recharts.

## Acceptance

- Landing hero fills viewport, headline rendered in Instrument Serif at clamp size, second line italic.
- All numbers app-wide are IBM Plex Mono; all UI text DM Sans.
- No gradients, no colored section backgrounds beyond `#f8f9fa` panel gray, no shadow heavier than 0 1px 2px.
- Dashboard mode is chosen by the agent post-run; user only picks goal.
- Economics list selection drives the right panel and both tabs.

Approve and I'll implement.
