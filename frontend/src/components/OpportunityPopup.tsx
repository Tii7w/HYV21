import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { Listing, Score } from "../types";
import OpportunityCard from "./OpportunityCard";

type Detail = { listing: Listing; score: Score };

/**
 * Yeni fırsat bulunduğunda ekranın ortasında açılan pencere.
 * Aynı anda birden çok fırsat gelirse sıraya alınır; "Sonraki" ile tek tek gezilir.
 */
export default function OpportunityPopup({
  queue,
  onNext,
  onClose,
  onOpenList,
}: {
  queue: number[];
  onNext: () => void;
  onClose: () => void;
  onOpenList: (isDemo: boolean) => void;
}) {
  const scoreId = queue[0];
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (scoreId === undefined) return;
    let alive = true;
    setDetail(null);
    setError(null);
    api<Detail>(`/api/opportunities/${scoreId}`)
      .then((d) => alive && setDetail(d))
      .catch((e) => alive && setError((e as Error).message));
    return () => {
      alive = false;
    };
  }, [scoreId]);

  useEffect(() => {
    if (scoreId === undefined) return;
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [scoreId, onClose]);

  if (scoreId === undefined) return null;
  const remaining = queue.length - 1;

  return (
    <div className="dialog-backdrop popup-backdrop" role="dialog" aria-modal="true" aria-labelledby="popup-title"
      onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="panel dialog opp-popup">
        <div className="panel-head">
          <h2 id="popup-title">🚨 {detail?.listing.is_demo ? "[DEMO] " : ""}Yeni fırsat bulundu</h2>
          {remaining > 0 && <span className="pill info num">+{remaining} fırsat daha</span>}
        </div>
        <div className="panel-body stack" style={{ gap: 12 }}>
          {error && <div className="notice bad" role="alert">{error}</div>}
          {!detail && !error && <div className="opp" style={{ height: 360 }} aria-busy="true" />}
          {detail && <OpportunityCard listing={detail.listing} score={detail.score} />}
          <p className="small muted" style={{ margin: 0 }}>Bu ilan “Bulunan fırsatlar” sekmesine kaydedildi.</p>
          <div className="popup-actions">
            <button className="btn" onClick={() => onOpenList(detail?.listing.is_demo ?? false)}>Bulunan fırsatlara git</button>
            <span style={{ display: "flex", gap: 8 }}>
              <button ref={closeRef} className="btn ghost" onClick={onClose}>{remaining > 0 ? "Tümünü kapat" : "Kapat"}</button>
              {remaining > 0 && <button className="btn primary" onClick={onNext}>Sonraki</button>}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
