"""
HKY Estates V2 - Veri normalizasyonu
Farklı kaynaklardaki ham kayıtları tek biçime getirir. Yalnızca izinli alanlar geçer;
açıklamadaki telefon numaraları da maskelenir. Excel sütun adları HKYEstatesBot ile uyumludur.
"""

import hashlib
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlsplit

TURKISH_MONTHS = {
    "ocak": 1, "şubat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "haziran": 6,
    "temmuz": 7, "ağustos": 8, "eylül": 9, "ekim": 10, "kasım": 11, "aralık": 12,
}
TURKISH_FOLD = str.maketrans("ığüşöçâîû", "igusocaiu")

COLUMN_ALIASES = {
    "İlan Numarası": "İlan No", "ilan_no": "İlan No", "id": "İlan No", "source_listing_id": "İlan No",
    "İlan Linki": "Detay Linki", "url": "Detay Linki", "link": "Detay Linki",
    "Tam Konum Metni": "İlçe / Mahalle", "İlan Açıklaması": "Açıklama", "description": "Açıklama",
    "title": "İlan Başlığı", "Başlık": "İlan Başlığı", "price": "Fiyat", "category": "Kategori",
    "Brüt m²": "m² (Brüt)", "m2 (Brüt)": "m² (Brüt)", "m²": "m² (Brüt)", "m2": "m² (Brüt)",
    "Net m²": "m² (Net)", "m2 (Net)": "m² (Net)", "Oda": "Oda Sayısı", "rooms": "Oda Sayısı",
    "Banyo": "Banyo Sayısı", "Kat": "Bulunduğu Kat", "Binadaki Kat Sayısı": "Kat Sayısı",
    "Binanın Yaşı": "Bina Yaşı", "Isınma Tipi": "Isıtma", "Şehir": "İl", "city": "İl", "district": "İlçe",
    "neighbourhood": "Mahalle", "listed_at": "İlan Tarihi", "photo_url": "Fotoğraf", "Kilometre": "KM", "km": "KM",
    "brand": "Marka", "series": "Seri", "model": "Model", "year": "Yıl", "Model Yılı": "Yıl",
}

PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?90[\s.-]*)?\(?0?\s*[2-5]\d{2}\)?[\s.-]*\d{3}[\s.-]*\d{2}[\s.-]*\d{2}(?!\d)")
LOCATION_SUFFIX = re.compile(r"\s*(?:mahallesi|mah\.?|mh\.?)\s*$", re.IGNORECASE)
HOUSING_TYPES = {
    "daire": "Daire", "rezidans": "Rezidans", "residence": "Rezidans", "mustakil": "Müstakil Ev",
    "villa": "Villa", "ciftlik": "Çiftlik Evi", "yazlik": "Yazlık",
}
BUSINESS_HINTS = ("is yeri", "isyeri", "dukkan", "magaza", "ofis", "depo", "plaza", "devren")
VEHICLE_HINTS = (
    ("arazi", "arazi-suv-pickup"), ("suv", "arazi-suv-pickup"), ("pickup", "arazi-suv-pickup"),
    ("motosiklet", "motosiklet"), ("minivan", "ticari-arac"), ("panelvan", "ticari-arac"),
    ("kamyon", "ticari-arac"), ("ticari", "ticari-arac"), ("otobus", "ticari-arac"), ("otomobil", "otomobil"),
)
KEY_FIELDS = {
    "emlak": ("price", "m2_gross", "rooms", "district", "neighbourhood", "listed_at", "title", "description"),
    "vasita": ("price", "brand", "series", "year", "km", "fuel", "transmission", "listed_at", "description"),
}


class NormalizationError(ValueError):
    pass


def turkish_lower(text: str) -> str:
    return text.replace("İ", "i").replace("I", "ı").lower()


def fold_turkish(text: str) -> str:
    return turkish_lower(text).translate(TURKISH_FOLD)


