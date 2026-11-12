"""
Sahibinden.com scraper.
Patchright (stealth Chromium) ile sayfayı çeker, Scrapling Selector ile parse eder.
"""

from __future__ import annotations

import random
import re
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from ...schemas import ListingFilters

if TYPE_CHECKING:  # scrapling/patchright opsiyonel: yalnızca fetch_page çağrılınca yüklenir
    from scrapling import Selector

# Sahibinden.com şehir ID'leri (plaka kodu bazlı)
CITY_IDS: Dict[str, int] = {
    "Adana": 1, "Adıyaman": 2, "Afyonkarahisar": 3, "Ağrı": 4,
    "Amasya": 5, "Ankara": 6, "Antalya": 7, "Artvin": 8,
    "Aydın": 9, "Balıkesir": 10, "Bilecik": 11, "Bingöl": 12,
    "Bitlis": 13, "Bolu": 14, "Burdur": 15, "Bursa": 16,
    "Çanakkale": 17, "Çankırı": 18, "Çorum": 19, "Denizli": 20,
    "Diyarbakır": 21, "Edirne": 22, "Elazığ": 23, "Erzincan": 24,
    "Erzurum": 25, "Eskişehir": 26, "Gaziantep": 27, "Giresun": 28,
    "Gümüşhane": 29, "Hakkari": 30, "Hatay": 31, "Isparta": 32,
    "Mersin": 33, "İstanbul": 34, "İzmir": 35, "Kars": 36,
    "Kastamonu": 37, "Kayseri": 38, "Kırklareli": 39, "Kırşehir": 40,
    "Kocaeli": 41, "Konya": 42, "Kütahya": 43, "Malatya": 44,
    "Manisa": 45, "Kahramanmaraş": 46, "Mardin": 47, "Muğla": 48,
    "Muş": 49, "Nevşehir": 50, "Niğde": 51, "Ordu": 52,
    "Rize": 53, "Sakarya": 54, "Samsun": 55, "Siirt": 56,
    "Sinop": 57, "Sivas": 58, "Tekirdağ": 59, "Tokat": 60,
    "Trabzon": 61, "Tunceli": 62, "Şanlıurfa": 63, "Uşak": 64,
    "Van": 65, "Yozgat": 66, "Zonguldak": 67, "Aksaray": 68,
    "Bayburt": 69, "Karaman": 70, "Kırıkkale": 71, "Batman": 72,
    "Şırnak": 73, "Bartın": 74, "Ardahan": 75, "Iğdır": 76,
    "Yalova": 77, "Karabük": 78, "Kilis": 79, "Osmaniye": 80,
    "Düzce": 81,
}

CATEGORY_SLUG: Dict[str, str] = {
    "satilik-konut": "satilik-konut",
    "kiralik-konut": "kiralik-konut",
    "satilik-isyeri": "satilik-isyeri-dukkan",
    "kiralik-isyeri": "kiralik-isyeri-dukkan",
    "satilik-arsa": "satilik-arsa",
    "diger-emlak": "emlak",
    "otomobil": "otomobil",
    "arazi-suv-pickup": "arazi-suv-pickup",
    "motosiklet": "motosiklet",
    "ticari-arac": "ticari-arac",
    "diger-vasita": "vasita",
}

PAGE_SIZE = 24

_HEADERS = {
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
}


def build_search_url(category: str, filters: ListingFilters, page_offset: int = 0) -> str:
    slug = CATEGORY_SLUG.get(category, category)
    params: List[str] = []

    for city in (filters.cities or []):
        city_id = CITY_IDS.get(city)
        if city_id:
            params.append(f"query_city_ids[]={city_id}")

    if filters.price_min is not None:
        params.append(f"price_min={filters.price_min}")
    if filters.price_max is not None:
        params.append(f"price_max={filters.price_max}")
    if filters.m2_min is not None:
        params.append(f"area_min={filters.m2_min}")
    if filters.m2_max is not None:
        params.append(f"area_max={filters.m2_max}")
    for room in (filters.rooms or []):
        params.append(f"query_room_count[]={room}")
    if page_offset:
        params.append(f"pagingOffset={page_offset}")

    qs = "&".join(params)
    return f"https://www.sahibinden.com/{slug}?{qs}" if qs else f"https://www.sahibinden.com/{slug}"


