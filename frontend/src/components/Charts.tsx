import { useState } from "react";

const W = 560;
const PAD = { left: 44, right: 12, top: 26, bottom: 26 };
const compact = new Intl.NumberFormat("tr-TR", { notation: "compact", maximumFractionDigits: 1 });
const full = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 0 });

function niceStep(max: number, count = 4): number {
  const raw = max / count;
  const magnitude = 10 ** Math.floor(Math.log10(raw || 1));
  return [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((step) => step >= raw) ?? raw;
}

/** Emsal değerlerinin eşit aralıklı histogramı; ilanın kendi değeri ve emsal medyanı işaretlenir. */
export function ComparableHistogram({ values, subject, median, unit }: { values: number[]; subject: number; median: number | null; unit: string }) {
  const [tip, setTip] = useState("Bir çubuğun üzerine gelin.");
  if (values.length === 0) return <p className="muted small">Emsal yok; dağılım çizilemedi.</p>;
  const height = 200;
  const lo = Math.min(...values, subject);
  const hi = Math.max(...values, subject);
  const bins = 8;
  const width = (hi - lo) / bins || 1;
  const counts = Array.from({ length: bins }, () => 0);
  values.forEach((v) => counts[Math.min(bins - 1, Math.floor((v - lo) / width))]++);
  const step = Math.max(1, Math.ceil(niceStep(Math.max(...counts), 3)));
  const top = Math.ceil((Math.max(...counts) + 0.5) / step) * step;
  const plotW = W - PAD.left - PAD.right;
  const plotH = height - PAD.top - PAD.bottom;
  const x = (v: number) => PAD.left + ((v - lo) / (hi - lo || 1)) * plotW;
  const y = (c: number) => PAD.top + plotH - (c / top) * plotH;
  const barW = plotW / bins;

  return (
    <div>
      <div className="chart-tip" aria-live="polite">{tip}</div>
      <svg className="chart" viewBox={`0 0 ${W} ${height}`} role="img" aria-label={`Emsal dağılımı, ${values.length} ilan`}>
        {Array.from({ length: top / step + 1 }, (_, i) => i * step).map((tick) => (
          <g key={tick}>
            <line className={tick === 0 ? "base" : "grid"} x1={PAD.left} x2={W - PAD.right} y1={y(tick)} y2={y(tick)} />
            <text x={PAD.left - 8} y={y(tick) + 4} textAnchor="end">{tick}</text>
          </g>
        ))}
        {counts.map((count, i) => (
          <rect key={i} x={PAD.left + i * barW + 1} width={barW - 2} y={y(count)} height={Math.max(0, y(0) - y(count))} rx={2}
            fill="var(--accent)" opacity={count ? 0.9 : 0}
            onMouseEnter={() => setTip(`${full.format(lo + i * width)} – ${full.format(lo + (i + 1) * width)} ${unit}: ${count} ilan`)}>
            <title>{`${count} ilan`}</title>
          </rect>
        ))}
        {median !== null && (
          <g>
            <line x1={x(median)} x2={x(median)} y1={PAD.top - 4} y2={y(0)} stroke="var(--muted)" strokeDasharray="3 3" />
            <text x={x(median)} y={PAD.top - 10} textAnchor={x(median) > W - 90 ? "end" : "middle"}>Medyan</text>
          </g>
        )}
        <line x1={x(subject)} x2={x(subject)} y1={PAD.top - 4} y2={y(0)} stroke="var(--ink)" strokeWidth={1.5} />
        <text x={x(subject) + 4} y={PAD.top + 8} style={{ fill: "var(--ink)" }} textAnchor={x(subject) > W - 90 ? "end" : "start"}>Bu ilan</text>
        {[lo, lo + (hi - lo) / 2, hi].map((v, i) => (
          <text key={i} x={x(v)} y={height - 6} textAnchor={i === 0 ? "start" : i === 2 ? "end" : "middle"}>{compact.format(v)}</text>
        ))}
      </svg>
    </div>
  );
}

/** Kayıtlı fiyat geçmişi; değişim yoksa grafik yerine tek cümle gösterilir. */
export function PriceHistory({ points, currency }: { points: { price: number; observed_at: string }[]; currency: string }) {
  if (points.length < 2) {
    return <p className="muted small" style={{ margin: 0 }}>Tek fiyat kaydı var ({full.format(points[0]?.price ?? 0)} {currency}); fiyat değişikliği görülmedi.</p>;
  }
  const height = 160;
  const prices = points.map((p) => p.price);
  const step = niceStep(Math.max(...prices) - Math.min(...prices) || Math.max(...prices) * 0.1, 3);
  const lo = Math.floor(Math.min(...prices) / step) * step - step;
  const hi = Math.ceil(Math.max(...prices) / step) * step + step;
  const plotW = W - PAD.left - PAD.right;
  const plotH = height - PAD.top - PAD.bottom;
  const x = (i: number) => PAD.left + (i / (points.length - 1)) * plotW;
  const y = (v: number) => PAD.top + plotH - ((v - lo) / (hi - lo)) * plotH;
  const path = points.map((p, i) => `${i ? "H" : "M"}${x(i)} ${i ? "" : y(p.price)}${i ? `V${y(p.price)}` : ""}`).join(" ");
  const ticks = Array.from({ length: Math.round((hi - lo) / step) + 1 }, (_, i) => lo + i * step);
  return (
    <svg className="chart" viewBox={`0 0 ${W} ${height}`} role="img" aria-label="Fiyat geçmişi">
      {ticks.map((t) => (
        <g key={t}>
          <line className="grid" x1={PAD.left} x2={W - PAD.right} y1={y(t)} y2={y(t)} />
          <text x={PAD.left - 8} y={y(t) + 4} textAnchor="end">{compact.format(t)}</text>
        </g>
      ))}
      <path d={path} fill="none" stroke="var(--accent)" strokeWidth={2} />
      {points.map((p, i) => (
        <g key={i}>
          <circle cx={x(i)} cy={y(p.price)} r={4} fill="var(--accent)"><title>{`${new Date(p.observed_at).toLocaleDateString("tr-TR")}: ${full.format(p.price)} ${currency}`}</title></circle>
          <text x={x(i)} y={height - 6} textAnchor={i === 0 ? "start" : i === points.length - 1 ? "end" : "middle"}>
            {new Date(p.observed_at).toLocaleDateString("tr-TR", { day: "numeric", month: "short" })}
          </text>
        </g>
      ))}
    </svg>
  );
}

/** Kırılım listesi: etiket, ince gri oran çubuğu ve sağa hizalı medyan. */
export function BreakdownList({ rows, unit }: { rows: { label: string; count: number; median: number }[]; unit: string }) {
  if (!rows.length) return <p className="muted small" style={{ margin: 0 }}>Bu kırılım için yeterli veri yok.</p>;
  const max = Math.max(...rows.map((r) => r.median));
  return (
    <div style={{ display: "grid", gap: 10 }}>
      {rows.map((row) => (
        <div key={row.label} style={{ display: "grid", gap: 4 }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 12, fontSize: 13 }}>
            <span>{row.label} <span className="muted">· {row.count} ilan</span></span>
            <span className="num">{full.format(row.median)} {unit}</span>
          </div>
          <div style={{ height: 3, borderRadius: 2, background: "rgb(255 255 255 / 0.08)" }}>
            <div style={{ height: "100%", width: `${(row.median / max) * 88}%`, borderRadius: 2, background: "var(--muted)" }} />
          </div>
        </div>
      ))}
    </div>
  );
}
