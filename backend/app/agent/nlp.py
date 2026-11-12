"""
HKY Estates V2 - Türkçe ilan metni analizi
Kural tabanlı bağlam analizi ve TF-IDF kullanır. Olumsuzluk, sohbet dışı 'acil' kullanımı ve
'piyasayla aynı' gibi ifadeler ayrıştırılır. Yeni model eklemek için TextAnalyzer yeterlidir.
"""

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Protocol, Tuple

from .normalizer import fold_turkish

STRONG, MEDIUM, WEAK = 3, 2, 1
SENSITIVITY_MIN_STRENGTH = {"dusuk": STRONG, "orta": MEDIUM, "yuksek": WEAK}

NON_SALE_URGENCY = re.compile(r"\bacil\s+(?:servis|cikis|durum|kapi|aydinlatma|yardim|hastane|numara)\w*")
CLAUSE_SPLIT = re.compile(r"[.!?;\n]+|,\s+|\s+ama\s+|\s+fakat\s+|\s+ancak\s+")
NEGATION_AFTER = re.compile(
    r"^(?:\W*\w+){0,3}?\W*\b(?:degil\w*|yok\w*|olma\w*|bulunma\w*|yapilmaz|olmaz|edilmez|alinmaz|verilmez|"
    r"dusunmuyor\w*|dusunulmuyor\w*|dusunulmez|istemiyor\w*|istenmez)\b"
)
TOKEN = re.compile(r"[a-z0-9]+")
AMOUNT = re.compile(r"(\d[\d.,]*)\s*(bin|milyon)?\s*(?:tl|lira|₺)?")
STOPWORDS = frozenset(
    "ve veya ile icin bir bu su o da de ki mi mu en cok daha gibi olan olarak ama fakat var yok ilan "
    "satilik kiralik tl m2 metrekare".split()
)


@dataclass(frozen=True)
class Rule:
    key: str
    label: str
    pattern: "re.Pattern[str]"
    weight: float
    strength: int


def _rule(key: str, label: str, pattern: str, weight: float, strength: int) -> Rule:
    return Rule(key, label, re.compile(pattern), weight, strength)