def _clean_price(text: str) -> Optional[int]:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else None


def _parse_rows(sel: Selector) -> List[Dict[str, Any]]:
    rows = sel.css("tr.searchResultsItem")
    results: List[Dict[str, Any]] = []

    for row in rows:
        listing_id = row.attrib.get("data-id", "")

        title_el = row.find("h3.classifiedTitle a")
        title = title_el.text.strip() if title_el else ""
        href = title_el.attrib.get("href", "") if title_el else ""
        detail_url = (
            f"https://www.sahibinden.com{href}" if href.startswith("/") else href
        )

        price_el = row.find("td.searchResultsPriceValue")
        price_text = price_el.text.strip() if price_el else ""
        price = _clean_price(price_text)

        location_el = row.find("td.searchResultsLocationValue")
        location_text = location_el.text.strip() if location_el else ""

        date_el = row.find("td.searchResultsDateValue")
        date_text = date_el.text.strip() if date_el else ""

        detail_els = row.css("td.searchResultsAttributeValue")
        attributes = [el.text.strip() for el in detail_els if el.text.strip()]

        if not (listing_id and title):
            continue

        results.append({
            "external_id": listing_id,
            "title": title,
            "url": detail_url,
            "price": price,
            "price_text": price_text,
            "location_text": location_text,
            "date_text": date_text,
            "attributes": attributes,
            "source": "sahibinden",
        })

    return results


RESULTS_PAGE_MARKERS = ("searchResultsTable", "searchResultsItem")
NO_RESULTS_MARKERS = ("aramanızla eşleşen ilan bulunamadı", "kriterlere uygun ilan bulunamadı", "ilan bulunamadı")


class NotAListingPage(RuntimeError):
    """Arama sonucu yerine başka bir sayfa (bot doğrulaması, hata, boş sayfa) döndü."""


def check_results_page(html: str) -> None:
    """Sayfa gerçekten bir arama sonucu mu? Değilse 0 ilanı sessizce kabul etmek yerine hata verir.

    Captcha/doğrulama sayfası ÇÖZÜLMEZ; yalnızca tespit edilip açıkça raporlanır.
    """
    if any(marker in html for marker in RESULTS_PAGE_MARKERS):
        return
    lowered = html.lower()
    if any(marker in lowered for marker in NO_RESULTS_MARKERS):
        return
    raise NotAListingPage(
        "Sahibinden ilan listesi yerine farklı bir sayfa döndürdü (büyük ihtimalle bot doğrulaması "
        "veya erişim engeli). 0 ilan gerçek bir sonuç değil; bir süre bekleyip tekrar deneyin."
    )


def _has_next_page(sel: Selector) -> bool:
    return sel.find("a.prevNextBut[title='Sonraki']") is not None


def fetch_page(url: str, headless: bool = True) -> tuple[List[Dict[str, Any]], bool]:
    """
    Patchright (stealth Chromium) ile sayfayı çeker.
    Homepage'i önce ziyaret ederek cookie/session kurar, ardından arama URL'ine gider.
    """
    from patchright.sync_api import sync_playwright
    from scrapling import Selector

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        context = browser.new_context(
            locale="tr-TR",
            timezone_id="Europe/Istanbul",
            extra_http_headers=_HEADERS,
            viewport={"width": 1366, "height": 768},
        )
        page = context.new_page()

        # 1) Ana sayfayı ziyaret et — cookie ve session için
        page.goto("https://www.sahibinden.com/", wait_until="domcontentloaded", timeout=30000)
        time.sleep(random.uniform(1.5, 2.5))

        # 2) Arama sayfasına git
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        time.sleep(random.uniform(1.5, 3.0))

        final_url = page.url
        html = page.content()
        browser.close()

    if "giris" in final_url or "secure.sahibinden.com" in final_url:
        raise NotAListingPage(
            f"Sahibinden giriş sayfasına yönlendirdi: {final_url}\n"
            "Bot tespiti yapılmış olabilir; proxy veya bekleme süresi artırılabilir."
        )

    check_results_page(html)
    sel = Selector(content=html, url=url)
    records = _parse_rows(sel)
    has_next = _has_next_page(sel)
    return records, has_next
