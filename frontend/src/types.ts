export type User = { id: number; email: string; role: "admin" | "viewer" };

export type Filters = {
  data_mode: "real" | "demo";
  main_category: "emlak" | "vasita" | null;
  categories: string[];
  country: string;
  cities: string[];
  districts: string[];
  neighbourhoods: string[];
  currency: string;
  price_min: number | null;
  price_max: number | null;
  unit_price_min: number | null;
  unit_price_max: number | null;
  below_regional_avg: boolean;
  below_regional_median: boolean;
  m2_basis: "brut" | "net";
  m2_min: number | null;
  m2_max: number | null;
  rooms: string[];
  living_rooms: number[];
  building_age_min: number | null;
  building_age_max: number | null;
  floors: string[];
  total_floors_min: number | null;
  total_floors_max: number | null;
  heating: string[];
  bathrooms: number[];
  balcony: boolean | null;
  elevator: boolean | null;
  parking: boolean | null;
  in_site: boolean | null;
  deed_status: string[];
  credit_eligible: boolean | null;
  furnished: boolean | null;
  brands: string[];
  series: string[];
  year_min: number | null;
  year_max: number | null;
  km_min: number | null;
  km_max: number | null;
  fuels: string[];
  transmissions: string[];
  engine_cc_min: number | null;
  engine_cc_max: number | null;
  engine_hp_min: number | null;
  engine_hp_max: number | null;
  body_types: string[];
  drive_types: string[];
  colors: string[];
  damage_record: boolean | null;
  paint_status: string[];
  changed_parts_max: number | null;
  heavy_damage: boolean | null;
  seller_types: string[];
  market_window_days: number;
  market_from: string | null;
  market_to: string | null;
  opportunity_window_days: number | null;
  opportunity_from: string | null;
  opportunity_to: string | null;
  urgent: boolean;
  need_sale: boolean;
  below_market: boolean;
  price_dropped: boolean;
  negotiable: boolean;
  bargain: boolean;
  swap: boolean;
  high_investment: boolean;
  cheapest_in_region: boolean;
  only_opportunities: boolean;
  min_score: number | null;
  min_advantage: number | null;
  min_confidence: "Düşük" | "Orta" | "Yüksek" | null;
};

export type Listing = {
  id: number;
  source_key: string;
  source_listing_id: string;
  is_demo: boolean;
  status: string;
  main_category: "emlak" | "vasita";
  category: string;
  property_type: string | null;
  title: string;
  url: string | null;
  photo_url: string | null;
  country: string;
  city: string | null;
  district: string | null;
  neighbourhood: string | null;
  price: number;
  currency: string;
  price_per_m2: number | null;
  price_drop_pct: number | null;
  m2_gross: number | null;
  m2_net: number | null;
  rooms: string | null;
  brand: string | null;
  series: string | null;
  model: string | null;
  year: number | null;
  km: number | null;
  listed_at: string | null;
  last_seen_at: string;
  data_quality: number;
  description?: string;
  [key: string]: unknown;
};

export type Signal = { key: string; label: string; evidence: string; weight: number; counted: boolean };

export type Score = {
  id: number;
  job_id: string;
  is_opportunity: boolean;
  is_suspicious: boolean;
  rank: number | null;
  score: number;
  classification: string;
  price_advantage_score: number;
  nlp_score: number;
  freshness_score: number;
  discount_pct: number | null;
  reference_kind: "unit" | "price" | null;
  reference_value: number | null;
  market_median_price: number | null;
  market_avg_price: number | null;
  estimated_gap: number | null;
  comparable_count: number;
  comparable_level: string | null;
  gross_yield_pct: number | null;
  confidence: number;
  confidence_label: string;
  risk_score: number;
  risk_level: string;
  reliability: number;
  warnings: string[];
  signals: Signal[];
  ineligible_reason: string | null;
  analyzed_at: string;
  summary?: string;
};

export type Item = { listing: Listing; score: Score | null };

/** "Bulunan fırsatlar" sekmesindeki kalıcı kayıt. */
export type FoundItem = {
  listing: Listing;
  score: Score;
  first_found_at: string;
  last_found_at: string;
  times_found: number;
  still_opportunity: boolean;
};

/** SSE "opportunity.found" olayının verisi. */
export type FoundEvent = { job_id: string; score_id: number; listing_id: number; score: number; is_demo: boolean };

export type Job = {
  id: string;
  profile_name: string;
  source_keys: string[];
  status: string;
  stage: string;
  examined: number;
  processed: number;
  opportunities: number;
  failed_requests: number;
  progress: number;
  last_action: string;
  error: string | null;
  filters: Filters;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  queue?: Record<string, number>;
  dead_letters?: number;
};

export type LogLine = { id?: number; at: string; level: string; message: string };

export type Source = {
  key: string;
  name: string;
  kind: string;
  enabled: boolean;
  status: string;
  status_message: string;
  last_checked_at: string | null;
  config: Record<string, string | boolean | null>;
  api_key_set: boolean;
  /** Kaynak şu an tarama başlatabilir mi (yalnızca /api/sources listesinde gelir). */
  ready?: boolean;
  ready_message?: string;
};

export type Profile = { id: number; name: string; filters: Filters; created_at: string; last_run_at: string | null };

export type Note = {
  id: number;
  listing_id: number | null;
  score_id: number | null;
  title: string;
  body: string;
  score: number | null;
  advantage_pct: number | null;
  is_demo: boolean;
  read: boolean;
  created_at: string;
  popup?: boolean;
  browser?: boolean;
};

export type CatalogOptions = {
  categories: Record<"emlak" | "vasita", { value: string; label: string }[]>;
  has_demo: boolean;
  [key: string]: unknown;
};

export type AppSettings = {
  scan: { request_interval_ms: number; max_concurrent: number; timeout_seconds: number; max_retries: number; per_minute: number; per_hour: number };
  proxy: { enabled: boolean; scheme: "http" | "https"; host: string; port: number | null; username: string; authorized_use: boolean };
  agent: { min_score: number; min_advantage: number; min_comparables: number; nlp_sensitivity: string; analysis_depth: string; min_opportunities: number };
  notifications: { popup: boolean; browser: boolean; min_score: number; dedupe: boolean; dedupe_hours: number };
  proxy_password_set?: boolean;
};
