import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, post } from "../api";
import StartJobDialog from "../components/StartJobDialog";
import { useApp, useEvents } from "../context";
import { DASH, dateTime, EMPTY_FILTERS, num, SOURCE_LABELS, STATUS_LABELS } from "../format";
import type { Filters, Job, LogLine } from "../types";

type DeadLetter = { id: number; source_key: string; url: string; status_code: number | null; error: string; attempts: number; created_at: string };

const STATUS_TONE: Record<string, string> = { running: "info", queued: "info", completed: "good", failed: "bad", stopped: "warn", paused: "warn", interrupted: "warn" };
const ACTIVE = ["running", "queued", "pausing", "stopping"];
const POLL_MS = 3000;
const STAGE_LABELS: Record<string, string> = { collect: "Veri toplama", ingest: "Normalizasyon ve kayıt", analyze: "Piyasa analizi, NLP ve skor", rank: "Sıralama" };
const ACTIONS: { action: string; label: string; when: string[]; tone?: string }[] = [
  { action: "pause", label: "Duraklat", when: ["queued", "running"] },
  { action: "resume", label: "Devam ettir", when: ["paused", "interrupted"] },
  { action: "stop", label: "Tamamen durdur", when: ["queued", "running", "paused", "pausing", "interrupted"], tone: "danger" },
  { action: "restart", label: "Yeniden başlat", when: ["completed", "stopped", "failed", "interrupted"] },
];

function storedFilters(): Filters {
  try {
    return { ...EMPTY_FILTERS, ...JSON.parse(sessionStorage.getItem("hky.filters") ?? "{}") };
  } catch {
    return EMPTY_FILTERS;
  }
}

