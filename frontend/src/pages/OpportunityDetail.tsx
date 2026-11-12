import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { BreakdownList, ComparableHistogram, PriceHistory } from "../components/Charts";
import { confidenceClass, riskClass, ScoreLabel } from "../components/OpportunityCard";
import { CATEGORY_LABELS, DASH, dateText, dateTime, headline, money, num, pct, place, safeUrl, signedPct, sizeText } from "../format";
import type { Listing, Score } from "../types";

type Detail = {
  listing: Listing & { description: string };
  score: Score;
  nlp: { signals: { key: string; label: string; evidence: string; counted: boolean }[]; negated: { key: string; evidence: string }[]; risks: { label: string }[]; parity: boolean; price_drop_amount: number | null; terms: string[] };
  report: { summary: string; details: { comparables: { level: string | null; outliers_removed: number; coverage_days: number } }; generator: string } | null;
  comparables: Listing[];
  benchmark: {
    segment_label: string; market_days: number; coverage_days: number; sample_size: number; avg_price: number | null; median_price: number | null;
    min_price: number | null; max_price: number | null; avg_unit_price: number | null; median_unit_price: number | null; trend_pct: number | null;
    breakdowns: Record<string, { label: string; count: number; median: number }[]>;
  } | null;
  price_history: { price: number; currency: string; observed_at: string }[];
  source: { key: string; name: string; last_seen_at: string };
  disclaimer: string;
};

const FIELD_LABELS: [string, string, (v: unknown) => string][] = [
  ["rooms", "Oda", String], ["m2_gross", "Brüt m²", (v) => num(v as number)], ["m2_net", "Net m²", (v) => num(v as number)],
  ["building_age", "Bina yaşı", String], ["floor", "Bulunduğu kat", String], ["total_floors", "Kat sayısı", String],
  ["heating", "Isıtma", String], ["bathrooms", "Banyo", String], ["deed_status", "Tapu", String],
  ["brand", "Marka", String], ["series", "Seri", String], ["model", "Model", String], ["year", "Yıl", String],
  ["km", "Kilometre", (v) => `${num(v as number)} km`], ["fuel", "Yakıt", String], ["transmission", "Vites", String],
  ["paint_status", "Boya", String], ["changed_parts", "Değişen", String], ["seller_type", "Kimden", String],
];
const BOOL_LABELS: [string, string][] = [
  ["balcony", "Balkon"], ["elevator", "Asansör"], ["parking", "Otopark"], ["in_site", "Site içi"], ["credit_eligible", "Krediye uygun"],
  ["furnished", "Eşyalı"], ["damage_record", "Hasar kaydı"], ["heavy_damage", "Ağır hasar"],
];

function Panel({ title, children, aside }: { title: string; children: React.ReactNode; aside?: React.ReactNode }) {
  return (
    <section className="panel">
      <div className="panel-head"><h2>{title}</h2>{aside}</div>
      <div className="panel-body">{children}</div>
    </section>
  );
}