SIGNAL_RULES: Tuple[Rule, ...] = (
    _rule("urgent", "Acil satış", r"\bacil(?:en)?\s+(?:satilik|satiyorum|satilir|satis|devren)\w*|\bsahibinden\s+acil\b|\bcok\s+acil\b", 50, STRONG),
    _rule("urgent", "Acil satış", r"\bacil\b", 30, MEDIUM),
    _rule("need_sale", "Nakit ihtiyacı", r"\bacil\s+nakit\b|\bnakit\s+ihtiyac\w*|\bparaya\s+(?:ihtiyac|sikis)\w*|\bihtiyactan\s+sat\w*|\bihtiyac\w*\s+(?:nedeniyle|dolayi)\b", 50, STRONG),
    _rule("need_sale", "Borç nedeni", r"\bborc(?:tan|lardan)\b|\bborc\w*\s+(?:dolayi|nedeni\w*|sebebi\w*)", 45, STRONG),
    _rule("need_sale", "Zorunlu satış", r"\bmecburen\b|\bzorunlu(?:luktan)?\s+sat\w*", 35, MEDIUM),
    _rule("moving", "Taşınma nedeni", r"\btasinacag\w*|\btasiniyor\w*|\btasinma\s+nedeni\w*|\b(?:yurt|sehir)\s*disina\s+(?:cik|tasin|gid)\w*", 25, MEDIUM),
    _rule("dispose", "Elden çıkarma isteği", r"\belden\s+cikar\w*", 25, MEDIUM),
    _rule("price_drop", "Fiyat düşüşü", r"\bfiyat\w*\s+(?:\d[\d.,]*\s*(?:bin|milyon)?\s*(?:tl|lira)?\s*)?(?:dustu|dusuruldu|dusurdum|dusurulmustur|indirildi|indirdim|indi)\b|\bindirim\s+yapildi\b", 35, STRONG),
    _rule("below_market", "Piyasa altı (satıcı beyanı)", r"\bpiyasa(?:nin)?\s+(?:degerinin\s+)?alti\w*|\bdegerinin\s+alti\w*|\bemsal\w*\s+alti\w*", 20, MEDIUM),
    _rule("bargain", "Kelepir / fırsat (satıcı beyanı)", r"\bkelepir\w*|\byok\s+pahasina\b|\bzararina\b|\bkacirilmayacak\s+firsat\w*|\bfirsat\s+fiyat\w*", 15, MEDIUM),
    _rule("negotiable", "Pazarlık payı", r"\bpazarlik\s+pay\w*|\bpazarlikli\b|\bpazarliga\s+acik\b|\bpazarlik\b", 12, WEAK),
    _rule("swap", "Takas", r"\btakas\w*", 4, WEAK),
    _rule("investment", "Yatırımlık", r"\byatirimlik\b|\byatirima\s+uygun\b|\bkira\s+getirisi\b|\bamorti\b", 4, WEAK),
)
PARITY_PATTERN = re.compile(
    r"\bpiyasa\w*\s+(?:fiyat\w*\s+)?(?:ile\s+)?ayni\w*|\bpiyasa\s+(?:fiyat|deger)inde\b|\bemsal\w*\s+(?:ile\s+)?ayni\w*"
)
NEGATED_PHRASES = (
    (re.compile(r"\bacele\w*\s+(?:yok|degil)\w*"), "urgent"),
    (re.compile(r"\bpazarliksiz\b|\bson\s+fiyat\w*"), "negotiable"),
    (re.compile(r"\btakassiz\b"), "swap"),
)
RISK_RULES: Tuple[Tuple[str, str, "re.Pattern[str]", float], ...] = (
    ("tapu", "Hisseli tapu ifadesi", re.compile(r"\bhisseli\b|\bhisse\s+satis\w*"), 30),
    ("tapu", "İpotek ifadesi", re.compile(r"\bipotek\w*"), 30),
    ("hukuki", "Haciz ifadesi", re.compile(r"\bhaciz\w*"), 40),
    ("tapu", "İskan sorunu ifadesi", re.compile(r"\biskansiz\b|\biskani\s+yok\b"), 25),
    ("tapu", "Kooperatif / kat karşılığı", re.compile(r"\bkooperatif\w*|\bkat\s+karsiligi\b"), 15),
    ("hukuki", "İntifa / imar sorunu", re.compile(r"\bintifa\w*|\bimar\s+sorun\w*|\btapu\s+sorun\w*"), 30),
    ("sahte", "Görmeden ödeme talebi", re.compile(r"\bkapora\w*|\bkaparo\w*|\bon\s+odeme\b"), 35),
    ("hasar", "Ağır hasar / pert ifadesi", re.compile(r"\bagir\s+hasar\w*|\bpert\b"), 45),
    ("hasar", "Hasar kaydı ifadesi", re.compile(r"\bhasarli\b|\btramer\s+kayit\w*"), 15),
)


@dataclass
class TextAnalysis:
    score: float = 0.0
    signals: List[Dict[str, Any]] = field(default_factory=list)
    negated: List[Dict[str, Any]] = field(default_factory=list)
    risks: List[Dict[str, Any]] = field(default_factory=list)
    parity: bool = False
    price_drop_amount: Optional[int] = None
    terms: List[str] = field(default_factory=list)

    @property
    def keys(self) -> List[str]:
        return sorted({signal["key"] for signal in self.signals})

    def as_dict(self) -> Dict[str, Any]:
        return {
            "score": self.score, "signals": self.signals, "negated": self.negated, "risks": self.risks,
            "parity": self.parity, "price_drop_amount": self.price_drop_amount, "terms": self.terms,
        }


class TextAnalyzer(Protocol):
    def analyze(self, title: str, description: str, sensitivity: str = "orta") -> TextAnalysis: ...


def tokenize(text: str) -> List[str]:
    return [t for t in TOKEN.findall(fold_turkish(text)) if len(t) > 2 and t not in STOPWORDS and not t.isdigit()]


def _extract_amount(clause: str) -> Optional[int]:
    for number, unit in AMOUNT.findall(clause):
        digits = number.replace(".", "").replace(",", "")
        if not digits:
            continue
        value = int(digits) * {"bin": 1_000, "milyon": 1_000_000}.get(unit, 1)
        if value >= 1000:
            return value
    return None


