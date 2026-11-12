"""
HKY Estates V2 - Fırsat skoru ve risk değerlendirmesi
Opportunity = Fiyat Avantajı × 0.40 + NLP Aciliyet × 0.30 + Tazelik × 0.30
Risk skoru ayrı tutulur: yüksek skorlu ilan da tapu, hasar veya sahte ilan uyarısı alabilir.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any, List, Optional, Tuple

from .nlp import TextAnalysis

WEIGHT_PRICE, WEIGHT_NLP, WEIGHT_FRESHNESS = 0.40, 0.30, 0.30
# %25 ve üzeri indirim tam puan alır; bu oranı aşan ağırlık, %40'lık payı tek başına belirlerdi.
FULL_SCORE_DISCOUNT = 25.0
SUSPICIOUS_DISCOUNT = 45.0
SALE_PRICE_FLOOR_TL = 150_000
RENT_PRICE_CEILING_TL = 1_000_000
CHEAPEST_REGION_SHARE = 0.25
HIGH_YIELD_PCT = 5.0

DISCLAIMER = (
    "Skorlar ilan verilerine dayalı istatistiksel tahminlerdir; yatırım tavsiyesi veya getiri garantisi değildir. "
    "Satın almadan önce tapu, ekspertiz ve hukuki kontrolleri yaptırın."
)


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def discount_percent(reference: float, value: float) -> float:
    return (reference - value) / reference * 100


def price_advantage_score(discount: Optional[float]) -> float:
    if discount is None or discount <= 0:
        return 0.0
    return round(clamp(discount / FULL_SCORE_DISCOUNT * 100), 1)


def freshness_score(listed_at: Optional[date], today: date, window_days: int) -> float:
    """Yayın günü 100; fırsat penceresinin sonunda 0. Tarihi bilinmeyen ilan taze sayılmaz."""
    if listed_at is None:
        return 0.0
    age = (today - listed_at).days
    if age < 0:
        return 0.0
    return round(clamp((1 - age / max(1, window_days)) * 100), 1)


def opportunity_score(price_advantage: float, nlp: float, freshness: float) -> float:
    return round(price_advantage * WEIGHT_PRICE + nlp * WEIGHT_NLP + freshness * WEIGHT_FRESHNESS, 1)


def classify(score: float) -> str:
    if score >= 90:
        return "Olağanüstü fırsat"
    if score >= 80:
        return "Yüksek fırsat"
    if score >= 65:
        return "İncelenmeye değer"
    return "Normal ilan"


def confidence_label(confidence: float) -> str:
    return "Yüksek" if confidence >= 70 else "Orta" if confidence >= 45 else "Düşük"


@dataclass
class RiskResult:
    score: float
    level: str
    warnings: List[str]
    suspicious: bool


def assess_risk(listing: Any, analysis: TextAnalysis, discount: Optional[float], confidence: float) -> RiskResult:
    """Metin, alan ve fiyat tutarsızlıklarından risk puanı ve uyarılar üretir."""
    points = 0.0
    warnings: List[str] = []

    for risk in analysis.risks:
        points += risk["weight"]
        warnings.append(f"{risk['label']}: resmi kayıtlardan doğrulayın.")

    if discount is not None and discount >= SUSPICIOUS_DISCOUNT:
        points += 40
        warnings.append("Emsallerden aşırı ucuz: veri hatası, sahte ilan veya özel durum olabilir.")

    if listing.main_category == "vasita":
        warnings.append("Araç için bağımsız ekspertiz raporu ve tramer sorgusu alın.")
        if listing.heavy_damage:
            points += 45
            warnings.append("Ağır hasar kayıtlı.")
        elif listing.damage_record:
            points += 20
            warnings.append("Hasar kaydı var.")
        if listing.changed_parts:
            points += min(20, listing.changed_parts * 5)
            warnings.append(f"{listing.changed_parts} değişen parça bildirilmiş.")
    else:
        deed = (listing.deed_status or "").lower()
        if "hisse" in deed or "kooperatif" in deed:
            points += 30
            warnings.append(f"Tapu durumu: {listing.deed_status}.")
        if listing.m2_net and listing.m2_gross and listing.m2_net > listing.m2_gross:
            points += 15
            warnings.append("Tutarsızlık: net m², brüt m²'den büyük.")

    if listing.currency == "TL" and listing.category.startswith("satilik") and listing.price < SALE_PRICE_FLOOR_TL:
        points += 30
        warnings.append("Tutarsızlık: satılık ilan için fiyat çok düşük, kira bedeli girilmiş olabilir.")
    if listing.currency == "TL" and listing.category.startswith("kiralik") and listing.price > RENT_PRICE_CEILING_TL:
        points += 30
        warnings.append("Tutarsızlık: kiralık ilan için fiyat çok yüksek, satış fiyatı girilmiş olabilir.")

    if listing.data_quality < 60:
        points += 15
        warnings.append(f"Eksik ilan bilgisi (veri kalitesi %{listing.data_quality}).")
    if confidence < 45:
        points += 10

    score = round(clamp(points), 1)
    level = "Yüksek" if score >= 40 else "Orta" if score >= 15 else "Düşük"
    suspicious = bool(discount is not None and discount >= SUSPICIOUS_DISCOUNT) or any(r["category"] == "sahte" for r in analysis.risks)
    return RiskResult(score, level, warnings, suspicious)


def reliability_score(data_quality: int, confidence: float) -> float:
    return round(data_quality * 0.5 + confidence * 0.5, 1)


def is_eligible(
    score: float, discount: Optional[float], confidence: float, suspicious: bool, comparable_count: int,
    min_score: float, min_advantage: float, min_comparables: int, min_confidence: float = 0.0,
) -> Tuple[bool, Optional[str]]:
    """Fırsat sayılma koşulları; sayıyı doldurmak için hiçbir koşul gevşetilmez."""
    if comparable_count < min_comparables:
        return False, "Yetersiz emsal"
    if discount is None or discount < min_advantage:
        return False, "Fiyat avantajı yetersiz"
    if suspicious:
        return False, "Şüpheli ilan"
    if confidence < min_confidence:
        return False, "Analiz güveni düşük"
    if score < min_score:
        return False, "Skor eşiğin altında"
    return True, None
