import type { Filters, Listing } from "./types";

const integer = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 0 });
const oneDecimal = new Intl.NumberFormat("tr-TR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

export const DASH = "—";

export function money(value: number | null | undefined, currency = "TL"): string {
  if (value === null || value === undefined) return DASH;
  return `${integer.format(Math.round(value))} ${currency}`;
}

export const num = (value: number | null | undefined) => (value === null || value === undefined ? DASH : integer.format(value));
export const pct = (value: number | null | undefined) => (value === null || value === undefined ? DASH : `%${oneDecimal.format(value)}`);
export const signedPct = (value: number | null | undefined) =>
  value === null || value === undefined ? DASH : `${value > 0 ? "+" : value < 0 ? "−" : ""}%${oneDecimal.format(Math.abs(value))}`;

export function dateText(value: string | null | undefined): string {
  if (!value) return DASH;
  return new Date(value.length === 10 ? `${value}T00:00:00` : value).toLocaleDateString("tr-TR", { day: "numeric", month: "short", year: "numeric" });
}

export function dateTime(value: string | null | undefined): string {
  if (!value) return DASH;
  return new Date(value).toLocaleString("tr-TR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function ageText(value: string | null): string {
  if (!value) return "Tarih yok";
  const days = Math.round((Date.now() - new Date(`${value}T00:00:00`).getTime()) / 86_400_000);
  if (days <= 0) return "Bugün";
  if (days === 1) return "Dün";
  return `${days} gün önce`;
}

export const CATEGORY_LABELS: Record<string, string> = {
  "satilik-konut": "Satılık Konut", "kiralik-konut": "Kiralık Konut", "satilik-isyeri": "Satılık İş Yeri",
  "kiralik-isyeri": "Kiralık İş Yeri", "satilik-arsa": "Satılık Arsa", "diger-emlak": "Diğer Emlak",
  otomobil: "Otomobil", "arazi-suv-pickup": "Arazi, SUV ve Pickup", motosiklet: "Motosiklet",
  "ticari-arac": "Ticari Araç", "diger-vasita": "Diğer Vasıta",
};

export const place = (l: Listing) => [l.city, l.district, l.neighbourhood].filter(Boolean).join(" / ") || DASH;

export function sizeText(l: Listing): string {
  if (l.main_category === "vasita") return l.km !== null ? `${num(l.km)} km` : DASH;
  return l.m2_gross ? `${num(l.m2_gross)} m²` : DASH;
}

export function headline(l: Listing): string {
  if (l.main_category === "vasita") return [l.brand, l.series, l.year].filter(Boolean).join(" ");
  return [CATEGORY_LABELS[l.category], l.rooms, l.property_type].filter(Boolean).join(" · ");
}

// Kullanıcının girdiği veriden gelen bağlantılar yalnızca http(s) ise tıklanabilir.
export const safeUrl = (url: string | null | undefined) => (url && /^https?:\/\//i.test(url) ? url : null);

export const SOURCE_LABELS: Record<string, string> = {
  sahibinden: "Sahibinden (web)", authorized: "Yetkili sağlayıcı", manual_import: "Dosya içe aktarma", demo: "DEMO",
};

export const STATUS_LABELS: Record<string, string> = {
  queued: "Sırada", running: "Çalışıyor", pausing: "Duraklatılıyor", paused: "Duraklatıldı", stopping: "Durduruluyor",
  stopped: "Durduruldu", completed: "Tamamlandı", failed: "Hata", interrupted: "Kesildi",
  ok: "Bağlı", not_configured: "Yapılandırılmadı", error: "Hata", access_denied: "Erişim reddedildi",
};

export const EMPTY_FILTERS: Filters = {
  data_mode: "real", main_category: "emlak", categories: [], country: "Türkiye", cities: [], districts: [], neighbourhoods: [],
  currency: "TL", price_min: null, price_max: null, unit_price_min: null, unit_price_max: null, below_regional_avg: false,
  below_regional_median: false, m2_basis: "brut", m2_min: null, m2_max: null, rooms: [], living_rooms: [],
  building_age_min: null, building_age_max: null, floors: [], total_floors_min: null, total_floors_max: null, heating: [],
  bathrooms: [], balcony: null, elevator: null, parking: null, in_site: null, deed_status: [], credit_eligible: null,
  furnished: null, brands: [], series: [], year_min: null, year_max: null, km_min: null, km_max: null, fuels: [],
  transmissions: [], engine_cc_min: null, engine_cc_max: null, engine_hp_min: null, engine_hp_max: null, body_types: [],
  drive_types: [], colors: [], damage_record: null, paint_status: [], changed_parts_max: null, heavy_damage: null,
  seller_types: [], market_window_days: 30, market_from: null, market_to: null, opportunity_window_days: 14,
  opportunity_from: null, opportunity_to: null, urgent: false, need_sale: false, below_market: false, price_dropped: false,
  negotiable: false, bargain: false, swap: false, high_investment: false, cheapest_in_region: false,
  only_opportunities: false, min_score: null, min_advantage: null, min_confidence: null,
};
