import { useId, useMemo, useState } from "react";

const toNumber = (value: string): number | null => {
  const digits = value.replace(/[^\d]/g, "");
  return digits ? Number(digits) : null;
};
const display = (value: number | null) => (value === null ? "" : new Intl.NumberFormat("tr-TR").format(value));

export function NumberRange(props: {
  label: string; min: number | null; max: number | null; onChange: (min: number | null, max: number | null) => void; unit?: string;
}) {
  return (
    <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }}>
      <legend style={{ padding: 0, marginBottom: 4 }}>{props.label}{props.unit ? ` (${props.unit})` : ""}</legend>
      <div className="range">
        <input className="input num" inputMode="numeric" aria-label={`${props.label} en az`} placeholder="En az"
          value={display(props.min)} onChange={(e) => props.onChange(toNumber(e.target.value), props.max)} />
        <input className="input num" inputMode="numeric" aria-label={`${props.label} en çok`} placeholder="En çok"
          value={display(props.max)} onChange={(e) => props.onChange(props.min, toNumber(e.target.value))} />
      </div>
    </fieldset>
  );
}

export function TriState(props: { label: string; value: boolean | null; onChange: (value: boolean | null) => void; yes?: string; no?: string }) {
  const id = useId();
  return (
    <label className="field" htmlFor={id}>
      <span>{props.label}</span>
      <select id={id} className="input" value={props.value === null ? "" : String(props.value)}
        onChange={(e) => props.onChange(e.target.value === "" ? null : e.target.value === "true")}>
        <option value="">Farketmez</option>
        <option value="true">{props.yes ?? "Var"}</option>
        <option value="false">{props.no ?? "Yok"}</option>
      </select>
    </label>
  );
}

export function ChipGroup<T extends string | number>(props: { label: string; options: T[]; value: T[]; onChange: (value: T[]) => void; format?: (v: T) => string }) {
  const toggle = (option: T) =>
    props.onChange(props.value.includes(option) ? props.value.filter((v) => v !== option) : [...props.value, option]);
  return (
    <div className="field">
      <span>{props.label}</span>
      <div className="chips" role="group" aria-label={props.label}>
        {props.options.map((option) => (
          <button type="button" key={String(option)} className="chip" aria-pressed={props.value.includes(option)} onClick={() => toggle(option)}>
            {props.format ? props.format(option) : String(option)}
          </button>
        ))}
      </div>
    </div>
  );
}

/** Aranabilir çoklu seçim; seçilenler çip olarak üstte görünür. */
export function MultiSelect(props: {
  label: string; options: string[]; value: string[]; onChange: (value: string[]) => void; disabledHint?: string; allowCustom?: boolean;
}) {
  const [query, setQuery] = useState("");
  const id = useId();
  const visible = useMemo(() => {
    const q = query.toLocaleLowerCase("tr");
    return props.options.filter((o) => !props.value.includes(o) && o.toLocaleLowerCase("tr").includes(q)).slice(0, 60);
  }, [props.options, props.value, query]);

  if (props.disabledHint) {
    return (
      <div className="field">
        <span>{props.label}</span>
        <span className="small">{props.disabledHint}</span>
      </div>
    );
  }
  const add = (option: string) => {
    props.onChange([...props.value, option]);
    setQuery("");
  };
  const custom = props.allowCustom && query.trim() && !props.options.some((o) => o.toLocaleLowerCase("tr") === query.trim().toLocaleLowerCase("tr"));

  return (
    <div className="field">
      <label htmlFor={id}>{props.label}</label>
      {props.value.length > 0 && (
        <div className="chips">
          {props.value.map((v) => (
            <button type="button" key={v} className="chip" aria-pressed="true" onClick={() => props.onChange(props.value.filter((x) => x !== v))} aria-label={`${v} seçimini kaldır`}>
              {v} <span className="x" aria-hidden="true">×</span>
            </button>
          ))}
        </div>
      )}
      <input id={id} className="input" placeholder="Ara…" value={query} onChange={(e) => setQuery(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            if (visible[0]) add(visible[0]);
            else if (custom) add(query.trim());
          }
        }} />
      {(query || props.options.length <= 12) && (visible.length > 0 || custom) && (
        <div style={{ maxHeight: 168, overflow: "auto", border: "1px solid var(--border)", borderRadius: 6 }}>
          {visible.map((option) => (
            <button type="button" key={option} className="btn ghost sm" style={{ width: "100%", justifyContent: "flex-start", color: "var(--ink)" }} onClick={() => add(option)}>
              {option}
            </button>
          ))}
          {custom && (
            <button type="button" className="btn ghost sm" style={{ width: "100%", justifyContent: "flex-start" }} onClick={() => add(query.trim())}>
              “{query.trim()}” ekle
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export const DAY_PRESETS = [1, 3, 7, 14, 30, 60, 90];
const PRESET_LABEL = (d: number) => (d === 1 ? "24 saat" : `${d} gün`);

/** Hazır gün aralığı veya özel tarih aralığı; iki tarih filtresi bu bileşenden ayrı ayrı oluşturulur. */
export function DateWindow(props: {
  label: string; hint: string; days: number | null; from: string | null; to: string | null; allowAll?: boolean;
  onChange: (days: number | null, from: string | null, to: string | null) => void;
}) {
  const custom = props.from !== null || props.to !== null;
  return (
    <div className="field">
      <span>{props.label}</span>
      <span className="small">{props.hint}</span>
      <div className="chips" role="group" aria-label={props.label}>
        {DAY_PRESETS.map((d) => (
          <button type="button" key={d} className="chip" aria-pressed={!custom && props.days === d} onClick={() => props.onChange(d, null, null)}>
            Son {PRESET_LABEL(d)}
          </button>
        ))}
        {props.allowAll && (
          <button type="button" className="chip" aria-pressed={!custom && props.days === null} onClick={() => props.onChange(null, null, null)}>Tümü</button>
        )}
        <button type="button" className="chip" aria-pressed={custom}
          onClick={() => props.onChange(props.days ?? 30, props.from ?? new Date(Date.now() - 30 * 86_400_000).toISOString().slice(0, 10), props.to ?? new Date().toISOString().slice(0, 10))}>
          Özel aralık
        </button>
      </div>
      {custom && (
        <div className="range">
          <input type="date" className="input" aria-label={`${props.label} başlangıç`} value={props.from ?? ""} onChange={(e) => props.onChange(props.days, e.target.value || null, props.to)} />
          <input type="date" className="input" aria-label={`${props.label} bitiş`} value={props.to ?? ""} onChange={(e) => props.onChange(props.days, props.from, e.target.value || null)} />
        </div>
      )}
    </div>
  );
}
