import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, post } from "../api";
import { filterSummary } from "../filterSummary";
import { STATUS_LABELS } from "../format";
import type { Filters, Job, Profile, Source } from "../types";

/** Agent görevini mevcut filtrelerle veya bir profille başlatır; kaynak seçimi burada yapılır. */
export default function StartJobDialog({ filters, profile, onClose }: { filters: Filters; profile?: Profile | null; onClose: () => void }) {
  const [sources, setSources] = useState<Source[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const navigate = useNavigate();
  const activeFilters = profile ? profile.filters : filters;
  const isDemo = activeFilters.data_mode === "demo";
  // Seçilebilir kaynak: etkin, erişimi reddedilmemiş, hazır (dosya yüklenmiş vb.) ve veri moduna uygun.
  const isUsable = (s: Source) => s.enabled && s.status !== "access_denied" && s.ready !== false && (s.key === "demo") === isDemo;
  const reasonOf = (s: Source) => {
    if (!s.enabled) return "Devre dışı";
    if ((s.key === "demo") !== isDemo) return isDemo ? "Gerçek veri kaynağı" : "Yalnızca DEMO modunda";
    if (s.ready === false) return s.ready_message ?? "Hazır değil";
    return STATUS_LABELS[s.status] ?? s.status;
  };

  useEffect(() => {
    api<Source[]>("/api/sources").then((list) => {
      setSources(list);
      setSelected(list.filter(isUsable).map((s) => s.key));
      setLoaded(true);
    }).catch((exc) => setError((exc as Error).message));
    // isUsable yalnızca isDemo'ya bağlıdır.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isDemo]);

  const summary = filterSummary(activeFilters);
  const usableCount = sources.filter(isUsable).length;
  // Seçili gerçek kaynakların son durum mesajı (örn. Sahibinden engeli, son yüklenen dosya) başlatmadan önce görünür.
  const lastStatus = sources.filter((s) => selected.includes(s.key) && s.key !== "demo" && s.status_message);
  const looksFailed = (s: Source) => s.status === "error" || /çekilemedi|engel|hata|reddedildi/i.test(s.status_message);

  async function start() {
    setBusy(true);
    setError(null);
    try {
      const job = await post<Job>("/api/agent/jobs", { filters: activeFilters, source_keys: selected, profile_id: profile?.id ?? null });
      navigate(`/agent?job=${job.id}`);
      onClose();
    } catch (exc) {
      setError((exc as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="dialog-backdrop" role="dialog" aria-modal="true" aria-labelledby="start-job-title" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="panel dialog">
        <div className="panel-head"><h2 id="start-job-title">Analizi başlat</h2></div>
        <div className="panel-body stack" style={{ gap: 12 }}>
          <p className="muted" style={{ margin: 0 }}>
            {profile ? `“${profile.name}” profili` : "Ana sayfadaki filtreler"} ile veri toplanır, piyasa analizi ve fırsat puanlaması yapılır.
            {isDemo && " DEMO modunda yalnızca sentetik test verisi kullanılır."}
          </p>
          <div>
            <span className="small muted">Tarama bu filtrelerle çalışacak</span>
            <dl className="kv job-summary">
              {summary.map(([label, value]) => (
                <div key={label} style={{ display: "contents" }}><dt>{label}</dt><dd>{value}</dd></div>
              ))}
            </dl>
          </div>
          <fieldset style={{ border: 0, padding: 0, margin: 0, display: "grid", gap: 6 }}>
            <legend className="small muted" style={{ marginBottom: 6 }}>Veri kaynakları</legend>
            {sources.map((source) => {
              const blocked = !isUsable(source);
              return (
                <label key={source.key} className="check" style={{ opacity: blocked ? 0.55 : 1 }} title={source.status_message || undefined}>
                  <input type="checkbox" disabled={blocked} checked={selected.includes(source.key)}
                    onChange={(e) => setSelected((list) => (e.target.checked ? [...list, source.key] : list.filter((k) => k !== source.key)))} />
                  <span>{source.name}</span>
                  <span className="small muted">{reasonOf(source)}</span>
                </label>
              );
            })}
          </fieldset>
          {loaded && usableCount === 0 && (
            <div className="notice warn" role="status">
              {isDemo
                ? "DEMO kaynağı kapalı. Tarama ayarları → Veri kaynakları bölümünden “DEMO / Test Verisi”ni etkinleştirin."
                : "Gerçek veri için hazır bir kaynak yok. Tarama ayarları → Dosya içe aktarma bölümünden ilan dosyası (Excel/CSV) yükleyin; şablonlar proje klasöründeki sablonlar/ içinde. Denemek için ana sayfada DEMO moduna da geçebilirsiniz."}
            </div>
          )}
          {lastStatus.map((s) => (
            <div key={s.key} className={`notice${looksFailed(s) ? " warn" : ""}`} role="status">
              <span><strong>{s.name}</strong> · son durum: {s.status_message}</span>
            </div>
          ))}
          {error && <div className="notice bad" role="alert">{error}</div>}
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
            <button className="btn ghost" onClick={onClose}>Vazgeç</button>
            <button className="btn primary" disabled={busy || selected.length === 0} onClick={start}>{busy ? "Başlatılıyor…" : "Başlat"}</button>
          </div>
        </div>
      </div>
    </div>
  );
}
