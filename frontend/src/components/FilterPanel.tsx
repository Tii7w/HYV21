import { useEffect, useState } from "react";
import { api, del, post } from "../api";
import { useApp } from "../context";
import { EMPTY_FILTERS } from "../format";
import { OPPORTUNITY_FLAGS } from "../filterSummary";
import type { CatalogOptions, Filters, Profile } from "../types";
import { ChipGroup, DateWindow, MultiSelect, NumberRange, TriState } from "./Fields";

type Props = {
  filters: Filters;
  onChange: (filters: Filters) => void;
  onApply: () => void;
  onRunProfile: (profile: Profile) => void;
  open: boolean;
  onClose: () => void;
};

const opt = (catalog: CatalogOptions | null, key: string) => (catalog?.[key] as string[] | undefined) ?? [];

function Group({ title, children, open = false }: { title: string; children: React.ReactNode; open?: boolean }) {
  return (
    <details className="fgroup" open={open}>
      <summary>{title}</summary>
      <div className="fgroup-body">{children}</div>
    </details>
  );
}

export default function FilterPanel({ filters: f, onChange, onApply, onRunProfile, open, onClose }: Props) {
  const { isAdmin } = useApp();
  const [catalog, setCatalog] = useState<CatalogOptions | null>(null);
  const [cities, setCities] = useState<string[]>([]);
  const [districts, setDistricts] = useState<string[]>([]);
  const [hoods, setHoods] = useState<string[]>([]);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [profileName, setProfileName] = useState("");
  const [profileError, setProfileError] = useState<string | null>(null);
  const set = (patch: Partial<Filters>) => onChange({ ...f, ...patch });

  useEffect(() => {
    api<CatalogOptions>("/api/catalog/options").then(setCatalog).catch(() => undefined);
    api<string[]>("/api/catalog/cities").then(setCities).catch(() => undefined);
    api<Profile[]>("/api/profiles").then(setProfiles).catch(() => undefined);
  }, []);

  // İl → ilçe → mahalle zinciri: üst seviye boşalınca alt seçimler de temizlenir.
  useEffect(() => {
    if (!f.cities.length) {
      setDistricts([]);
      return;
    }
    const query = f.cities.map((c) => `city=${encodeURIComponent(c)}`).join("&");
    api<Record<string, string[]>>(`/api/catalog/districts?${query}`)
      .then((byCity) => setDistricts(Object.values(byCity).flat()))
      .catch(() => setDistricts([]));
  }, [f.cities]);

  useEffect(() => {
    if (!f.districts.length) {
      setHoods([]);
      return;
    }
    Promise.all(
      f.cities.map((city) =>
        api<Record<string, string[]>>(`/api/catalog/neighbourhoods?city=${encodeURIComponent(city)}&${f.districts.map((d) => `district=${encodeURIComponent(d)}`).join("&")}`),
      ),
    )
      .then((results) => setHoods([...new Set(results.flatMap((r) => Object.values(r).flat()))]))
      .catch(() => setHoods([]));
  }, [f.cities, f.districts]);

  async function saveProfile() {
    setProfileError(null);
    try {
      const profile = await post<Profile>("/api/profiles", { name: profileName, filters: f });
      setProfiles((list) => [...list, profile].sort((a, b) => a.name.localeCompare(b.name, "tr")));
      setProfileName("");
    } catch (exc) {
      setProfileError((exc as Error).message);
    }
  }

  const categories = f.main_category ? catalog?.categories[f.main_category] ?? [] : [];
  const isEmlak = f.main_category !== "vasita";
  const isVasita = f.main_category === "vasita";

  return (
    <aside className={`panel filters${open ? " open" : ""}`} aria-label="Gelişmiş filtreler">
      <div className="panel-head">
        <h2>Filtreler</h2>
        <div style={{ display: "flex", gap: 6 }}>
          <button className="btn ghost sm" onClick={() => onChange({ ...EMPTY_FILTERS, data_mode: f.data_mode })}>Sıfırla</button>
          <button className="btn sm sheet-close" onClick={onClose}>Kapat</button>
        </div>
      </div>
      <div className="filters-scroll">
        <Group title="Kategori" open>
          <div className="seg" role="group" aria-label="Ana kategori">
            {(["emlak", "vasita"] as const).map((main) => (
              <button type="button" key={main} aria-pressed={f.main_category === main}
                onClick={() => set({ main_category: main, categories: [], rooms: [], brands: [], series: [] })}>
                {main === "emlak" ? "Emlak" : "Vasıta"}
              </button>
            ))}
          </div>
          <ChipGroup label="Alt kategori" options={categories.map((c) => c.value)} value={f.categories}
            format={(v) => categories.find((c) => c.value === v)?.label ?? v} onChange={(categories) => set({ categories })} />
        </Group>

        <Group title="Konum" open>
          <label className="field"><span>Ülke</span>
            <select className="input" value={f.country} onChange={(e) => set({ country: e.target.value })}>
              {(opt(catalog, "countries").length ? opt(catalog, "countries") : ["Türkiye"]).map((c) => <option key={c}>{c}</option>)}
            </select>
          </label>
          <MultiSelect label="İl" options={cities} value={f.cities} onChange={(v) => set({ cities: v, districts: v.length ? f.districts : [], neighbourhoods: v.length ? f.neighbourhoods : [] })} />
          <MultiSelect label="İlçe" options={districts} value={f.districts} disabledHint={f.cities.length ? undefined : "Önce il seçin."}
            onChange={(v) => set({ districts: v, neighbourhoods: v.length ? f.neighbourhoods : [] })} />
          <MultiSelect label="Mahalle" options={hoods} value={f.neighbourhoods} allowCustom disabledHint={f.districts.length ? undefined : "Önce ilçe seçin."}
            onChange={(v) => set({ neighbourhoods: v })} />
        </Group>

        <Group title="Fiyat" open>
          <NumberRange label="Fiyat" unit="TL" min={f.price_min} max={f.price_max} onChange={(price_min, price_max) => set({ price_min, price_max })} />
          {isEmlak && <NumberRange label="Birim fiyat" unit="TL/m²" min={f.unit_price_min} max={f.unit_price_max} onChange={(unit_price_min, unit_price_max) => set({ unit_price_min, unit_price_max })} />}
        </Group>

        <Group title="İlan tarihi ve piyasa aralığı" open>
          <DateWindow label="Fırsat aranacak ilanlar" hint="Bu aralıkta yayınlanan ilanlar listelenir ve puanlanır." allowAll
            days={f.opportunity_window_days} from={f.opportunity_from} to={f.opportunity_to}
            onChange={(opportunity_window_days, opportunity_from, opportunity_to) => set({ opportunity_window_days, opportunity_from, opportunity_to })} />
          <DateWindow label="Piyasa analizi geçmişi" hint="Emsal ve bölge ortalaması bu aralıktaki ilanlardan hesaplanır."
            days={f.market_window_days} from={f.market_from} to={f.market_to}
            onChange={(days, market_from, market_to) => set({ market_window_days: days ?? 30, market_from, market_to })} />
        </Group>

        {isEmlak && (
          <Group title="Emlak özellikleri">
            <div className="seg" role="group" aria-label="m² türü">
              {(["brut", "net"] as const).map((basis) => (
                <button type="button" key={basis} aria-pressed={f.m2_basis === basis} onClick={() => set({ m2_basis: basis })}>{basis === "brut" ? "Brüt m²" : "Net m²"}</button>
              ))}
            </div>
            <NumberRange label="Metrekare" unit="m²" min={f.m2_min} max={f.m2_max} onChange={(m2_min, m2_max) => set({ m2_min, m2_max })} />
            <ChipGroup label="Oda sayısı" options={opt(catalog, "rooms")} value={f.rooms} onChange={(rooms) => set({ rooms })} />
            <ChipGroup label="Salon sayısı" options={[0, 1, 2, 3]} value={f.living_rooms} onChange={(living_rooms) => set({ living_rooms })} />
            <ChipGroup label="Banyo sayısı" options={[1, 2, 3, 4]} value={f.bathrooms} onChange={(bathrooms) => set({ bathrooms })} />
            <NumberRange label="Bina yaşı" min={f.building_age_min} max={f.building_age_max} onChange={(building_age_min, building_age_max) => set({ building_age_min, building_age_max })} />
            <MultiSelect label="Bulunduğu kat" options={opt(catalog, "floors")} value={f.floors} allowCustom onChange={(floors) => set({ floors })} />
            <NumberRange label="Toplam kat sayısı" min={f.total_floors_min} max={f.total_floors_max} onChange={(total_floors_min, total_floors_max) => set({ total_floors_min, total_floors_max })} />
            <MultiSelect label="Isıtma türü" options={opt(catalog, "heating")} value={f.heating} onChange={(heating) => set({ heating })} />
            <MultiSelect label="Tapu durumu" options={opt(catalog, "deed_status")} value={f.deed_status} onChange={(deed_status) => set({ deed_status })} />
            <div className="range">
              <TriState label="Balkon" value={f.balcony} onChange={(balcony) => set({ balcony })} />
              <TriState label="Asansör" value={f.elevator} onChange={(elevator) => set({ elevator })} />
              <TriState label="Otopark" value={f.parking} onChange={(parking) => set({ parking })} />
              <TriState label="Site içerisinde" value={f.in_site} yes="Evet" no="Hayır" onChange={(in_site) => set({ in_site })} />
              <TriState label="Krediye uygun" value={f.credit_eligible} yes="Evet" no="Hayır" onChange={(credit_eligible) => set({ credit_eligible })} />
              <TriState label="Eşyalı" value={f.furnished} yes="Eşyalı" no="Eşyasız" onChange={(furnished) => set({ furnished })} />
            </div>
          </Group>
        )}

        {isVasita && (
          <Group title="Vasıta özellikleri">
            <MultiSelect label="Marka" options={opt(catalog, "brands")} value={f.brands} allowCustom onChange={(brands) => set({ brands })} />
            <MultiSelect label="Model / seri" options={opt(catalog, "series")} value={f.series} allowCustom onChange={(series) => set({ series })} />
            <NumberRange label="Model yılı" min={f.year_min} max={f.year_max} onChange={(year_min, year_max) => set({ year_min, year_max })} />
            <NumberRange label="Kilometre" unit="km" min={f.km_min} max={f.km_max} onChange={(km_min, km_max) => set({ km_min, km_max })} />
            <ChipGroup label="Yakıt" options={opt(catalog, "fuels")} value={f.fuels} onChange={(fuels) => set({ fuels })} />
            <ChipGroup label="Vites" options={opt(catalog, "transmissions")} value={f.transmissions} onChange={(transmissions) => set({ transmissions })} />
            <NumberRange label="Motor hacmi" unit="cc" min={f.engine_cc_min} max={f.engine_cc_max} onChange={(engine_cc_min, engine_cc_max) => set({ engine_cc_min, engine_cc_max })} />
            <NumberRange label="Motor gücü" unit="hp" min={f.engine_hp_min} max={f.engine_hp_max} onChange={(engine_hp_min, engine_hp_max) => set({ engine_hp_min, engine_hp_max })} />
            <MultiSelect label="Kasa tipi" options={opt(catalog, "body_types")} value={f.body_types} onChange={(body_types) => set({ body_types })} />
            <ChipGroup label="Çekiş" options={opt(catalog, "drive_types")} value={f.drive_types} onChange={(drive_types) => set({ drive_types })} />
            <MultiSelect label="Renk" options={opt(catalog, "colors")} value={f.colors} allowCustom onChange={(colors) => set({ colors })} />
            <ChipGroup label="Boya durumu" options={opt(catalog, "paint_status")} value={f.paint_status} onChange={(paint_status) => set({ paint_status })} />
            <NumberRange label="En fazla değişen parça" min={null} max={f.changed_parts_max} onChange={(_min, changed_parts_max) => set({ changed_parts_max })} />
            <div className="range">
              <TriState label="Hasar kaydı" value={f.damage_record} onChange={(damage_record) => set({ damage_record })} />
              <TriState label="Ağır hasar" value={f.heavy_damage} yes="Ağır hasarlı" no="Hasarsız" onChange={(heavy_damage) => set({ heavy_damage })} />
            </div>
          </Group>
        )}

        <Group title="Satıcı">
          <ChipGroup label="Kimden" options={opt(catalog, "seller_types")} value={f.seller_types} onChange={(seller_types) => set({ seller_types })} />
        </Group>

        <Group title="Fırsat filtreleri">
          {OPPORTUNITY_FLAGS.map(([key, label]) => (
            <label key={key} className="check">
              <input type="checkbox" checked={Boolean(f[key])} onChange={(e) => set({ [key]: e.target.checked } as Partial<Filters>)} /> {label}
            </label>
          ))}
          <div className="range">
            <label className="field"><span>En düşük skor</span>
              <input className="input num" inputMode="numeric" value={f.min_score ?? ""} onChange={(e) => set({ min_score: e.target.value ? Math.min(100, Number(e.target.value.replace(/\D/g, ""))) : null })} />
            </label>
            <label className="field"><span>En düşük avantaj %</span>
              <input className="input num" inputMode="numeric" value={f.min_advantage ?? ""} onChange={(e) => set({ min_advantage: e.target.value ? Number(e.target.value.replace(/[^\d]/g, "")) : null })} />
            </label>
          </div>
          <label className="field"><span>En düşük analiz güveni</span>
            <select className="input" value={f.min_confidence ?? ""} onChange={(e) => set({ min_confidence: (e.target.value || null) as Filters["min_confidence"] })}>
              <option value="">Farketmez</option><option>Düşük</option><option>Orta</option><option>Yüksek</option>
            </select>
          </label>
        </Group>

        <Group title={`Kayıtlı profiller (${profiles.length})`}>
          {profiles.length === 0 && <span className="small">Henüz kayıtlı profil yok.</span>}
          {profiles.map((profile) => (
            <div key={profile.id} style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <button type="button" className="btn ghost sm" style={{ flex: 1, justifyContent: "flex-start", color: "var(--ink)", overflow: "hidden" }}
                onClick={() => onChange({ ...EMPTY_FILTERS, ...profile.filters })} title="Filtreleri yükle">
                {profile.name}
              </button>
              {isAdmin && <button type="button" className="btn sm" onClick={() => onRunProfile(profile)}>Çalıştır</button>}
              <button type="button" className="btn ghost sm" aria-label={`${profile.name} profilini sil`}
                onClick={() => del(`/api/profiles/${profile.id}`).then(() => setProfiles((l) => l.filter((p) => p.id !== profile.id)))}>Sil</button>
            </div>
          ))}
          <div style={{ display: "flex", gap: 6 }}>
            <input className="input" placeholder="Örn. Bursa Nilüfer Satılık Daire" aria-label="Profil adı" value={profileName} onChange={(e) => setProfileName(e.target.value)} />
            <button type="button" className="btn sm" disabled={profileName.trim().length < 2} onClick={saveProfile}>Kaydet</button>
          </div>
          {profileError && <span className="small" style={{ color: "var(--negative)" }}>{profileError}</span>}
        </Group>
      </div>
      <div className="filters-foot">
        <button className="btn primary" onClick={() => { onApply(); onClose(); }}>Sonuçları göster</button>
      </div>
    </aside>
  );
}
