import { useCallback, useEffect, useState } from "react";
import { api, ApiError, del, post, put } from "../api";
import { dateTime, STATUS_LABELS } from "../format";
import type { AppSettings, Source } from "../types";

type Batch = { id: number; filename: string; row_count: number; dropped_columns: string[]; created_at: string };
type LinkResult = { url: string; status: string; message: string };
const TABS = [["sources", "Veri kaynakları"], ["scan", "Tarama"], ["proxy", "Proxy"], ["agent", "Agent"], ["notifications", "Bildirimler"]] as const;
const SOURCE_TONE: Record<string, string> = { ok: "good", error: "bad", access_denied: "bad", not_configured: "" };

function NumberField({ label, value, onChange, hint }: { label: string; value: number | null; onChange: (v: number) => void; hint?: string }) {
  return (
    <label className="field"><span>{label}</span>
      <input className="input num" inputMode="numeric" value={value ?? ""} onChange={(e) => onChange(Number(e.target.value.replace(/[^\d.]/g, "")) || 0)} />
      {hint && <span className="small">{hint}</span>}
    </label>
  );
}

function SourceCard({ source, onChanged }: { source: Source; onChanged: (s: Source) => void }) {
  const [config, setConfig] = useState(source.config);
  const [apiKey, setApiKey] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(task: () => Promise<Source>, success?: string) {
    setBusy(true);
    setMessage(null);
    try {
      const updated = await task();
      onChanged(updated);
      setMessage(success ?? updated.status_message);
    } catch (exc) {
      setMessage((exc as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel source" aria-label={source.name}>
      <div className="panel-head">
        <h3>{source.name}</h3>
        <span style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span className={`pill ${SOURCE_TONE[source.status] ?? ""}`}>{STATUS_LABELS[source.status] ?? source.status}</span>
          <label className="check"><input type="checkbox" checked={source.enabled} disabled={busy}
            onChange={(e) => run(() => put<Source>(`/api/sources/${source.key}`, { enabled: e.target.checked }), e.target.checked ? "Etkinleştirildi." : "Devre dışı bırakıldı.")} /> Etkin</label>
        </span>
      </div>
      <div className="panel-body stack" style={{ gap: 12 }}>
        {source.status_message && <p className="small muted" style={{ margin: 0 }}>{source.status_message}{source.last_checked_at && ` · Son kontrol ${dateTime(source.last_checked_at)}`}</p>}
        {source.key === "sahibinden" && (
          <p className="small" style={{ margin: 0 }}>
            Bu sağlayıcı yalnızca resmi API sözleşmesiyle çalışır. Sözleşme ve uç nokta dokümantasyonu eklenene kadar istek gönderilmez;
            site sayfaları okunmaz ve giriş/CAPTCHA aşılmaz. API bilgileri sunucudaki .env dosyasından okunur.
          </p>
        )}
        {source.key === "demo" && <p className="small" style={{ margin: 0 }}>Sentetik test verisi üretir. Sonuçlar her yerde DEMO etiketiyle gösterilir ve gerçek analizle karışmaz.</p>}
        {source.key === "authorized" && (
          <>
            <p className="small" style={{ margin: 0 }}>Sözleşmeli veya izinli bir veri sağlayıcının JSON beslemesi. Yanıt bir ilan listesi ve isteğe bağlı sonraki sayfa imleci içermelidir.</p>
            <div className="form-grid">
              <label className="field" style={{ gridColumn: "1 / -1" }}><span>Besleme adresi (https)</span>
                <input className="input" value={String(config.base_url ?? "")} onChange={(e) => setConfig({ ...config, base_url: e.target.value })} placeholder="https://veri.ornek-saglayici.com/v1/ilanlar" /></label>
              <label className="field"><span>Sonuç yolu</span><input className="input" value={String(config.results_path ?? "")} placeholder="items" onChange={(e) => setConfig({ ...config, results_path: e.target.value })} /></label>
              <label className="field"><span>Sonraki sayfa yolu</span><input className="input" value={String(config.next_cursor_path ?? "")} placeholder="next" onChange={(e) => setConfig({ ...config, next_cursor_path: e.target.value })} /></label>
              <label className="field"><span>İmleç parametresi</span><input className="input" value={String(config.cursor_param ?? "")} placeholder="cursor" onChange={(e) => setConfig({ ...config, cursor_param: e.target.value })} /></label>
              <label className="field"><span>Kimlik başlığı</span><input className="input" value={String(config.auth_header ?? "")} placeholder="Authorization" onChange={(e) => setConfig({ ...config, auth_header: e.target.value })} /></label>
              <label className="field"><span>Önek</span><input className="input" value={String(config.auth_prefix ?? "")} placeholder="Bearer " onChange={(e) => setConfig({ ...config, auth_prefix: e.target.value })} /></label>
              <label className="field"><span>API anahtarı</span><input className="input" type="password" autoComplete="off" value={apiKey}
                placeholder={source.api_key_set ? "Kayıtlı (değiştirmek için yazın)" : "Anahtar yok"} onChange={(e) => setApiKey(e.target.value)} /></label>
            </div>
            <label className="check"><input type="checkbox" checked={Boolean(config.authorized_use)} onChange={(e) => setConfig({ ...config, authorized_use: e.target.checked })} />
              Bu kaynaktan veri almak için yazılı iznim veya sözleşmem var.</label>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button className="btn" disabled={busy} onClick={() => run(() => put<Source>("/api/sources/authorized", { ...config, ...(apiKey ? { api_key: apiKey } : {}) }), "Kaydedildi. Bağlantıyı test edin.")}>Kaydet</button>
              {source.api_key_set && <button className="btn ghost" disabled={busy} onClick={() => run(() => put<Source>("/api/sources/authorized", { api_key: "" }), "Anahtar silindi.")}>Anahtarı sil</button>}
            </div>
          </>
        )}
        {source.key !== "manual_import" && (
          <div><button className="btn" disabled={busy} onClick={() => run(() => post<Source>(`/api/sources/${source.key}/test`))}>{busy ? "Kontrol ediliyor…" : "Bağlantıyı test et"}</button></div>
        )}
        {message && <p className="small" role="status" style={{ margin: 0 }}>{message}</p>}
      </div>
    </section>
  );
}

function Imports({ onUploaded }: { onUploaded: () => void }) {
  const [batches, setBatches] = useState<Batch[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [authorized, setAuthorized] = useState(false);
  const [links, setLinks] = useState("");
  const [linksAuthorized, setLinksAuthorized] = useState(false);
  const [linkResults, setLinkResults] = useState<LinkResult[]>([]);
  const [linksBusy, setLinksBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const load = useCallback(() => api<Batch[]>("/api/imports").then(setBatches).catch(() => undefined), []);
  useEffect(() => {
    load();
  }, [load]);

  async function upload(event: React.FormEvent) {
    event.preventDefault();
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    form.append("authorized", String(authorized));
    setMessage(null);
    try {
      const result = await api<Batch>("/api/imports", { method: "POST", body: form });
      setMessage(`${result.row_count} satır yüklendi.${result.dropped_columns.length ? ` Kişisel veri sütunları atıldı: ${result.dropped_columns.join(", ")}.` : ""} Agent merkezinden analizi başlatın.`);
      setFile(null);
      load();
      onUploaded();
    } catch (exc) {
      setMessage(exc instanceof ApiError ? exc.message : "Yükleme başarısız.");
    }
  }

  async function importLinks(event: React.FormEvent) {
    event.preventDefault();
    const urls = [...new Set(links.split(/\r?\n/).map((url) => url.trim()).filter(Boolean))];
    if (!urls.length) return;
    setLinksBusy(true);
    setMessage(null);
    setLinkResults([]);
    try {
      const result = await post<{ row_count: number; results: LinkResult[] }>("/api/imports/links", {
        urls,
        authorized: linksAuthorized,
      });
      setLinkResults(result.results);
      setMessage(`${result.row_count} bağlantıdan ilan verisi alındı. Erişim kısıtlı veya okunamayan sayfalar atlandı. Agent merkezinde “Dosya içe aktarma” kaynağını seçerek analizi başlatın.`);
      if (result.row_count) {
        setLinks("");
        load();
        onUploaded();
      }
    } catch (exc) {
      setMessage((exc as Error).message);
    } finally {
      setLinksBusy(false);
    }
  }

  return (
    <section className="panel">
      <div className="panel-head"><h3>Dosya içe aktarma</h3><span className="small muted">.xlsx · .csv · .json, en fazla 15 MB</span></div>
      <form className="panel-body stack" style={{ gap: 12 }} onSubmit={upload}>
        <p className="small" style={{ margin: 0 }}>HKYEstatesBot Excel sütunları (İlan No, Kategori, İlçe / Mahalle, Fiyat, m² (Brüt)…) doğrudan tanınır. Telefon ve satıcı adı sütunları kaydedilmeden atılır.</p>
        <input type="file" accept=".xlsx,.xls,.csv,.json" onChange={(e) => setFile(e.target.files?.[0] ?? null)} aria-label="İçe aktarılacak dosya" />
        <label className="check"><input type="checkbox" checked={authorized} onChange={(e) => setAuthorized(e.target.checked)} /> Bu dosyadaki verileri kullanma yetkim var.</label>
        <div><button className="btn" disabled={!file || !authorized}>Yükle</button></div>
        {message && <p className="small" role="status" style={{ margin: 0 }}>{message}</p>}
        {batches.length > 0 && (
          <table className="table">
            <thead><tr><th>Dosya</th><th className="r">Satır</th><th className="r">Yüklenme</th><th /></tr></thead>
            <tbody>
              {batches.map((b) => (
                <tr key={b.id}>
                  <td>{b.filename}{b.dropped_columns.length > 0 && <span className="cell-sub">Atılan: {b.dropped_columns.join(", ")}</span>}</td>
                  <td className="r">{b.row_count}</td><td className="r">{dateTime(b.created_at)}</td>
                  <td className="r"><button type="button" className="btn ghost sm" onClick={() => del(`/api/imports/${b.id}`).then(load)}>Sil</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </form>
      <form className="panel-body stack" style={{ gap: 12, borderTop: "1px solid var(--border)" }} onSubmit={importLinks}>
        <h4 style={{ margin: 0 }}>İlan sayfası bağlantıları</h4>
        <p className="small" style={{ margin: 0 }}>
          Harici ilan API’si veya JSON-LD gerekmez. Agent, izin verdiğiniz HTTPS sayfalarının görünen DOM içeriğini Playwright ile okur.
          En fazla 20 bağlantı, her biri ayrı satırda.
        </p>
        <textarea className="input" rows={4} value={links} onChange={(e) => setLinks(e.target.value)}
          placeholder="https://example.com/ilan/123" aria-label="İlan sayfası bağlantıları" />
        <label className="check"><input type="checkbox" checked={linksAuthorized} onChange={(e) => setLinksAuthorized(e.target.checked)} />
          Bu sayfalarda otomatik erişim ve ilan verilerini kullanma iznim var.</label>
        <div><button className="btn" disabled={linksBusy || !links.trim() || !linksAuthorized}>
          {linksBusy ? "Agent sayfaları inceliyor…" : "Bağlantıları oku ve içe aktar"}
        </button></div>
        {message && <p className="small" role="status" style={{ margin: 0 }}>{message}</p>}
        {linkResults.length > 0 && (
          <ul className="small" style={{ margin: 0, paddingLeft: 20 }}>
            {linkResults.map((result, index) => (
              <li key={`${result.url}-${index}`}><span className="mono">{result.url}</span> — {result.message}</li>
            ))}
          </ul>
        )}
      </form>
    </section>
  );
}

export default function Settings() {
  const [tab, setTab] = useState<(typeof TABS)[number][0]>("sources");
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [sources, setSources] = useState<Source[]>([]);
  const [proxyPassword, setProxyPassword] = useState("");
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null);
  const [permission, setPermission] = useState(typeof Notification === "undefined" ? "unsupported" : Notification.permission);

  const loadSources = useCallback(() => api<Source[]>("/api/sources").then(setSources).catch(() => undefined), []);
  useEffect(() => {
    api<AppSettings>("/api/settings").then(setSettings).catch((e) => setStatus({ ok: false, text: (e as Error).message }));
    loadSources();
  }, [loadSources]);

  if (!settings) return <p className="muted">{status?.text ?? "Ayarlar yükleniyor…"}</p>;
  const patch = <K extends keyof AppSettings>(section: K, value: Partial<AppSettings[K]>) =>
    setSettings({ ...settings, [section]: { ...(settings[section] as object), ...value } });

  async function save() {
    if (!settings) return;
    setStatus(null);
    try {
      const { proxy_password_set: _ignored, ...body } = settings;
      void _ignored;
      const saved = await put<AppSettings>("/api/settings", { ...body, ...(proxyPassword ? { proxy_password: proxyPassword } : {}) });
      setSettings(saved);
      setProxyPassword("");
      setStatus({ ok: true, text: "Ayarlar kaydedildi. Yeni görevler bu ayarlarla çalışır." });
    } catch (exc) {
      setStatus({ ok: false, text: (exc as Error).message });
    }
  }

  async function testProxy() {
    setStatus(null);
    try {
      const result = await post<{ ok: boolean; message: string }>("/api/settings/proxy/test");
      setStatus({ ok: result.ok, text: result.message });
    } catch (exc) {
      setStatus({ ok: false, text: (exc as Error).message });
    }
  }

  const { scan, proxy, agent, notifications } = settings;
  return (
    <>
      <div className="title-row">
        <div>
          <h1>Tarama ayarları</h1>
          <p className="sub">{sources.filter((s) => s.enabled).length} kaynak etkin · istekler kaynak başına dakikada {scan.per_minute}, saatte {scan.per_hour} ile sınırlı.</p>
        </div>
        {tab !== "sources" && <div className="title-actions"><button className="btn primary" onClick={save}>Kaydet</button></div>}
      </div>
      <div className="tabs" role="tablist">
        {TABS.map(([key, label]) => <button key={key} role="tab" aria-selected={tab === key} onClick={() => { setTab(key); setStatus(null); }}>{label}</button>)}
      </div>
      {status && <div className={`notice ${status.ok ? "" : "bad"}`} role="status" style={{ marginBottom: 20 }}>{status.text}</div>}

      {tab === "sources" && (
        <div className="grid-2">
          <div className="stack">{sources.filter((s) => s.key !== "manual_import").map((s) => <SourceCard key={s.key} source={s} onChanged={(u) => setSources((l) => l.map((x) => (x.key === u.key ? u : x)))} />)}</div>
          <div className="stack">
            {sources.filter((s) => s.key === "manual_import").map((s) => <SourceCard key={s.key} source={s} onChanged={(u) => setSources((l) => l.map((x) => (x.key === u.key ? u : x)))} />)}
            <Imports onUploaded={loadSources} />
          </div>
        </div>
      )}

      {tab === "scan" && (
        <section className="panel"><div className="panel-head"><h2>İstek yönetimi</h2></div>
          <div className="panel-body form-grid">
            <NumberField label="İstekler arası en az süre (ms)" value={scan.request_interval_ms} onChange={(v) => patch("scan", { request_interval_ms: v })} />
            <NumberField label="Dakikalık istek sınırı" value={scan.per_minute} onChange={(v) => patch("scan", { per_minute: v })} />
            <NumberField label="Saatlik istek sınırı" value={scan.per_hour} onChange={(v) => patch("scan", { per_hour: v })} />
            <NumberField label="Eşzamanlı istek" value={scan.max_concurrent} onChange={(v) => patch("scan", { max_concurrent: v })} />
            <NumberField label="Zaman aşımı (sn)" value={scan.timeout_seconds} onChange={(v) => patch("scan", { timeout_seconds: v })} />
            <NumberField label="Tekrar deneme (5xx, zaman aşımı)" value={scan.max_retries} onChange={(v) => patch("scan", { max_retries: v })} hint="403 hiç, 429 yalnızca Retry-After ile bir kez denenir." />
          </div>
        </section>
      )}

      {tab === "proxy" && (
        <section className="panel"><div className="panel-head"><h2>Proxy</h2><span className="small muted">Tek proxy · rotasyon yok</span></div>
          <div className="panel-body stack" style={{ gap: 14 }}>
            <p className="small" style={{ margin: 0 }}>Yalnızca kurumsal ağ çıkışı gibi izinli yönlendirme için. Erişim reddinde proxy değiştirilmez ve kısıtlamalar aşılmaz. Şifre sunucuda şifreli saklanır ve geri gösterilmez.</p>
            <div className="form-grid">
              <label className="field"><span>Tür</span><select className="input" value={proxy.scheme} onChange={(e) => patch("proxy", { scheme: e.target.value as "http" | "https" })}><option value="http">HTTP</option><option value="https">HTTPS</option></select></label>
              <label className="field"><span>Host</span><input className="input" value={proxy.host} onChange={(e) => patch("proxy", { host: e.target.value })} /></label>
              <NumberField label="Port" value={proxy.port} onChange={(v) => patch("proxy", { port: v || null })} />
              <label className="field"><span>Kullanıcı adı</span><input className="input" autoComplete="off" value={proxy.username} onChange={(e) => patch("proxy", { username: e.target.value })} /></label>
              <label className="field"><span>Şifre</span><input className="input" type="password" autoComplete="new-password" value={proxyPassword} placeholder={settings.proxy_password_set ? "Kayıtlı (değiştirmek için yazın)" : ""} onChange={(e) => setProxyPassword(e.target.value)} /></label>
            </div>
            <label className="check"><input type="checkbox" checked={proxy.authorized_use} onChange={(e) => patch("proxy", { authorized_use: e.target.checked })} /> Bu proxy'yi yalnızca izinli ağ yönlendirmesi için kullanıyorum.</label>
            <label className="check"><input type="checkbox" checked={proxy.enabled} onChange={(e) => patch("proxy", { enabled: e.target.checked })} /> Proxy etkin</label>
            <div><button className="btn" onClick={testProxy}>Bağlantıyı test et</button> <span className="small muted">Önce kaydedin.</span></div>
          </div>
        </section>
      )}

      {tab === "agent" && (
        <section className="panel"><div className="panel-head"><h2>Fırsat kriterleri</h2></div>
          <div className="panel-body form-grid">
            <NumberField label="Minimum fırsat skoru" value={agent.min_score} onChange={(v) => patch("agent", { min_score: Math.min(100, v) })} />
            <NumberField label="Minimum fiyat avantajı (%)" value={agent.min_advantage} onChange={(v) => patch("agent", { min_advantage: v })} />
            <NumberField label="Minimum emsal sayısı" value={agent.min_comparables} onChange={(v) => patch("agent", { min_comparables: v })} />
            <NumberField label="Hedef fırsat sayısı" value={agent.min_opportunities} onChange={(v) => patch("agent", { min_opportunities: v })} hint="Ulaşılamazsa kriterler gevşetilmez." />
            <label className="field"><span>NLP hassasiyeti</span><select className="input" value={agent.nlp_sensitivity} onChange={(e) => patch("agent", { nlp_sensitivity: e.target.value })}><option value="dusuk">Düşük (yalnızca güçlü ifadeler)</option><option value="orta">Orta</option><option value="yuksek">Yüksek (zayıf ifadeler dahil)</option></select></label>
            <label className="field"><span>Analiz derinliği</span><select className="input" value={agent.analysis_depth} onChange={(e) => patch("agent", { analysis_depth: e.target.value })}><option value="hizli">Hızlı (mahalle)</option><option value="standart">Standart (ilçeye kadar)</option><option value="derin">Derin (ile kadar)</option></select></label>
          </div>
        </section>
      )}

      {tab === "notifications" && (
        <section className="panel"><div className="panel-head"><h2>Bildirimler</h2></div>
          <div className="panel-body stack" style={{ gap: 12 }}>
            <label className="check"><input type="checkbox" checked={notifications.popup} onChange={(e) => patch("notifications", { popup: e.target.checked })} /> Uygulama içi pop-up</label>
            <label className="check"><input type="checkbox" checked={notifications.browser} onChange={(e) => patch("notifications", { browser: e.target.checked })} /> Tarayıcı / masaüstü bildirimi</label>
            <div className="small muted">
              Tarayıcı izni: {permission === "granted" ? "verildi" : permission === "denied" ? "reddedildi (tarayıcı ayarlarından açın)" : permission === "unsupported" ? "desteklenmiyor" : "sorulmadı"}
              {permission === "default" && <> <button className="btn sm" onClick={() => Notification.requestPermission().then(setPermission)}>İzin iste</button></>}
            </div>
            <div className="form-grid">
              <NumberField label="Bildirim skoru (bu değerin üstü)" value={notifications.min_score} onChange={(v) => patch("notifications", { min_score: Math.min(100, v) })} />
              <NumberField label="Tekrar engelleme süresi (saat)" value={notifications.dedupe_hours} onChange={(v) => patch("notifications", { dedupe_hours: v })} />
            </div>
            <label className="check"><input type="checkbox" checked={notifications.dedupe} onChange={(e) => patch("notifications", { dedupe: e.target.checked })} /> Aynı ilan için tekrar bildirim gönderme</label>
          </div>
        </section>
      )}
    </>
  );
}
