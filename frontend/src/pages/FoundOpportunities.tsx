import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api";
import OpportunityCard from "../components/OpportunityCard";
import { useEvents } from "../context";
import { dateTime } from "../format";
import type { FoundItem } from "../types";

type Mode = "real" | "demo";
type Page = { total: number; page: number; page_size: number; items: FoundItem[] };

const PAGE_SIZE = 24;

/** Agent'ın bulduğu her fırsatın kalıcı kaydı. Yeni fırsat geldikçe kendini yeniler. */
export default function FoundOpportunities() {
  // Mod adres çubuğunda tutulur (?mod=demo): popup'tan gelince doğru veri modu açılır.
  const [params, setParams] = useSearchParams();
  const mode: Mode = params.get("mod") === "demo" ? "demo" : "real";
  const setMode = (next: Mode) => setParams(next === "demo" ? { mod: "demo" } : {}, { replace: true });
  const [items, setItems] = useState<FoundItem[] | null>(null);
  const [total, setTotal] = useState(0);
  const [pages, setPages] = useState(1);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback((pageCount: number) => {
    setError(null);
    api<Page>(`/api/opportunities/found?data_mode=${mode}&page=1&page_size=${PAGE_SIZE * pageCount}`)
      .then((r) => {
        setItems(r.items);
        setTotal(r.total);
      })
      .catch((e) => setError((e as Error).message));
  }, [mode]);

  useEffect(() => {
    setItems(null);
    setPages(1);
    load(1);
  }, [load]);

  useEvents((event, data) => {
    if (event === "opportunity.found" && Boolean((data as { is_demo?: boolean }).is_demo) === (mode === "demo")) load(pages);
  });

  const more = () => {
    const next = pages + 1;
    setPages(next);
    load(next);
  };

  return (
    <>
      <div className="title-row">
        <div>
          <h1>Bulunan fırsatlar</h1>
          <p className="sub">
            {items === null
              ? "Yükleniyor…"
              : `${total} fırsat kayıtlı. Agent'ın fırsat olarak işaretlediği her ilan burada saklanır; en yeni bulunan en üstte.`}
          </p>
        </div>
        <div className="title-actions">
          <div className="seg" role="group" aria-label="Veri modu">
            <button aria-pressed={mode === "real"} onClick={() => setMode("real")}>Gerçek veri</button>
            <button aria-pressed={mode === "demo"} onClick={() => setMode("demo")}>DEMO</button>
          </div>
        </div>
      </div>

      {error && <div className="notice bad" role="alert">{error} <button className="btn sm" onClick={() => load(pages)}>Tekrar dene</button></div>}

      {items?.length === 0 && (
        <div className="empty">
          Henüz kayıtlı fırsat yok. Agent bir fırsat bulduğunda ekranda bir pencere açılır ve ilan burada saklanır.
        </div>
      )}

      {items === null && <div className="opp-grid">{[0, 1, 2].map((i) => <div key={i} className="opp" style={{ height: 420 }} />)}</div>}

      {items && items.length > 0 && (
        <div className="opp-grid">
          {items.map((item) => (
            <div key={item.listing.id} className="found-item">
              <div className="found-meta">
                <span title={`İlk bulunma: ${dateTime(item.first_found_at)}`}>Bulundu: {dateTime(item.last_found_at)}</span>
                <span style={{ display: "flex", gap: 6 }}>
                  {item.times_found > 1 && <span className="pill info">{item.times_found} taramada</span>}
                  {!item.still_opportunity && <span className="pill warn" title="Son taramada fırsat kriterlerini karşılamadı veya ilan yayından kalktı.">Artık fırsat değil</span>}
                </span>
              </div>
              <OpportunityCard listing={item.listing} score={item.score} />
            </div>
          ))}
        </div>
      )}

      {items && items.length < total && (
        <div style={{ display: "flex", justifyContent: "center", marginTop: 20 }}>
          <button className="btn" onClick={more}>Daha fazla göster ({total - items.length})</button>
        </div>
      )}
    </>
  );
}