export default function OpportunityDetail() {
  const { scoreId } = useParams();
  const [data, setData] = useState<Detail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    api<Detail>(`/api/opportunities/${scoreId}`).then(setData).catch((exc) => setError((exc as Error).message));
  }, [scoreId]);

  if (error) return <div className="notice bad" role="alert">{error} <Link to="/">Fırsatlara dön</Link></div>;
  if (!data) return <p className="muted">Analiz yükleniyor…</p>;

  const { listing: l, score: s, nlp, benchmark: b } = data;
  const unitKind = s.reference_kind === "unit";
  const unit = unitKind ? `${l.currency}/m²` : l.currency;
  const own = unitKind ? l.price_per_m2 : l.price;
  const compValues = data.comparables.map((c) => (unitKind ? c.price_per_m2 : c.price)).filter((v): v is number => typeof v === "number");
  const link = safeUrl(l.url);
  const subscores: [string, number, number][] = [
    ["Fiyat avantajı", s.price_advantage_score, 0.4], ["Açıklama ve aciliyet", s.nlp_score, 0.3], ["İlan tazeliği", s.freshness_score, 0.3],
  ];

  return (
    <>
      <div className="title-row">
        <div>
          <p className="small muted" style={{ margin: "0 0 6px" }}><Link to="/" className="muted">Fırsatlar</Link> / {CATEGORY_LABELS[l.category]}</p>
          <h1 style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>{l.is_demo && <span className="demo-tag">DEMO</span>}{l.title || headline(l)}</h1>
          <p className="sub">{place(l)} · {money(l.price, l.currency)} · {sizeText(l)} · İlan tarihi {dateText(l.listed_at)}</p>
        </div>
        <div className="title-actions">
          {link ? <a className="btn primary" href={link} target="_blank" rel="noopener noreferrer">Orijinal ilanı aç ↗</a>
            : <span className="small muted">{l.is_demo ? "Demo ilan; orijinal bağlantı yok." : "Kaynakta bağlantı yok."}</span>}
        </div>
      </div>

      <div className="detail">
        <div className="stack">
          <Panel title="Fırsat skoru" aside={<ScoreLabel score={s} />}>
            <div className="stack" style={{ gap: 16 }}>
              <div style={{ display: "flex", gap: 24, alignItems: "baseline", flexWrap: "wrap" }}>
                <span className="score-big num" style={{ fontSize: 40 }}>{s.score.toFixed(1)}<small>/100</small></span>
                <span className="muted">Sıra {s.rank ?? DASH} · güven <span className={`pill ${confidenceClass(s.confidence_label)}`}>{s.confidence_label} %{s.confidence.toFixed(0)}</span> · risk <span className={`pill ${riskClass(s.risk_level)}`}>{s.risk_level}</span></span>
              </div>
              <div className="equation">
                {subscores.map(([label, value, weight]) => (
                  <div className="line" key={label}>
                    <span>{label} <span className="muted">×{weight.toFixed(2)}</span></span>
                    <div className="bar-track"><div className="bar-fill" style={{ width: `${value}%` }} /></div>
                    <span className="num" style={{ textAlign: "right" }}>{value.toFixed(0)}</span>
                  </div>
                ))}
              </div>
              <div className="formula">
                Skor = {subscores.map(([, v, w], i) => <span key={i}>{i ? " + " : ""}{v.toFixed(0)} × {w.toFixed(2)}</span>)} = <strong>{s.score.toFixed(1)}</strong>
              </div>
              {!s.is_opportunity && s.ineligible_reason && <div className="notice warn">Fırsat sayılmadı: {s.ineligible_reason}.</div>}
            </div>
          </Panel>

          <Panel title="Neden bu fırsatı kaçırmamalıyım?" aside={<span className="small muted">Kural tabanlı analiz · {data.report?.generator}</span>}>
            <p style={{ margin: 0 }}>{data.report?.summary ?? DASH}</p>
          </Panel>

          <Panel title="Fiyat avantajı hesabı">
            {s.discount_pct === null || own === null ? (
              <div className="notice warn">Yeterli emsal bulunamadığı için fiyat avantajı hesaplanmadı (bulunan {s.comparable_count}).</div>
            ) : (
              <div className="stack" style={{ gap: 14 }}>
                <div className="formula">
                  İndirim = (Emsal medyanı <strong>{num(s.reference_value)}</strong> − İlan <strong>{num(own)}</strong>) / {num(s.reference_value)} × 100 = <strong>{pct(s.discount_pct)}</strong> <span>({unit})</span>
                </div>
                <dl className="kv">
                  <dt>Karşılaştırma seviyesi</dt><dd>{s.comparable_level}</dd>
                  <dt>Emsal sayısı</dt><dd>{s.comparable_count}{data.report?.details.comparables.outliers_removed ? ` (${data.report.details.comparables.outliers_removed} uç değer çıkarıldı)` : ""}</dd>
                  <dt>Piyasa medyanı</dt><dd>{money(s.market_median_price, l.currency)}</dd>
                  <dt>Bölgesel ortalama</dt><dd>{money(s.market_avg_price, l.currency)}</dd>
                  <dt>Tahmini fark</dt><dd>{money(s.estimated_gap, l.currency)}</dd>
                  {s.gross_yield_pct !== null && <><dt>Tahmini brüt kira getirisi</dt><dd>{pct(s.gross_yield_pct)} / yıl</dd></>}
                </dl>
                <ComparableHistogram values={compValues} subject={own} median={s.reference_value} unit={unit} />
              </div>
            )}
          </Panel>

          <Panel title={`Emsal ilanlar (${data.comparables.length})`}>
            {data.comparables.length === 0 ? <div className="empty">Emsal ilan yok.</div> : (
              <div className="table-wrap" style={{ margin: -16 }}>
                <table className="table stacking">
                  <thead><tr><th>İlan</th><th className="r">Fiyat</th><th className="r">{unitKind ? "TL/m²" : "Km"}</th><th className="r">Tarih</th></tr></thead>
                  <tbody>
                    <tr className="subject">
                      <td><span className="cell-title">Bu ilan</span><span className="cell-sub">{place(l)}</span></td>
                      <td className="r">{money(l.price, l.currency)}</td><td className="r hide-sm">{unitKind ? num(l.price_per_m2) : num(l.km)}</td><td className="r hide-sm">{dateText(l.listed_at)}</td>
                    </tr>
                    {data.comparables.slice(0, 25).map((c) => (
                      <tr key={c.id}>
                        <td><span className="cell-title">{c.title}</span><span className="cell-sub">{[c.neighbourhood ?? c.district, c.rooms ?? c.year, sizeText(c)].filter(Boolean).join(" · ")}</span></td>
                        <td className="r">{money(c.price, c.currency)}</td><td className="r hide-sm">{unitKind ? num(c.price_per_m2) : num(c.km)}</td><td className="r hide-sm">{dateText(c.listed_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
        </div>

        <div className="stack">
          <Panel title="Risk analizi" aside={<span className={`pill ${riskClass(s.risk_level)}`}>{s.risk_level} · {s.risk_score.toFixed(0)}</span>}>
            {s.warnings.length === 0 ? <p className="muted" style={{ margin: 0 }}>Veride risk işareti bulunmadı. Bu, tapu ve ekspertiz kontrolünün yerini tutmaz.</p> : (
              <ul style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 6 }}>{s.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
            )}
          </Panel>

          <Panel title="Açıklama analizi (NLP)" aside={<span className="small muted num">Aciliyet {s.nlp_score.toFixed(0)}/100</span>}>
            {nlp.signals.length === 0 && nlp.negated.length === 0 && <p className="muted" style={{ margin: 0 }}>Satış motivasyonu ifadesi bulunmadı.</p>}
            {nlp.signals.map((sig) => (
              <div className="signal" key={sig.key + sig.label}>
                <span><span className={`dot ${sig.counted ? "info" : ""}`} /> {sig.label}{!sig.counted && <span className="small muted"> · hassasiyet ayarı nedeniyle skora katılmadı</span>}</span>
                <q>{sig.evidence}</q>
              </div>
            ))}
            {nlp.negated.map((n, i) => (
              <div className="signal" key={`neg-${i}`}><span><span className="dot" /> Olumsuz ifade: {n.key}</span><q>{n.evidence}</q></div>
            ))}
            {nlp.parity && <p className="small muted">“Piyasa fiyatıyla aynı” ifadesi bulundu; fiyat avantajı kanıtı sayılmadı.</p>}
            {nlp.terms.length > 0 && <p className="small muted" style={{ marginBottom: 0 }}>Ayırt edici terimler (TF-IDF): {nlp.terms.join(", ")}</p>}
          </Panel>

          <Panel title="Bölgesel piyasa" aside={b && <span className="small muted">Son {b.market_days} gün</span>}>
            {!b ? <p className="muted" style={{ margin: 0 }}>Bölge özeti yok.</p> : (
              <div className="stack" style={{ gap: 14 }}>
                <span>{b.segment_label}</span>
                <dl className="kv">
                  <dt>Benzer ilan</dt><dd>{b.sample_size}</dd>
                  <dt>Veri kapsamı</dt><dd>{b.coverage_days} gün</dd>
                  {b.median_unit_price !== null && <><dt>Medyan TL/m²</dt><dd>{num(b.median_unit_price)}</dd><dt>Ortalama TL/m²</dt><dd>{num(b.avg_unit_price)}</dd></>}
                  <dt>Medyan fiyat</dt><dd>{money(b.median_price, l.currency)}</dd>
                  <dt>Ortalama fiyat</dt><dd>{money(b.avg_price, l.currency)}</dd>
                  <dt>En düşük / en yüksek</dt><dd>{money(b.min_price, l.currency)} / {money(b.max_price, l.currency)}</dd>
                  <dt>Dönem içi eğilim</dt><dd>{b.trend_pct === null ? <span className="muted">Yetersiz veri</span> : `${signedPct(b.trend_pct)} (dönemin ilk yarısına göre)`}</dd>
                </dl>
                {b.coverage_days < b.market_days * 0.5 && <div className="notice warn">Bu bölge için yalnızca {b.coverage_days} günlük veri var; {b.market_days} günlük geçmiş henüz oluşmadı.</div>}
                {Object.entries(b.breakdowns).map(([name, rows]) => (
                  <div key={name} className="stack" style={{ gap: 8 }}>
                    <span className="small muted">{name} kırılımı</span>
                    <BreakdownList rows={rows} unit={l.main_category === "emlak" ? `${l.currency}/m²` : l.currency} />
                  </div>
                ))}
              </div>
            )}
          </Panel>

          <Panel title="Fiyat geçmişi"><PriceHistory points={data.price_history} currency={l.currency} /></Panel>

          <Panel title="İlan detayları">
            <dl className="kv">
              {FIELD_LABELS.filter(([key]) => l[key] !== null && l[key] !== undefined && l[key] !== "").map(([key, label, format]) => (
                <span key={key} style={{ display: "contents" }}><dt>{label}</dt><dd>{format(l[key])}</dd></span>
              ))}
              {BOOL_LABELS.filter(([key]) => typeof l[key] === "boolean").map(([key, label]) => (
                <span key={key} style={{ display: "contents" }}><dt>{label}</dt><dd>{l[key] ? "Evet" : "Hayır"}</dd></span>
              ))}
              <dt>Veri kalitesi</dt><dd>%{l.data_quality}</dd>
            </dl>
            {l.description && <p style={{ whiteSpace: "pre-line", marginBottom: 0 }} className="small">{l.description}</p>}
          </Panel>

          <Panel title="Veri kaynağı">
            <dl className="kv">
              <dt>Kaynak</dt><dd>{data.source.name}</dd>
              <dt>Kaynak ilan no</dt><dd className="mono">{l.source_listing_id}</dd>
              <dt>Son görülme</dt><dd>{dateTime(data.source.last_seen_at)}</dd>
              <dt>Son analiz</dt><dd>{dateTime(s.analyzed_at)}</dd>
            </dl>
            <p className="small muted" style={{ marginBottom: 0 }}>{data.disclaimer}</p>
          </Panel>
        </div>
      </div>
    </>
  );
}
