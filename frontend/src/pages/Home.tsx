import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, post } from "../api";
import FilterPanel from "../components/FilterPanel";
import OpportunityCard, { ScoreLabel } from "../components/OpportunityCard";
import StartJobDialog from "../components/StartJobDialog";
import { useApp, useEvents } from "../context";
import { ageText, CATEGORY_LABELS, dateTime, EMPTY_FILTERS, money, num, pct, place, sizeText } from "../format";
import type { CatalogOptions, Filters, Item, Job, Profile } from "../types";

const STORAGE_KEY = "hky.filters";
const PAGE_SIZE = 20;
const SORTS = [
  ["score", "Fırsat skoru"], ["advantage", "En yüksek fiyat avantajı"], ["price_asc", "En ucuz"],
  ["price_desc", "En pahalı"], ["unit_asc", "En düşük TL/m²"], ["newest", "En yeni"],
] as const;

function loadFilters(): Filters {
  try {
    const saved = sessionStorage.getItem(STORAGE_KEY);
    return saved ? { ...EMPTY_FILTERS, ...JSON.parse(saved) } : EMPTY_FILTERS;
  } catch {
    return EMPTY_FILTERS;
  }
}

type Results = { total: number; items: Item[] };

export default function Home() {
  const { isAdmin, publicSettings } = useApp();
  const navigate = useNavigate();
  const [draft, setDraft] = useState<Filters>(loadFilters);
  const [applied, setApplied] = useState<Filters>(loadFilters);
  const [sort, setSort] = useState<(typeof SORTS)[number][0]>("score");
  const [page, setPage] = useState(1);
  const [results, setResults] = useState<Results | null>(null);
  const [opportunities, setOpportunities] = useState<Item[] | null>(null);
  const [meta, setMeta] = useState<{ last_completed_at: string | null; disclaimer: string } | null>(null);
  const [hasDemo, setHasDemo] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [dialog, setDialog] = useState<{ profile: Profile | null } | null>(null);
  const refreshTimer = useRef<number>(0);
  const minimum = publicSettings?.agent.min_opportunities ?? 3;

  const load = useCallback(async () => {
    setError(null);
    try {
      const [found, all, info] = await Promise.all([
        post<Results>("/api/listings/search", { filters: { ...applied, only_opportunities: true }, sort: "score", page: 1, page_size: 6 }),
        post<Results>("/api/listings/search", { filters: applied, sort, page, page_size: PAGE_SIZE }),
        api<{ last_completed_at: string | null; disclaimer: string }>(`/api/opportunities?data_mode=${applied.data_mode}&limit=1`),
      ]);
      setOpportunities(found.items);
      setResults(all);
      setMeta(info);
    } catch (exc) {
      setError((exc as Error).message);
    }
  }, [applied, sort, page]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    api<CatalogOptions>("/api/catalog/options").then((o) => setHasDemo(o.has_demo)).catch(() => undefined);
  }, []);

  // Agent yeni fırsat bulduğunda veya görev bittiğinde liste kendini yeniler.
  useEvents((event, data) => {
    const finished = event === "job.updated" && ["completed", "stopped"].includes((data as Job).status);
    if (event === "opportunity.found" || finished) {
      window.clearTimeout(refreshTimer.current);
      refreshTimer.current = window.setTimeout(load, 1500);
      if (finished) api<CatalogOptions>("/api/catalog/options").then((o) => setHasDemo(o.has_demo)).catch(() => undefined);
    }
  });

  const apply = (next: Filters = draft) => {
    setApplied(next);
    setPage(1);
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
      /* depolama kapalıysa filtreler yalnızca bu oturumda kalır */
    }
  };

  // Tarama, panelde o an görünen filtrelerle başlar; aynı filtreler sonuç listesine de uygulanır.
  const startWithCurrentFilters = () => {
    apply(draft);
    setFiltersOpen(false);
    setDialog({ profile: null });
  };

  const setMode = (data_mode: Filters["data_mode"]) => {
    const next = { ...draft, data_mode };
    setDraft(next);
    apply(next);
  };

  const best = opportunities?.[0];
  const finding = best?.score
    ? `En güçlü fırsat ${place(best.listing)} · ${best.listing.rooms ?? best.listing.series ?? ""}: emsal medyanının ${pct(best.score.discount_pct)} altında.`
    : "Bu filtrelere uyan ve fırsat kriterlerini karşılayan ilan henüz yok.";
  const isDemo = applied.data_mode === "demo";

  return (
    <>
      <div className="title-row">
        <div>
          <h1>Fırsatlar</h1>
          <p className="sub">
            {opportunities === null ? "Yükleniyor…" : finding}
            {meta?.last_completed_at && <> Son analiz {dateTime(meta.last_completed_at)}.</>}
          </p>
        </div>
        <div className="title-actions">
          {(hasDemo || isDemo) && (
            <div className="seg" role="group" aria-label="Veri modu">
              <button aria-pressed={!isDemo} onClick={() => setMode("real")}>Gerçek veri</button>
              <button aria-pressed={isDemo} onClick={() => setMode("demo")}>DEMO</button>
            </div>
          )}
          <button className="btn filters-toggle" onClick={() => setFiltersOpen(true)}>Filtreler</button>
          {isAdmin && <button className="btn primary" onClick={startWithCurrentFilters}>Analizi başlat</button>}
        </div>
      </div>

      {isDemo && (
        <div className="notice warn" style={{ marginBottom: 20 }}>
          <span className="demo-tag">DEMO</span>
          <span>Sentetik test verisi gösteriliyor. Bu ilanlar gerçek değildir ve gerçek piyasa analizine dahil edilmez.</span>
        </div>
      )}

      <div className="home">
        <FilterPanel filters={draft} onChange={setDraft} onApply={() => apply()} open={filtersOpen} onClose={() => setFiltersOpen(false)}
          onRunProfile={(profile) => setDialog({ profile })} />

        <div className="stack">
          {error && <div className="notice bad" role="alert">{error} <button className="btn sm" onClick={load}>Tekrar dene</button></div>}

          <section className="panel" aria-labelledby="opps-title">
            <div className="panel-head">
              <h2 id="opps-title">FIRSATLAR</h2>
              <span className="small muted num">{opportunities ? `${opportunities.length} fırsat` : ""}</span>
            </div>
            <div className="panel-body stack" style={{ gap: 16 }}>
              {opportunities === null && <div className="opp-grid">{[0, 1, 2].map((i) => <div key={i} className="opp" style={{ height: 420 }} />)}</div>}
              {opportunities && opportunities.length === 0 && (
                <div className="empty">
                  Fırsat kriterlerini (skor, fiyat avantajı, emsal sayısı) karşılayan ilan yok. Düşük kaliteli ilanlar sayıyı doldurmak için gösterilmez.
                  {isAdmin && <> <button className="btn sm" onClick={startWithCurrentFilters}>Bu filtrelerle analiz başlat</button></>}
                </div>
              )}
              {opportunities && opportunities.length > 0 && (
                <>
                  <div className="opp-grid">
                    {opportunities.map((item) => item.score && <OpportunityCard key={item.listing.id} listing={item.listing} score={item.score} />)}
                  </div>
                  {opportunities.length < minimum && (
                    <div className="notice">Kriterleri karşılayan {opportunities.length} fırsat var (hedef {minimum}). Sayıyı doldurmak için kriterler gevşetilmedi.</div>
                  )}
                </>
              )}
            </div>
          </section>

          <section className="panel" aria-labelledby="results-title">
            <div className="panel-head">
              <h2 id="results-title">Filtreye uyan ilanlar <span className="small muted num">{results ? `· ${num(results.total)}` : ""}</span></h2>
              <label className="small muted" style={{ display: "flex", gap: 8, alignItems: "center" }}>
                Sırala
                <select className="input" style={{ width: "auto", height: 30 }} value={sort} onChange={(e) => { setSort(e.target.value as typeof sort); setPage(1); }}>
                  {SORTS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
              </label>
            </div>
            {results === null ? (
              <div className="panel-body muted">Yükleniyor…</div>
            ) : results.items.length === 0 ? (
              <div className="panel-body"><div className="empty">Bu filtrelere uyan ilan yok. Tarih aralığını genişletin veya veri kaynağından yeni ilan toplayın.</div></div>
            ) : (
              <>
                <div className="table-wrap">
                  <table className="table stacking">
                    <thead>
                      <tr>
                        <th>İlan</th><th className="r">Fiyat</th><th className="r">Alan / km</th><th className="r">TL/m²</th>
                        <th className="r">Tarih</th><th className="r">Avantaj</th><th className="r">Skor</th>
                      </tr>
                    </thead>
                    <tbody>
                      {results.items.map(({ listing, score }) => (
                        <tr key={listing.id} className={score ? "link" : ""} tabIndex={score ? 0 : -1}
                          onClick={() => score && navigate(`/firsat/${score.id}`)}
                          onKeyDown={(e) => e.key === "Enter" && score && navigate(`/firsat/${score.id}`)}>
                          <td>
                            <span className="cell-title">{listing.is_demo && <span className="demo-tag" style={{ marginRight: 6 }}>DEMO</span>}{listing.title}</span>
                            <span className="cell-sub">{CATEGORY_LABELS[listing.category]} · {place(listing)}</span>
                          </td>
                          <td className="r"><strong>{money(listing.price, listing.currency)}</strong></td>
                          <td className="r hide-sm">{sizeText(listing)}</td>
                          <td className="r hide-sm">{listing.price_per_m2 ? num(listing.price_per_m2) : "—"}</td>
                          <td className="r hide-sm">{ageText(listing.listed_at)}</td>
                          <td className="r hide-sm">{score ? pct(score.discount_pct) : "—"}</td>
                          <td className="r">{score ? <><span className="num">{score.score.toFixed(0)}</span> <ScoreLabel score={score} /></> : <span className="muted small">Analiz edilmedi</span>}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="pager">
                  <span className="num">{num((page - 1) * PAGE_SIZE + 1)}–{num(Math.min(page * PAGE_SIZE, results.total))} / {num(results.total)}</span>
                  <span style={{ display: "flex", gap: 6 }}>
                    <button className="btn sm" disabled={page === 1} onClick={() => setPage((p) => p - 1)}>Önceki</button>
                    <button className="btn sm" disabled={page * PAGE_SIZE >= results.total} onClick={() => setPage((p) => p + 1)}>Sonraki</button>
                  </span>
                </div>
              </>
            )}
          </section>
          {meta && <p className="small muted" style={{ margin: 0 }}>{meta.disclaimer}</p>}
        </div>
      </div>
      {dialog && <StartJobDialog filters={draft} profile={dialog.profile} onClose={() => setDialog(null)} />}
    </>
  );
}
