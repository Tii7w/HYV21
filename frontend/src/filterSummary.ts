import { CATEGORY_LABELS, EMPTY_FILTERS, num } from "./format";
import type { Filters } from "./types";

/** Fırsat kutuları: filtre paneli ve tarama özeti aynı listeyi kullanır (backend SIGNAL_FLAGS ile aynı). */
export const OPPORTUNITY_FLAGS: [keyof Filters, string][] = [
  ["urgent", "Acil satılık"], ["need_sale", "İhtiyaçtan / nakit ihtiyacı"], ["below_market", "Piyasa altı (satıcı beyanı)"],
  ["price_dropped", "Fiyatı düşen"], ["negotiable", "Pazarlığa açık"], ["bargain", "Kelepir"], ["swap", "Takaslı"],
  ["high_investment", "Yüksek yatırım potansiyeli"], ["cheapest_in_region", "Bölgenin en ucuz %25'i"],
  ["below_regional_avg", "Bölge ortalamasının altında"], ["below_regional_median", "Bölge medyanının altında"],
  ["only_opportunities", "Yalnızca fırsat sayılan ilanlar"],
];

const range = (min: number | null, max: number | null, unit = "") => {
  if (min === null && max === null) return null;
  const u = unit ? ` ${unit}` : "";
  if (min !== null && max !== null) return `${num(min)} – ${num(max)}${u}`;
  return min !== null ? `en az ${num(min)}${u}` : `en çok ${num(max)}${u}`;
};

const windowText = (days: number | null, from: string | null, to: string | null) =>
  from || to ? `${from ?? "…"} → ${to ?? "bugün"}` : days === null ? "tüm tarihler" : days === 1 ? "son 24 saat" : `son ${days} gün`;

/** Özette ayrıca gösterilen alanlar; geri kalan dolu alanlar "+N diğer filtre" olarak sayılır. */
const SUMMARIZED = new Set<keyof Filters>([
  "data_mode", "main_category", "categories", "country", "cities", "districts", "neighbourhoods", "price_min", "price_max",
  "m2_min", "m2_max", "m2_basis", "rooms", "brands", "series", "year_min", "year_max", "km_min", "km_max",
  "opportunity_window_days", "opportunity_from", "opportunity_to", "market_window_days", "market_from", "market_to",
  "min_score", "min_advantage", "min_confidence", "currency", ...OPPORTUNITY_FLAGS.map(([k]) => k),
]);

/** Taramanın hangi filtrelerle çalışacağını okunur satırlar olarak döndürür. */
export function filterSummary(f: Filters): [string, string][] {
  const rows: [string, string][] = [];
  const add = (label: string, value: string | null | undefined) => value && rows.push([label, value]);

  add("Veri", f.data_mode === "demo" ? "DEMO (sentetik test verisi)" : "Gerçek veri");
  const main = f.main_category === "vasita" ? "Vasıta" : "Emlak";
  add("Kategori", f.categories.length ? `${main} · ${f.categories.map((c) => CATEGORY_LABELS[c] ?? c).join(", ")}` : `${main} · tüm alt kategoriler`);
  add("Konum", [f.cities.join(", ") || "Tüm iller", f.districts.join(", "), f.neighbourhoods.join(", ")].filter(Boolean).join(" / "));
  add("Fiyat", range(f.price_min, f.price_max, "TL"));
  if (f.main_category === "vasita") {
    add("Marka / seri", [...f.brands, ...f.series].join(", ") || null);
    add("Model yılı", range(f.year_min, f.year_max));
    add("Kilometre", range(f.km_min, f.km_max, "km"));
  } else {
    add(f.m2_basis === "net" ? "Net m²" : "Brüt m²", range(f.m2_min, f.m2_max, "m²"));
    add("Oda", f.rooms.join(", ") || null);
  }
  add("Fırsat aranacak ilanlar", windowText(f.opportunity_window_days, f.opportunity_from, f.opportunity_to));
  add("Piyasa analizi", windowText(f.market_window_days, f.market_from, f.market_to));
  add("Fırsat koşulları", OPPORTUNITY_FLAGS.filter(([k]) => f[k]).map(([, label]) => label).join(", ") || null);
  add("Eşikler", [
    f.min_score !== null ? `skor ≥ ${f.min_score}` : "",
    f.min_advantage !== null ? `avantaj ≥ %${f.min_advantage}` : "",
    f.min_confidence ? `güven ≥ ${f.min_confidence}` : "",
  ].filter(Boolean).join(", ") || null);

  const others = (Object.keys(EMPTY_FILTERS) as (keyof Filters)[]).filter(
    (k) => !SUMMARIZED.has(k) && JSON.stringify(f[k]) !== JSON.stringify(EMPTY_FILTERS[k]),
  ).length;
  if (others) rows.push(["Diğer", `+${others} filtre daha (özellikler, satıcı vb.)`]);
  return rows;
}
