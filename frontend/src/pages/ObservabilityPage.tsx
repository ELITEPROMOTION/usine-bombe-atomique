import { useEffect, useMemo, useState } from "react";
import {
  Activity, AlertTriangle, BarChart3, Cloud, FileText,
  Filter, GitBranch, Search, Share2,
} from "lucide-react";
import {
  Badge, Card, CardHeader, HealthDot, KPIWidget,
} from "@/design-system";
import { apiClient } from "@/api/client";

// ===========================================================================
// Types
// ===========================================================================

interface AuditEvent {
  event_id: string;
  actor: string;
  action: string;
  created_at: string;
  payload?: unknown;
}

interface DatadogStatus {
  mode: string;
  site: string;
  default_tags: string[];
  log_file_path?: string;
}

interface SentryStatus {
  mode: string;
  environment: string;
  release: string;
  sample_rate: number;
  log_file_path?: string;
}

interface SentryError {
  fingerprint: string;
  count: number;
  last_seen?: string;
  message?: string;
  exc_type?: string;
}

interface OtelStatus {
  initialized: boolean;
  exporter: string;
  service_name: string;
  instrumentations: string[];
  sdk_available: boolean;
}

type TabId = "overview" | "traces" | "metrics" | "logs" | "errors" | "ci-cd";

const TABS: { id: TabId; label: string; icon: JSX.Element }[] = [
  { id: "overview", label: "Overview",  icon: <Activity size={12} /> },
  { id: "traces",   label: "Traces",    icon: <Share2 size={12} /> },
  { id: "metrics",  label: "Metrics",   icon: <BarChart3 size={12} /> },
  { id: "logs",     label: "Logs",      icon: <FileText size={12} /> },
  { id: "errors",   label: "Errors",    icon: <AlertTriangle size={12} /> },
  { id: "ci-cd",    label: "CI / CD",   icon: <GitBranch size={12} /> },
];

// ===========================================================================
// Page
// ===========================================================================