def turkish_title(text: str) -> str:
    words = []
    for word in re.sub(r"\s+", " ", text).strip().split(" "):
        if not word:
            continue
        first = word[0].replace("i", "İ").replace("ı", "I").upper()
        words.append(first + turkish_lower(word[1:]))
    return " ".join(words)


def _text(raw: Dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if value is None:
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip()
    return "" if text.lower() in ("nan", "none", "null", "-", "belirtilmemiş") else text


def parse_currency(raw_price: object) -> str:
    text = str(raw_price or "").split("\n")[0].upper()
    if "USD" in text or "$" in text:
        return "USD"
    if "EUR" in text or "€" in text:
        return "EUR"
    if "GBP" in text or "£" in text:
        return "GBP"
    return "TL"


def parse_amount(raw_price: object) -> Optional[int]:
    text = str(raw_price or "").split("\n")[0]
    digits = re.sub(r"\D", "", re.sub(r",\d{1,2}(?!\d)", "", text))
    value = int(digits) if digits else 0
    return value if value > 0 else None


def parse_int(raw: object) -> Optional[int]:
    """Metindeki ilk sayıyı okur; '11-15 arası' için 11, '125.000' için 125000 döner."""
    match = re.search(r"\d[\d.]*", str(raw or ""))
    if not match:
        return None
    digits = match.group().replace(".", "")
    return int(digits) if digits else None


def parse_m2(raw_m2: object, title: str = "") -> Optional[int]:
    value = parse_int(raw_m2) or 0
    if not value:
        match = re.search(r"(?<![\d.,])(\d{2,4})\s*(?:m²|m2|metrekare|metre\s*kare)", title, flags=re.IGNORECASE)
        value = int(match.group(1)) if match else 0
    return value if 15 <= value <= 100_000 else None


def parse_room(raw_room: object, title: str = "") -> Optional[str]:
    for text in (str(raw_room or ""), title):
        match = re.search(r"(?<![\d.,])(\d(?:[.,]5)?)\s*\+\s*(\d)(?!\d)", text)
        if match:
            return f"{match.group(1).replace(',', '.')}+{match.group(2)}"
    return None


def parse_listing_date(raw_date: object, today: date) -> Optional[date]:
    if isinstance(raw_date, datetime):
        return raw_date.date()
    if isinstance(raw_date, date):
        return raw_date
    text = str(raw_date or "").strip()
    if not text:
        return None
    lowered = turkish_lower(text)
    if "bugün" in lowered or "bugun" in lowered:
        return today
    if "dün" in lowered or "dun" in lowered:
        return today - timedelta(days=1)
    ago = re.search(r"(\d+)\s*g[üu]n\s*[öo]nce", lowered)
    if ago:
        return today - timedelta(days=int(ago.group(1)))
    iso = re.match(r"(\d{4})-(\d{2})-(\d{2})", text)
    dotted = re.match(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", text)
    named = re.search(r"(\d{1,2})\s+([^\W\d]+)\s+(\d{4})", text)
    try:
        if iso:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        if dotted:
            return date(int(dotted.group(3)), int(dotted.group(2)), int(dotted.group(1)))
        if named and turkish_lower(named.group(2)) in TURKISH_MONTHS:
            return date(int(named.group(3)), TURKISH_MONTHS[turkish_lower(named.group(2))], int(named.group(1)))
    except ValueError:
        return None
    return None


def parse_bool(raw: object) -> Optional[bool]:
    text = fold_turkish(str(raw or "")).strip()
    if not text or text in ("nan", "none", "-"):
        return None
    if text in ("yok", "hayir", "no", "false", "0"):
        return False
    return True


def clean_location(value: str) -> str:
    return turkish_title(LOCATION_SUFFIX.sub("", value)) if value else ""


def classify_category(text: str, has_vehicle_fields: bool) -> Tuple[str, str, Optional[str]]:
    """Kategori metninden (ana kategori, kategori, emlak tipi) üretir."""
    folded = fold_turkish(text)
    is_rent = "kiralik" in folded or "gunluk" in folded
    is_sale = "satilik" in folded or "devren" in folded

    # Emlak ipuçları önce bakılır: 'Ticari imarlı arsa' bir vasıta değildir.
    if "arsa" in folded:
        return "emlak", "satilik-arsa" if is_sale else "diger-emlak", "Arsa"
    if any(hint in folded for hint in BUSINESS_HINTS):
        return "emlak", "kiralik-isyeri" if is_rent else "satilik-isyeri", "İş Yeri"
    for hint, label in HOUSING_TYPES.items():
        if hint in folded:
            if is_rent or is_sale:
                return "emlak", "kiralik-konut" if is_rent else "satilik-konut", label
            return "emlak", "diger-emlak", label

    for hint, category in VEHICLE_HINTS:
        if hint in folded:
            return "vasita", category, None
    if has_vehicle_fields:
        return "vasita", "otomobil", None
    if "vasita" in folded:
        return "vasita", "diger-vasita", None
    return "emlak", "diger-emlak", turkish_title(text) if text else None


def safe_http_url(value: str) -> Optional[str]:
    """Arayüzde bağlantı olacağı için yalnızca http(s) adreslerine izin verilir."""
    try:
        parts = urlsplit(value)
    except ValueError:
        return None
    return value[:600] if parts.scheme in ("http", "https") and parts.netloc else None


def scrub_personal_data(text: str) -> str:
    return PHONE_PATTERN.sub("[telefon gizlendi]", text)


def _split_location(raw: Dict[str, Any]) -> Tuple[str, str, str]:
    combined = [part.strip() for part in _text(raw, "İlçe / Mahalle").split("/") if part.strip()]
    city, district, hood = _text(raw, "İl"), _text(raw, "İlçe"), _text(raw, "Mahalle")
    if len(combined) >= 3:
        city, district, hood = city or combined[0], district or combined[1], hood or combined[-1]
    elif len(combined) == 2:
        district, hood = district or combined[0], hood or combined[1]
    elif len(combined) == 1:
        hood = hood or combined[0]
    return clean_location(city), clean_location(district), clean_location(hood)


def _damage(raw: Dict[str, Any]) -> Tuple[Optional[bool], Optional[bool]]:
    status = fold_turkish(_text(raw, "Hasar Durumu"))
    heavy = parse_bool(raw.get("Ağır Hasar")) if _text(raw, "Ağır Hasar") else None
    if "agir" in status or "pert" in status:
        heavy = True
    if not status:
        return None, heavy
    return ("hasarsiz" not in status and "yok" not in status), (heavy if heavy is not None else False)


def _quality(main_category: str, record: Dict[str, Any]) -> int:
    fields = KEY_FIELDS[main_category]
    return round(sum(1 for name in fields if record.get(name) not in (None, "")) / len(fields) * 100)


def compute_dedupe_key(record: Dict[str, Any]) -> str:
    identity = [
        record["category"], record.get("city"), record.get("district"), record.get("neighbourhood"),
        record.get("rooms"), record.get("m2_gross"), record["price"], record.get("brand"), record.get("series"),
        record.get("year"), record.get("km"), re.sub(r"\W+", "", fold_turkish(record.get("title") or "")),
    ]
    return hashlib.sha256("|".join(str(part) for part in identity).encode("utf-8")).hexdigest()


def normalize_record(raw_input: Dict[str, Any], source_key: str, is_demo: bool, today: date) -> Dict[str, Any]:
    """Ham kaydı Listing alanlarına çevirir; kullanılamayan kayıtta NormalizationError fırlatır."""
    raw = dict(raw_input)
    for old, new in COLUMN_ALIASES.items():
        if old in raw and new not in raw:
            raw[new] = raw[old]

    listing_id = _text(raw, "İlan No") or str(raw.get("_import_ref") or "")
    if not listing_id:
        raise NormalizationError("İlan numarası yok.")

    price = parse_amount(raw.get("Fiyat"))
    if price is None:
        raise NormalizationError("Fiyat okunamadı.")

    title = scrub_personal_data(_text(raw, "İlan Başlığı"))[:400]
    description = scrub_personal_data(str(raw.get("Açıklama") or "")).strip()
    if description.lower() in ("nan", "none"):
        description = ""
    city, district, hood = _split_location(raw)
    has_vehicle = bool(_text(raw, "Marka"))
    main_category, category, property_type = classify_category(_text(raw, "Kategori"), has_vehicle)

    record: Dict[str, Any] = {
        "source_key": source_key,
        "source_listing_id": listing_id[:120],
        "is_demo": is_demo,
        "main_category": main_category,
        "category": category,
        "property_type": property_type,
        "title": title,
        "description": description,
        "url": safe_http_url(_text(raw, "Detay Linki")),
        "photo_url": safe_http_url(_text(raw, "Fotoğraf")),
        "country": turkish_title(_text(raw, "Ülke")) or "Türkiye",
        "city": city or None,
        "district": district or None,
        "neighbourhood": hood or None,
        "price": price,
        "currency": parse_currency(raw.get("Fiyat")),
        "listed_at": parse_listing_date(raw.get("İlan Tarihi"), today),
        "status": "removed" if any(word in fold_turkish(_text(raw, "Durum")) for word in ("kaldir", "pasif", "silin")) else "active",
    }

    if main_category == "emlak":
        m2_gross = parse_m2(raw.get("m² (Brüt)"), title)
        record.update(
            m2_gross=m2_gross,
            m2_net=parse_m2(raw.get("m² (Net)")),
            rooms=parse_room(raw.get("Oda Sayısı"), title),
            living_rooms=parse_int(raw.get("Salon Sayısı")),
            building_age=parse_int(raw.get("Bina Yaşı")),
            floor=_text(raw, "Bulunduğu Kat")[:30] or None,
            total_floors=parse_int(raw.get("Kat Sayısı")),
            heating=_text(raw, "Isıtma")[:60] or None,
            bathrooms=parse_int(raw.get("Banyo Sayısı")),
            balcony=parse_bool(raw.get("Balkon")),
            elevator=parse_bool(raw.get("Asansör")),
            parking=parse_bool(raw.get("Otopark")),
            in_site=parse_bool(raw.get("Site İçerisinde")),
            deed_status=_text(raw, "Tapu Durumu")[:60] or None,
            credit_eligible=parse_bool(raw.get("Krediye Uygun")),
            furnished=parse_bool(raw.get("Eşyalı")),
            price_per_m2=round(price / m2_gross, 2) if m2_gross else None,
        )
    else:
        damage_record, heavy_damage = _damage(raw)
        year = parse_int(_text(raw, "Yıl"))
        record.update(
            brand=turkish_title(_text(raw, "Marka")) or None,
            series=turkish_title(_text(raw, "Seri")) or None,
            model=_text(raw, "Model")[:120] or None,
            year=year if year and 1950 <= year <= today.year + 1 else None,
            km=parse_int(raw.get("KM")),
            fuel=turkish_title(_text(raw, "Yakıt")) or None,
            transmission=turkish_title(_text(raw, "Vites")) or None,
            engine_cc=parse_int(raw.get("Motor Hacmi")),
            engine_hp=parse_int(raw.get("Motor Gücü")),
            body_type=turkish_title(_text(raw, "Kasa Tipi")) or None,
            drive_type=turkish_title(_text(raw, "Çekiş")) or None,
            color=turkish_title(_text(raw, "Renk")) or None,
            damage_record=damage_record,
            heavy_damage=heavy_damage,
            paint_status=turkish_title(_text(raw, "Boya")) or None,
            changed_parts=parse_int(raw.get("Değişen")),
        )
    # 'Kimden' sütununda parantez içinde satıcı adı bulunabilir; yalnızca tür saklanır.
    record["seller_type"] = re.sub(r"\s*\(.*\)$", "", _text(raw, "Kimden"))[:30] or None
    record["data_quality"] = _quality(main_category, record)
    record["dedupe_key"] = compute_dedupe_key(record)
    return record
