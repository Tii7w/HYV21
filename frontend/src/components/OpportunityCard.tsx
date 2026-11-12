import { Link } from "react-router-dom";
import { ageText, CATEGORY_LABELS, dateText, headline, money, pct, place, safeUrl, sizeText } from "../format";
import type { Listing, Score } from "../types";

export const riskClass = (level: string) => (level === "Yüksek" ? "bad" : level === "Orta" ? "warn" : "good");
export const confidenceClass = (label: string) => (label === "Yüksek" ? "good" : label === "Orta" ? "info" : "warn");

export function ScoreLabel({ score }: { score: Score }) {
  const tone = score.score >= 80 ? "good" : score.score >= 65 ? "info" : "";
  return <span className={`pill ${tone}`}>{score.classification}</span>;
}

export default function OpportunityCard({ listing, score }: { listing: Listing; score: Score }) {
  const photo = safeUrl(listing.photo_url);
  const link = safeUrl(listing.url);
  return (
    <article className="opp">
      <div className={`opp-media${photo ? "" : " no-photo"}`}>
        {photo ? <img src={photo} alt={listing.title} loading="lazy" referrerPolicy="no-referrer" /> : <span>{listing.property_type ?? CATEGORY_LABELS[listing.category]} · fotoğraf yok</span>}
        {listing.is_demo && <span className="demo-tag">DEMO</span>}
      </div>
      <div className="opp-body">
        <div className="opp-score">
          <span className="score-big num">{score.score.toFixed(0)}<small>/100</small></span>
          <ScoreLabel score={score} />
        </div>
        <div>
          <h3>{listing.title || headline(listing)}</h3>
          <span className="small muted">{CATEGORY_LABELS[listing.category]} · {place(listing)}</span>
        </div>
        <dl className="kv">
          <dt>Satış fiyatı</dt><dd><strong>{money(listing.price, listing.currency)}</strong></dd>
          <dt>{listing.main_category === "vasita" ? "Kilometre" : "Brüt alan"}</dt><dd>{sizeText(listing)}</dd>
          <dt>Piyasa medyanı</dt><dd>{money(score.market_median_price, listing.currency)}</dd>
          <dt>Bölgesel ortalama</dt><dd>{money(score.market_avg_price, listing.currency)}</dd>
          <dt>Fiyat avantajı</dt><dd style={{ color: "var(--positive)" }}>{pct(score.discount_pct)}</dd>
          <dt>İlan tarihi</dt><dd title={dateText(listing.listed_at)}>{ageText(listing.listed_at)}</dd>
          <dt>Analiz güveni</dt><dd><span className={`pill ${confidenceClass(score.confidence_label)}`}>{score.confidence_label} · {score.comparable_count} emsal</span></dd>
          <dt>Risk</dt><dd><span className={`pill ${riskClass(score.risk_level)}`}>{score.risk_level}</span></dd>
        </dl>
        {score.summary && (
          <p className="why"><span className="why-label">Neden bu fırsatı kaçırmamalıyım?</span>{score.summary}</p>
        )}
        <div className="opp-foot">
          <Link className="btn primary sm" to={`/firsat/${score.id}`}>Analizi incele</Link>
          {link ? (
            <a className="btn ghost sm" href={link} target="_blank" rel="noopener noreferrer">Orijinal ilan ↗</a>
          ) : (
            <span className="small muted">{listing.is_demo ? "Demo ilan, bağlantı yok" : "Bağlantı yok"}</span>
          )}
        </div>
      </div>
    </article>
  );
}
