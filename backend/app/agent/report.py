"""
HKY Estates V2 - Fırsat raporu
'Neden bu fırsatı kaçırmamalıyım?' metni yalnızca hesaplanmış değerlerden üretilir;
veri olmayan hiçbir cümle eklenmez. Gelecekte LLM ile zenginleştirme için details alanı saklanır.
"""

from typing import Any, Dict, List, Optional

from .market import ComparableResult
from .nlp import TextAnalysis


def tl(value: Optional[float], currency: str = "TL") -> str:
    if value is None:
        return "-"
    return f"{value:,.0f}".replace(",", ".") + f" {currency}"


def dec(value: float) -> str:
    """Arayüzdeki tr-TR biçimiyle aynı: bir ondalık, virgülle."""
    return f"{value:.1f}".replace(".", ",")


def build_report(
    listing: Any,
    comparables: ComparableResult,
    analysis: TextAnalysis,
    discount: Optional[float],
    estimated_gap: Optional[float],
    freshness_days: Optional[int],
    gross_yield: Optional[float],
    risk_warnings: List[str],
    confidence_label: str,
) -> Dict[str, Any]:
    sentences: List[str] = []
    currency = listing.currency
    stats = comparables.stats

    if comparables.sufficient and stats and discount is not None:
        basis = "TL/m² medyanının" if comparables.kind == "unit" else "fiyat medyanının"
        direction = "altında" if discount > 0 else "üstünde"
        sentences.append(
            f"Bu ilan, {comparables.level_label.lower()} özelliklerine sahip {stats.count} emsal ilanın {basis} "
            f"%{dec(abs(discount))} {direction} fiyatlandırılmıştır."
        )
        if discount > 0 and estimated_gap:
            sentences.append(f"Emsal medyanına göre tahmini fiyat farkı yaklaşık {tl(estimated_gap, currency)}'dir.")
    else:
        sentences.append(
            f"Yeterli emsal bulunamadı (en fazla {comparables.best_count} benzer ilan); fiyat avantajı hesaplanmadı."
        )

    counted = [s for s in analysis.signals if s.get("counted")]
    urgency = [s["label"].lower() for s in counted if s["key"] in ("urgent", "need_sale", "moving", "dispose")]
    if urgency:
        sentences.append(f"İlan açıklamasında satış motivasyonu tespit edildi: {', '.join(dict.fromkeys(urgency))}.")
    if analysis.price_drop_amount:
        sentences.append(f"Satıcı fiyatı yaklaşık {tl(analysis.price_drop_amount, currency)} düşürdüğünü belirtiyor.")
    if listing.price_drop_pct:
        sentences.append(f"Kayıtlı fiyat geçmişine göre ilk görülen fiyattan %{dec(listing.price_drop_pct)} düşüş var.")
    if analysis.parity:
        sentences.append("Açıklamada fiyatın piyasayla aynı olduğu belirtiliyor; bu ifade fiyat avantajı kanıtı sayılmadı.")
    if any(s["key"] in ("below_market", "bargain") for s in counted):
        sentences.append("'Piyasa altı' veya 'kelepir' ifadeleri satıcı beyanıdır; fiyat avantajı yalnızca emsallerden hesaplandı.")
    if freshness_days is not None:
        sentences.append("İlan bugün yayınlandı." if freshness_days == 0 else f"İlan {freshness_days} gün önce yayınlandı.")
    if gross_yield:
        sentences.append(f"Bölgedeki kiralık emsallere göre tahmini brüt kira getirisi yıllık %{dec(gross_yield)}'dir.")
    if comparables.sufficient and comparables.coverage_days:
        sentences.append(f"Analiz {comparables.coverage_days} günlük emsal verisine dayanır; güven seviyesi {confidence_label.lower()}.")
    if risk_warnings:
        sentences.append(f"Dikkat: {len(risk_warnings)} risk uyarısı var; ayrıntılar detay sayfasında.")

    details = {
        "comparables": {
            "level": comparables.level_label,
            "kind": comparables.kind,
            "count": stats.count if stats else 0,
            "median": stats.median if stats else None,
            "mean": stats.mean if stats else None,
            "min": stats.minimum if stats else None,
            "max": stats.maximum if stats else None,
            "outliers_removed": comparables.outliers_removed,
            "coverage_days": comparables.coverage_days,
        },
        "nlp_terms": analysis.terms,
    }
    return {"summary": " ".join(sentences), "details": details}