def _is_negated(clause: str, end: int) -> bool:
    return bool(NEGATION_AFTER.match(clause[end:]))


class RuleBasedAnalyzer:
    def analyze(self, title: str, description: str, sensitivity: str = "orta") -> TextAnalysis:
        result = TextAnalysis()
        min_strength = SENSITIVITY_MIN_STRENGTH.get(sensitivity, MEDIUM)
        text = NON_SALE_URGENCY.sub(" ", fold_turkish(f"{title}. {description}"))
        clauses = [c.strip() for c in CLAUSE_SPLIT.split(text) if c.strip()]

        seen_groups: Dict[str, float] = {}
        for clause in clauses:
            if PARITY_PATTERN.search(clause):
                result.parity = True
            for pattern, key in NEGATED_PHRASES:
                if pattern.search(clause):
                    result.negated.append({"key": key, "evidence": clause[:120]})
            for rule in SIGNAL_RULES:
                match = rule.pattern.search(clause)
                if not match:
                    continue
                if _is_negated(clause, match.end()):
                    result.negated.append({"key": rule.key, "evidence": clause[:120]})
                    continue
                group = f"{rule.key}:{rule.label}"
                if rule.key == "price_drop" and result.price_drop_amount is None:
                    result.price_drop_amount = _extract_amount(clause)
                if group not in seen_groups:
                    seen_groups[group] = rule.weight
                    result.signals.append(
                        {
                            "key": rule.key, "label": rule.label, "evidence": clause[:120], "weight": rule.weight,
                            # Hassasiyet yalnızca skora etkiyi belirler; sinyal filtrelerde yine kullanılır.
                            "counted": rule.strength >= min_strength,
                        }
                    )

            seen_risks = {risk["label"] for risk in result.risks}
            for category, label, pattern, weight in RISK_RULES:
                match = pattern.search(clause)
                if match and label not in seen_risks and not _is_negated(clause, match.end()):
                    result.risks.append({"category": category, "label": label, "weight": weight})

        negated_keys = {item["key"] for item in result.negated}
        # 'Acil satılık değildir' cümlesi tek başına 'acil' kuralını da tetikleyebilir.
        result.signals = [s for s in result.signals if not (s["key"] in negated_keys and s["key"] in ("urgent", "negotiable", "swap"))]
        if result.parity:
            result.signals = [s for s in result.signals if s["key"] not in ("below_market", "bargain")]

        # Aynı anahtarın birden çok kuralı toplanmaz; en güçlüsü sayılır.
        best: Dict[str, float] = {}
        for signal in result.signals:
            if signal["counted"]:
                best[signal["key"]] = max(best.get(signal["key"], 0), signal["weight"])
        total = sum(best.values())
        if "urgent" in negated_keys:
            total -= 30
        result.score = round(max(0.0, min(100.0, total)), 1)
        return result


class TfIdfIndex:
    """Bağımlılıksız TF-IDF: ayırt edici terimler ve yakın kopya ilan tespiti için kullanılır."""

    def __init__(self, documents: Iterable[str]) -> None:
        tokenized = [Counter(tokenize(doc)) for doc in documents]
        self.doc_count = len(tokenized)
        frequency: Counter = Counter()
        for counts in tokenized:
            frequency.update(counts.keys())
        self.idf = {term: math.log((1 + self.doc_count) / (1 + df)) + 1 for term, df in frequency.items()}

    def vector(self, document: str) -> Dict[str, float]:
        counts = Counter(tokenize(document))
        total = sum(counts.values()) or 1
        weights = {t: c / total * self.idf.get(t, math.log(1 + self.doc_count) + 1) for t, c in counts.items()}
        norm = math.sqrt(sum(v * v for v in weights.values())) or 1.0
        return {t: v / norm for t, v in weights.items()}

    def top_terms(self, document: str, limit: int = 6) -> List[str]:
        vector = self.vector(document)
        return [t for t, _ in sorted(vector.items(), key=lambda item: (-item[1], item[0]))[:limit]]


def cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(value * b.get(term, 0.0) for term, value in a.items())