export default function AgentCenter() {
  const { isAdmin } = useApp();
  const [params, setParams] = useSearchParams();
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [logs, setLogs] = useState<LogLine[]>([]);
  const [deadLetters, setDeadLetters] = useState<DeadLetter[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [dialog, setDialog] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);
  const refetchTimer = useRef(0);
  const selectedId = params.get("job") ?? jobs?.[0]?.id ?? null;

  const loadJobs = useCallback(() => api<Job[]>("/api/agent/jobs?limit=30").then(setJobs).catch((e) => setError((e as Error).message)), []);
  const loadJob = useCallback(async (id: string): Promise<Job | null> => {
    try {
      const detail = await api<Job>(`/api/agent/jobs/${id}`);
      setJob(detail);
      if (isAdmin && detail.dead_letters) setDeadLetters(await api<DeadLetter[]>(`/api/agent/jobs/${id}/dead-letters`));
      else setDeadLetters([]);
      return detail;
    } catch (exc) {
      setError((exc as Error).message);
      return null;
    }
  }, [isAdmin]);

  useEffect(() => {
    loadJobs();
  }, [loadJobs]);

  useEffect(() => {
    if (!selectedId) return;
    loadJob(selectedId);
    api<LogLine[]>(`/api/agent/jobs/${selectedId}/logs`).then(setLogs).catch(() => setLogs([]));
  }, [selectedId, loadJob]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [logs]);

  useEvents((event, data) => {
    if (event === "job.updated") {
      const updated = data as Job;
      setJobs((list) => (list?.some((j) => j.id === updated.id) ? list.map((j) => (j.id === updated.id ? { ...j, ...updated } : j)) : [updated, ...(list ?? [])]));
      if (updated.id === selectedId) {
        setJob((current) => (current ? { ...current, ...updated } : updated));
        window.clearTimeout(refetchTimer.current);
        refetchTimer.current = window.setTimeout(() => loadJob(updated.id), 1200);
      }
    }
    if (event === "job.log" && (data as { job_id: string }).job_id === selectedId) {
      setLogs((list) => [...list.slice(-299), data as LogLine]);
    }
  });

  async function control(action: string) {
    if (!job) return;
    setError(null);
    try {
      const result = await post<Job>(`/api/agent/jobs/${job.id}/${action}`);
      if (action === "restart") {
        setParams({ job: result.id });
        loadJobs();
      } else {
        setJob(result);
      }
    } catch (exc) {
      setError((exc as Error).message);
    }
  }

  const queue = job?.queue ?? {};
  const active = !!job && ACTIVE.includes(job.status);
  const activeId = active ? job.id : null;

  // Canlı bağlantı (SSE) koparsa ekran takılı kalmasın: görev sürerken düzenli olarak yeniden okunur.
  useEffect(() => {
    if (!activeId) return;
    const timer = window.setInterval(async () => {
      const detail = await loadJob(activeId);
      api<LogLine[]>(`/api/agent/jobs/${activeId}/logs`).then(setLogs).catch(() => undefined);
      if (detail && !ACTIVE.includes(detail.status)) loadJobs();
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [activeId, loadJob, loadJobs]);

  return (
    <>
      <div className="title-row">
        <div>
          <h1>Agent merkezi</h1>
          <p className="sub">
            {job ? <>Seçili görev {STATUS_LABELS[job.status]?.toLowerCase() ?? job.status}{active ? `, %${Math.round(job.progress)} tamamlandı` : ""}. {job.last_action}</> : "Henüz görev çalıştırılmadı."}
          </p>
        </div>
        {isAdmin && <div className="title-actions"><button className="btn primary" onClick={() => setDialog(true)}>Yeni analiz</button></div>}
      </div>
      {error && <div className="notice bad" role="alert" style={{ marginBottom: 20 }}>{error}</div>}

      {jobs !== null && jobs.length === 0 && (
        <div className="empty">Henüz görev yok. Ana sayfada filtreleri seçip “Analizi başlat” ile ilk taramayı yapın.</div>
      )}

      {job && (
        <div className="agent-grid">
          <section className="panel" aria-labelledby="job-title">
            <div className="panel-head">
              <h2 id="job-title">{job.profile_name}</h2>
              <span className={`pill ${STATUS_TONE[job.status] ?? ""}`}>{STATUS_LABELS[job.status] ?? job.status}</span>
            </div>
            <div className="panel-body stack" style={{ gap: 16 }}>
              <div style={{ display: "grid", gap: 6 }}>
                <div style={{ display: "flex", justifyContent: "space-between" }} className="small">
                  <span>{job.status === "completed" ? "Tüm aşamalar tamamlandı" : STAGE_LABELS[job.stage] ?? job.stage}</span><span className="num">%{job.progress.toFixed(0)}</span>
                </div>
                <div className="progress" role="progressbar" aria-valuenow={Math.round(job.progress)} aria-valuemin={0} aria-valuemax={100}><div style={{ width: `${job.progress}%` }} /></div>
              </div>
              <div className="metrics">
                <div className="metric"><span>İncelenen ilan</span><strong>{num(job.examined)}</strong></div>
                <div className="metric"><span>İşlenen (puanlanan)</span><strong>{num(job.processed)}</strong></div>
                <div className="metric"><span>Bulunan fırsat</span><strong style={{ color: job.opportunities ? "var(--positive)" : undefined }}>{num(job.opportunities)}</strong></div>
                <div className="metric"><span>Başarısız istek</span><strong style={{ color: job.failed_requests ? "var(--negative)" : undefined }}>{num(job.failed_requests)}</strong></div>
              </div>
              <dl className="kv">
                <dt>Görev ID</dt><dd className="mono" title={job.id}>{job.id.slice(0, 8)}…</dd>
                <dt>Veri kaynağı</dt><dd>{job.source_keys.map((k) => SOURCE_LABELS[k] ?? k).join(", ")}</dd>
                <dt>Kuyruk (kayıt)</dt><dd className="num">{num(queue.ingest_pending ?? 0)} bekleyen · {num(queue.ingest_done ?? 0)} işlendi · {num(queue.ingest_failed ?? 0)} atlandı</dd>
                <dt>Kuyruk (analiz)</dt><dd className="num">{num(queue.score_pending ?? 0)} bekleyen · {num(queue.score_done ?? 0)} puanlandı</dd>
                <dt>Dead Letter</dt><dd className="num">{job.dead_letters ? num(job.dead_letters) : "0"}</dd>
                <dt>Piyasa / fırsat aralığı</dt><dd>{job.filters.market_from ? `${job.filters.market_from} – ${job.filters.market_to ?? "bugün"}` : `${job.filters.market_window_days} gün`} / {job.filters.opportunity_from ? `${job.filters.opportunity_from} – ${job.filters.opportunity_to ?? "bugün"}` : job.filters.opportunity_window_days ? `${job.filters.opportunity_window_days} gün` : "tümü"}</dd>
                <dt>Başlangıç</dt><dd>{dateTime(job.started_at)}</dd>
                <dt>Tamamlanma</dt><dd>{dateTime(job.finished_at)}</dd>
              </dl>
              {job.error && <div className="notice bad">{job.error}</div>}
              {isAdmin && (
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {ACTIONS.filter((a) => a.when.includes(job.status)).map((a) => (
                    <button key={a.action} className={`btn ${a.tone ?? ""}`} onClick={() => control(a.action)}>{a.label}</button>
                  ))}
                </div>
              )}
            </div>
          </section>

          <section className="panel" aria-labelledby="log-title">
            <div className="panel-head"><h2 id="log-title">Görev kayıtları</h2><span className="small muted num">{logs.length} satır</span></div>
            <div className="log" ref={logRef} aria-live="polite">
              {logs.length === 0 && <p className="muted" style={{ padding: "12px 16px", margin: 0 }}>Kayıt yok.</p>}
              {logs.map((line, i) => (
                <div className="log-line" key={line.id ?? `live-${i}`}>
                  <span className="muted num">{new Date(line.at).toLocaleTimeString("tr-TR")}</span>
                  <span className={`dot ${line.level === "error" ? "bad" : line.level === "warning" ? "warn" : ""}`} aria-label={line.level} />
                  <span>{line.message}</span>
                </div>
              ))}
            </div>
          </section>
        </div>
      )}

      {deadLetters.length > 0 && (
        <section className="panel" style={{ marginTop: 20 }} aria-labelledby="dlq-title">
          <div className="panel-head"><h2 id="dlq-title">Dead Letter kayıtları</h2><span className="small muted">Kalıcı başarısız istekler</span></div>
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Kaynak</th><th>Adres</th><th className="r">Kod</th><th className="r">Deneme</th><th>Hata</th></tr></thead>
              <tbody>
                {deadLetters.map((d) => (
                  <tr key={d.id}><td>{SOURCE_LABELS[d.source_key] ?? d.source_key}</td><td className="mono">{d.url}</td><td className="r">{d.status_code ?? DASH}</td><td className="r">{d.attempts}</td><td>{d.error}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {jobs && jobs.length > 0 && (
        <section className="panel" style={{ marginTop: 20 }} aria-labelledby="history-title">
          <div className="panel-head"><h2 id="history-title">Önceki görevler</h2><span className="small muted num">{jobs.length} görev</span></div>
          <div className="table-wrap">
            <table className="table stacking">
              <thead><tr><th>Profil</th><th>Durum</th><th className="r">İncelenen</th><th className="r">Fırsat</th><th className="r">Başarısız istek</th><th className="r">Başlangıç</th></tr></thead>
              <tbody>
                {jobs.map((j) => (
                  <tr key={j.id} className="link" tabIndex={0} aria-selected={j.id === selectedId}
                    style={j.id === selectedId ? { background: "var(--panel-head)" } : undefined}
                    onClick={() => setParams({ job: j.id })} onKeyDown={(e) => e.key === "Enter" && setParams({ job: j.id })}>
                    <td><span className="cell-title">{j.profile_name}</span><span className="cell-sub">{j.source_keys.map((k) => SOURCE_LABELS[k] ?? k).join(", ")} · <span className="mono">{j.id.slice(0, 8)}</span></span></td>
                    <td><span className={`pill ${STATUS_TONE[j.status] ?? ""}`}>{STATUS_LABELS[j.status] ?? j.status}</span></td>
                    <td className="r hide-sm">{num(j.examined)}</td>
                    <td className="r">{num(j.opportunities)}</td>
                    <td className="r hide-sm">{num(j.failed_requests)}</td>
                    <td className="r hide-sm">{dateTime(j.started_at ?? j.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
      {dialog && <StartJobDialog filters={storedFilters()} onClose={() => { setDialog(false); loadJobs(); }} />}
    </>
  );
}