export function ObservabilityPage() {
  const [tab, setTab] = useState<TabId>("overview");

  return (
    <div className="px-4 lg:px-8 py-6 lg:py-10 max-w-7xl mx-auto">
      <header className="mb-6">
        <div className="text-[11px] uppercase tracking-[0.28em] text-gold-300 mb-1 flex items-center gap-1.5">
          <Cloud size={11} /> Observability V5.9
        </div>
        <h1 className="font-display text-2xl lg:text-3xl font-semibold">
          Datadog, Sentry, OpenTelemetry &amp; CI/CD
        </h1>
        <p className="text-ink-300 text-sm mt-1">
          Telemetrie, traces, errors, deployments — vue unifiee multi-fournisseurs.
        </p>
      </header>

      <div className="flex gap-1 mb-4 border-b border-ink-700 overflow-x-auto">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-3 py-2 text-xs font-medium flex items-center gap-1.5 border-b-2 transition-colors whitespace-nowrap ${
              tab === t.id
                ? "border-gold-400 text-gold-300"
                : "border-transparent text-ink-400 hover:text-ink-100"
            }`}
          >
            {t.icon}
            {t.label}
          </button>
        ))}
      </div>

      {tab === "overview" && <OverviewTab />}
      {tab === "traces"   && <TracesTab />}
      {tab === "metrics"  && <MetricsTab />}
      {tab === "logs"     && <LogsTab />}
      {tab === "errors"   && <ErrorsTab />}
      {tab === "ci-cd"    && <CiCdTab />}
    </div>
  );
}

// ===========================================================================
// Overview — at-a-glance health of all 3 backends + audit summary
// ===========================================================================

function OverviewTab() {
  const [dd, setDd] = useState<DatadogStatus | null>(null);
  const [sentry, setSentry] = useState<SentryStatus | null>(null);
  const [otel, setOtel] = useState<OtelStatus | null>(null);
  const [events, setEvents] = useState<AuditEvent[]>([]);

  async function refresh() {
    try {
      const [d, s, o, a] = await Promise.all([
        apiClient.get("/observability/datadog/status"),
        apiClient.get("/observability/sentry/status"),
        apiClient.get("/observability/otel/status"),
        apiClient.get("/analytics/audit/tail?limit=200"),
      ]);
      setDd(d.data);
      setSentry(s.data);
      setOtel(o.data);
      setEvents(a.data);
    } catch (e) {
      console.error(e);
    }
  }

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 15_000);
    return () => clearInterval(t);
  }, []);

  const failureRate = events.length
    ? events.filter((e) => e.action.includes("failed")).length / events.length
    : 0;
  const successRate = 1 - failureRate;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <BackendStatusCard
          title="Datadog"
          mode={dd?.mode}
          extra={dd?.site}
          ok={!!dd && dd.mode !== "error"}
        />
        <BackendStatusCard
          title="Sentry"
          mode={sentry?.mode}
          extra={sentry?.environment}
          ok={!!sentry && sentry.mode !== "error"}
        />
        <BackendStatusCard
          title="OpenTelemetry"
          mode={otel?.exporter}
          extra={otel ? `${otel.instrumentations.length} instrument(s)` : ""}
          ok={!!otel?.initialized}
        />
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KPIWidget
          icon={<Activity size={12} />}
          label="Audit events (200 last)"
          value={events.length}
        />
        <KPIWidget
          label="Success rate"
          value={`${(successRate * 100).toFixed(0)}%`}
          status={successRate >= 0.95 ? "success" : successRate >= 0.85 ? "warning" : "error"}
        />
        <KPIWidget
          label="Unique actions"
          value={new Set(events.map((e) => e.action)).size}
        />
        <KPIWidget
          label="Unique actors"
          value={new Set(events.map((e) => e.actor)).size}
        />
      </div>

      <Card>
        <CardHeader title="Audit activity (60s rolling buckets)" />
        <Sparkline events={events} />
      </Card>
    </div>
  );
}

function BackendStatusCard({
  title, mode, extra, ok,
}: { title: string; mode?: string; extra?: string; ok: boolean }) {
  return (
    <Card>
      <div className="flex items-center justify-between">
        <div>
          <div className="text-xs text-ink-400 uppercase tracking-wider">{title}</div>
          <div className="text-lg font-semibold text-ink-100 mt-1">
            {mode ?? "—"}
          </div>
          {extra && <div className="text-[11px] text-ink-500 mt-1">{extra}</div>}
        </div>
        <HealthDot status={ok ? "success" : "warning"} size="md" />
      </div>
    </Card>
  );
}

function Sparkline({ events }: { events: AuditEvent[] }) {
  const buckets = useMemo(() => {
    const now = Date.now();
    const bins = Array.from({ length: 30 }, () => 0);
    for (const e of events) {
      const t = new Date(e.created_at).getTime();
      const ageS = (now - t) / 1000;
      if (ageS < 0 || ageS > 30 * 60) continue;
      const idx = 29 - Math.floor(ageS / 60);
      if (idx >= 0 && idx < 30) bins[idx]++;
    }
    return bins;
  }, [events]);

  const max = Math.max(1, ...buckets);

  return (
    <div className="flex items-end gap-[2px] h-16 px-2">
      {buckets.map((c, i) => (
        <div
          key={i}
          className="flex-1 bg-gold-400/40 hover:bg-gold-300/70 transition-colors rounded-sm"
          style={{ height: `${(c / max) * 100}%`, minHeight: c > 0 ? "2px" : "1px" }}
          title={`t-${30 - i}min: ${c} events`}
        />
      ))}
    </div>
  );
}

// ===========================================================================
// Traces — OTel status + drill-down into instrumentations
// ===========================================================================

function TracesTab() {
  const [otel, setOtel] = useState<OtelStatus | null>(null);
  const [busy, setBusy] = useState(false);

  async function refresh() {
    const r = await apiClient.get("/observability/otel/status");
    setOtel(r.data);
  }

  async function init() {
    setBusy(true);
    try {
      await apiClient.post("/observability/otel/init");
      await refresh();
    } finally { setBusy(false); }
  }

  useEffect(() => { refresh(); }, []);

  if (!otel) return <Card><div className="p-4 text-ink-400">Loading…</div></Card>;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader
          icon={<Share2 size={14} />}
          title="OpenTelemetry status"
          action={
            <button
              onClick={init}
              disabled={busy}
              className="px-3 py-1 text-xs bg-gold-500/20 hover:bg-gold-500/30 disabled:opacity-40 text-gold-300 rounded-md border border-gold-500/30"
            >
              {busy ? "…" : "Initialize"}
            </button>
          }
        />
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <KPIWidget label="Initialized"
            value={otel.initialized ? "yes" : "no"}
            status={otel.initialized ? "success" : "warning"} />
          <KPIWidget label="Exporter" value={otel.exporter || "—"} />
          <KPIWidget label="Service" value={otel.service_name} />
          <KPIWidget label="SDK"
            value={otel.sdk_available ? "loaded" : "noop"}
            status={otel.sdk_available ? "success" : "neutral"} />
        </div>
      </Card>

      <Card>
        <CardHeader title="Instrumentations" />
        <div className="flex flex-wrap gap-2">
          {otel.instrumentations.length === 0 && (
            <div className="text-ink-400 text-xs italic">
              No SDK loaded — running in Noop mode.
              <br />
              Install <code className="text-gold-300">opentelemetry-sdk</code> to enable.
            </div>
          )}
          {otel.instrumentations.map((i) => (
            <Badge key={i} size="sm" status="success">{i}</Badge>
          ))}
        </div>
      </Card>
    </div>
  );
}

// ===========================================================================
// Metrics — Datadog dual-mode, snapshot + test
// ===========================================================================

function MetricsTab() {
  const [dd, setDd] = useState<DatadogStatus | null>(null);
  const [snapshot, setSnapshot] = useState<unknown>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function refresh() {
    const r = await apiClient.get("/observability/datadog/status");
    setDd(r.data);
  }

  async function takeSnapshot() {
    setBusy("snapshot");
    try {
      const r = await apiClient.post("/observability/datadog/snapshot");
      setSnapshot(r.data);
    } finally { setBusy(null); }
  }

  async function emitTest() {
    setBusy("test");
    try {
      await apiClient.post("/observability/datadog/test");
      await refresh();
    } finally { setBusy(null); }
  }

  useEffect(() => { refresh(); }, []);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader
          icon={<BarChart3 size={14} />}
          title="Datadog exporter"
          action={
            <div className="flex gap-2">
              <button
                onClick={emitTest}
                disabled={!!busy}
                className="px-3 py-1 text-xs bg-ink-700 hover:bg-ink-600 disabled:opacity-40 text-ink-100 rounded-md"
              >
                {busy === "test" ? "…" : "Emit test metric"}
              </button>
              <button
                onClick={takeSnapshot}
                disabled={!!busy}
                className="px-3 py-1 text-xs bg-gold-500/20 hover:bg-gold-500/30 disabled:opacity-40 text-gold-300 rounded-md border border-gold-500/30"
              >
                {busy === "snapshot" ? "…" : "Snapshot now"}
              </button>
            </div>
          }
        />
        {dd && (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <KPIWidget label="Mode" value={dd.mode}
              status={dd.mode === "cloud" ? "success" : "neutral"} />
            <KPIWidget label="Site" value={dd.site} />
            <KPIWidget label="Default tags" value={dd.default_tags.length} />
            <KPIWidget label="Local file"
              value={dd.log_file_path ? "configured" : "—"} />
          </div>
        )}
      </Card>

      {snapshot != null && (
        <Card>
          <CardHeader title="Last snapshot" />
          <pre className="font-mono text-[11px] text-ink-300 max-h-[320px] overflow-auto p-2 bg-ink-900 rounded">
            {JSON.stringify(snapshot, null, 2)}
          </pre>
        </Card>
      )}
    </div>
  );
}

// ===========================================================================
// Logs — audit tail (real WS-ready, polling fallback)
// ===========================================================================

function LogsTab() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [filter, setFilter] = useState("");
  const [actionFilter, setActionFilter] = useState("");

  async function refresh() {
    try {
      const r = await apiClient.get(
        "/analytics/audit/tail?limit=100" +
          (actionFilter ? `&action=${encodeURIComponent(actionFilter)}` : ""),
      );
      setEvents(r.data as AuditEvent[]);
    } catch (e) { console.error(e); }
  }

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 5_000);
    return () => clearInterval(t);
  }, [actionFilter]);

  const visible = events.filter((e) => {
    if (!filter) return true;
    const q = filter.toLowerCase();
    return e.actor.toLowerCase().includes(q) ||
           e.action.toLowerCase().includes(q);
  });

  return (
    <Card>
      <CardHeader
        icon={<Filter size={14} />}
        title="Audit log tail (5s refresh)"
        action={
          <div className="flex gap-2 items-center flex-wrap">
            <div className="relative">
              <Search size={12} className="absolute left-2 top-1.5 text-ink-400" />
              <input
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                placeholder="Search actor/action…"
                className="pl-7 pr-2 py-1 text-xs bg-ink-800 border border-ink-700 rounded-md text-ink-100 placeholder:text-ink-500 focus:outline-none focus:border-gold-400/50"
              />
            </div>
            <select
              value={actionFilter}
              onChange={(e) => setActionFilter(e.target.value)}
              className="px-2 py-1 text-xs bg-ink-800 border border-ink-700 rounded-md text-ink-100 focus:outline-none"
            >
              <option value="">All actions</option>
              <option value="workflow_task_failed">workflow_task_failed</option>
              <option value="autonomy_decision">autonomy_decision</option>
              <option value="login">login</option>
            </select>
          </div>
        }
      />
      <div className="space-y-1.5 max-h-[600px] overflow-y-auto font-mono text-[11px]">
        {visible.length === 0 && (
          <div className="text-ink-400 py-6 text-center italic">No events.</div>
        )}
        {visible.map((e) => (
          <div
            key={e.event_id}
            className="px-2 py-1.5 rounded hover:bg-ink-800/50 flex items-start gap-2 border-l-2 border-transparent hover:border-gold-400/40"
          >
            <HealthDot
              status={
                e.action.includes("failed") || e.action.includes("error") ? "error"
                : e.action.includes("warn") ? "warning"
                : e.action.includes("login") ? "info"
                : "success"
              }
              size="sm"
            />
            <span className="text-ink-500 shrink-0">
              {new Date(e.created_at).toISOString().substring(11, 19)}
            </span>
            <Badge size="sm" status="neutral">{e.action}</Badge>
            <span className="text-ink-300 truncate flex-1" title={e.actor}>
              {e.actor}
            </span>
          </div>
        ))}
      </div>
    </Card>
  );
}

// ===========================================================================
// Errors — Sentry grouped issues
// ===========================================================================

function ErrorsTab() {
  const [sentry, setSentry] = useState<SentryStatus | null>(null);
  const [data, setData] = useState<{ groups: SentryError[]; events: unknown[] } | null>(null);
  const [busy, setBusy] = useState(false);

  async function refresh() {
    const [s, e] = await Promise.all([
      apiClient.get("/observability/sentry/status"),
      apiClient.get("/observability/sentry/errors?limit=100"),
    ]);
    setSentry(s.data);
    setData(e.data);
  }

  async function emitTest() {
    setBusy(true);
    try {
      await apiClient.post("/observability/sentry/test", {
        message: "Manual UI test from /observability dashboard",
      });
      await refresh();
    } finally { setBusy(false); }
  }

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 15_000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader
          icon={<AlertTriangle size={14} />}
          title="Sentry integration"
          action={
            <button
              onClick={emitTest}
              disabled={busy}
              className="px-3 py-1 text-xs bg-ink-700 hover:bg-ink-600 disabled:opacity-40 text-ink-100 rounded-md"
            >
              {busy ? "…" : "Emit test event"}
            </button>
          }
        />
        {sentry && (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <KPIWidget label="Mode" value={sentry.mode}
              status={sentry.mode === "cloud" ? "success" : "neutral"} />
            <KPIWidget label="Environment" value={sentry.environment} />
            <KPIWidget label="Release" value={sentry.release} />
            <KPIWidget label="Sample rate" value={sentry.sample_rate.toFixed(2)} />
          </div>
        )}
      </Card>

      <Card>
        <CardHeader title="Recent grouped issues" />
        {!data || data.groups?.length === 0 ? (
          <div className="text-ink-400 text-xs italic py-4 text-center">
            {sentry?.mode === "cloud"
              ? "Cloud mode — open the Sentry dashboard for live data."
              : "No grouped issues recorded yet."}
          </div>
        ) : (
          <div className="space-y-1.5">
            {data.groups.map((g) => (
              <div key={g.fingerprint}
                className="px-2 py-2 rounded hover:bg-ink-800/50 border-l-2 border-error-500/40 flex items-start gap-2"
              >
                <Badge size="sm" status="error">{g.count}×</Badge>
                <div className="flex-1 min-w-0">
                  <div className="text-ink-100 text-[12px] truncate">
                    {g.exc_type}: {g.message}
                  </div>
                  <div className="text-[10px] text-ink-500 font-mono">
                    {g.fingerprint} · last {g.last_seen ? new Date(g.last_seen).toLocaleString() : "—"}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

// ===========================================================================
// CI / CD — workflow inventory + last commit hint
// ===========================================================================

function CiCdTab() {
  // The frontend doesn't have privileged GitHub access; surface what we can:
  // workflow definitions present and the recent audit entries that indicate deploys.
  const workflows = [
    { name: "test.yml",              purpose: "Lint, typecheck, security, tests, build (PR + push)" },
    { name: "deploy-staging.yml",    purpose: "Auto-deploy main → staging.uba.dendani.dz" },
    { name: "deploy-production.yml", purpose: "Release tags v*.*.*  (manual approval + rollback)" },
    { name: "security-scan.yml",     purpose: "Daily 03:00 UTC: deps, SAST, container, secrets" },
    { name: "performance.yml",       purpose: "PR benchmark vs main (fail if p99 > +20%)" },
    { name: "ci.yml",                purpose: "Legacy CI (kept for compatibility)" },
    { name: "deploy.yml",            purpose: "Legacy deploy (kept for compatibility)" },
  ];

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader icon={<GitBranch size={14} />} title="Workflows under .github/workflows/" />
        <div className="space-y-2">
          {workflows.map((w) => (
            <div key={w.name}
              className="px-3 py-2 rounded bg-ink-900/40 border border-ink-700 flex items-start gap-3"
            >
              <Badge size="sm" status="neutral">{w.name}</Badge>
              <div className="flex-1 text-[12px] text-ink-300">{w.purpose}</div>
            </div>
          ))}
        </div>
      </Card>

      <Card>
        <CardHeader title="Quality gates" />
        <ul className="text-[12px] text-ink-300 space-y-1 list-disc pl-4">
          <li>PRs must pass lint + typecheck + security + tests + build (test.yml).</li>
          <li>Performance regression &gt; +20% p99 vs main blocks merge (performance.yml).</li>
          <li>Daily scan files automated triage issues for HIGH+ findings.</li>
          <li>Production deploys require manual approval and run a smoke suite + auto-rollback on failure.</li>
        </ul>
      </Card>
    </div>
  );
}
