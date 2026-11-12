"""Read user-submitted public listing pages only when automated access is allowed."""

import ipaddress
import re
import socket
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from ..network.client import is_blocked_host

MAX_PAGE_BYTES = 4 * 1024 * 1024
BOT_MARKERS = (
    "captcha",
    "verify you are human",
    "verify that you are human",
    "automated access",
    "unusual traffic",
    "robot check",
)
PRICE_PATTERN = re.compile(
    r"(?:₺|TL|TRY|USD|\$|EUR|€)\s*[\d][\d.,\s]{1,}\d|"
    r"[\d][\d.,\s]{1,}\d\s*(?:₺|TL|TRY|USD|\$|EUR|€)",
    re.IGNORECASE,
)


class ListingLinkError(ValueError):
    def __init__(self, message: str, blocked: bool = False) -> None:
        super().__init__(message)
        self.blocked = blocked


def _display_url(url: str) -> str:
    try:
        parts = urlsplit(url)
        if not parts.hostname:
            return "Geçersiz bağlantı"
        host = parts.hostname
        if parts.port:
            host = f"{host}:{parts.port}"
        return urlunsplit((parts.scheme, host, parts.path, "", ""))[:400]
    except ValueError:
        return "Geçersiz bağlantı"


def _validate_public_url(url: str) -> str:
    try:
        parts = urlsplit(url)
        host = parts.hostname
        if parts.scheme != "https" or not host or parts.username or parts.password:
            raise ListingLinkError("Yalnızca kimlik bilgisi içermeyen HTTPS bağlantıları kabul edilir.")
        if is_blocked_host(url):
            raise ListingLinkError("Bu alan adına otomatik erişim desteklenmiyor.", blocked=True)
        addresses = {
            ipaddress.ip_address(result[4][0].split("%", 1)[0])
            for result in socket.getaddrinfo(host, parts.port or 443, type=socket.SOCK_STREAM)
        }
    except ListingLinkError:
        raise
    except (ValueError, OSError) as exc:
        raise ListingLinkError("Bağlantı adresi doğrulanamadı.") from exc
    if not addresses or any(not address.is_global for address in addresses):
        raise ListingLinkError("Yerel veya özel ağ adreslerine erişim engellendi.")
    return host.lower()


def _first_dom_value(page, selectors: List[str]) -> str:
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if not locator.count():
                continue
            value = locator.get_attribute("content") or locator.inner_text(timeout=1000)
            value = re.sub(r"\s+", " ", value or "").strip()
            if value:
                return value
        except PlaywrightError:
            continue
    return ""


def _first_dom_attribute(page, selectors: List[str], attribute: str) -> str:
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if not locator.count():
                continue
            value = locator.get_attribute(attribute) or ""
            if value.strip():
                return value.strip()
        except PlaywrightError:
            continue
    return ""


def _label_value(text: str, labels: str) -> Optional[str]:
    match = re.search(
        rf"(?:^|\n)[ \t]*(?:{labels})[ \t]*(?::[ \t]*([^\n|•]+)|\n[ \t]*([^\n|•]+))",
        text,
        re.IGNORECASE,
    )
    return next((value.strip() for value in match.groups() if value and value.strip()), None) if match else None


def _extract_record(page, url: str) -> Dict[str, Any]:
    body = page.locator("body").inner_text(timeout=3000)
    title = _first_dom_value(page, [
        "h1",
        '[data-testid*="title" i]',
        '[class*="listing-title" i]',
        '[class*="product-title" i]',
        'meta[property="og:title"]',
    ]) or page.title()
    price = _first_dom_value(page, [
        '[itemprop="price"]',
        '[data-testid*="price" i]',
        '[class*="listing-price" i]',
        '[class*="product-price" i]',
        '[class*="price" i]',
    ])
    price_match = PRICE_PATTERN.search(price) or PRICE_PATTERN.search(body)
    if price_match:
        price = price_match.group(0).strip()
    elif price and not re.search(r"\d", price):
        price = ""

    description = _first_dom_value(page, [
        '[itemprop="description"]',
        '[data-testid*="description" i]',
        '[class*="listing-description" i]',
        '[class*="description" i]',
        'meta[name="description"]',
    ])
    if len(description) > 20_000:
        description = description[:20_000]
    image = _first_dom_value(page, [
        '[itemprop="image"]',
        'meta[property="og:image"]',
    ])
    image = image or _first_dom_attribute(page, ["article img", "main img"], "src")
    if image and not image.startswith(("http://", "https://")):
        image = ""
    category = _label_value(body, r"Kategori|Emlak Tipi|Araç Tipi") or title
    listing_id = _label_value(body, r"İlan No|İlan Numarası|Stok No")
    location = _label_value(body, r"Konum|Adres")
    city = _label_value(body, r"İl|Şehir")
    district = _label_value(body, r"İlçe")
    neighbourhood = _label_value(body, r"Mahalle|Semt")
    size = _label_value(body, r"Brüt m²|m² \(Brüt\)|m²")
    rooms = _label_value(body, r"Oda Sayısı|Oda")
    building_age = _label_value(body, r"Bina Yaşı|Binanın Yaşı")
    floor = _label_value(body, r"Bulunduğu Kat|Kat")
    total_floors = _label_value(body, r"Kat Sayısı|Binadaki Kat Sayısı")
    heating = _label_value(body, r"Isıtma|Isınma Tipi")
    bathrooms = _label_value(body, r"Banyo Sayısı|Banyo")
    brand = _label_value(body, r"Marka")
    series = _label_value(body, r"Seri")
    model = _label_value(body, r"Model")
    year = _label_value(body, r"Model Yılı|Yıl")
    kilometres = _label_value(body, r"Kilometre|KM")
    fuel = _label_value(body, r"Yakıt")
    transmission = _label_value(body, r"Vites|Şanzıman")

    if not title or not price:
        raise ListingLinkError("Görünen sayfa içeriğinde ilan başlığı veya fiyat bulunamadı; dosya içe aktarımı kullanın.")
    return {
        "İlan No": str(listing_id or _display_url(url))[:120],
        "İlan Başlığı": title[:400],
        "Kategori": category,
        "Fiyat": price,
        "Açıklama": description,
        "Detay Linki": _display_url(url),
        "Fotoğraf": image[:600] if image else "",
        "İlçe / Mahalle": location or "",
        "İl": city or "",
        "İlçe": district or "",
        "Mahalle": neighbourhood or "",
        "m² (Brüt)": size or "",
        "Oda Sayısı": rooms or "",
        "Bina Yaşı": building_age or "",
        "Bulunduğu Kat": floor or "",
        "Kat Sayısı": total_floors or "",
        "Isıtma": heating or "",
        "Banyo Sayısı": bathrooms or "",
        "Marka": brand or "",
        "Seri": series or "",
        "Model": model or "",
        "Yıl": year or "",
        "KM": kilometres or "",
        "Yakıt": fuel or "",
        "Vites": transmission or "",
    }


def _is_challenge(page) -> bool:
    if page.locator(
        '[id*="captcha" i], [class*="captcha" i], iframe[src*="challenge" i], '
        'input[name*="captcha" i]'
    ).count():
        return True
    text = page.locator("body").inner_text(timeout=3000).lower()
    return any(marker in text for marker in BOT_MARKERS)


def _read_one(browser, url: str) -> Dict[str, Any]:
    host = _validate_public_url(url)
    context = browser.new_context(service_workers="block")
    page = context.new_page()

    def guard(route, request) -> None:
        try:
            request_host = _validate_public_url(request.url)
            if request.resource_type == "document" and request_host != host:
                route.abort()
                return
            route.continue_()
        except ListingLinkError:
            route.abort()

    context.route("**/*", guard)
    try:
        parts = urlsplit(url)
        robots_url = urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))
        robots_response = page.goto(robots_url, wait_until="domcontentloaded", timeout=15_000)
        if robots_response is not None:
            status = robots_response.status
            if status in (401, 403, 429):
                raise ListingLinkError(f"robots.txt erişimi kısıtlandı (HTTP {status}); sayfa atlandı.", blocked=True)
            if status not in (200, 404, 410) and status >= 400:
                raise ListingLinkError(f"robots.txt okunamadı (HTTP {status}); güvenli tarafta kalmak için sayfa atlandı.")
            if status == 200:
                parser = RobotFileParser()
                parser.set_url(robots_url)
                parser.parse(page.locator("body").inner_text().splitlines())
                if not parser.can_fetch("*", url):
                    raise ListingLinkError("robots.txt otomatik erişime izin vermiyor; sayfa atlandı.", blocked=True)

        response = page.goto(url, wait_until="domcontentloaded", timeout=20_000)
        if response is None:
            raise ListingLinkError("Sayfa yanıt vermedi.")
        if response.status in (401, 403, 429):
            raise ListingLinkError(f"Erişim kısıtlandı (HTTP {response.status}); sayfa atlandı.", blocked=True)
        if response.status >= 400:
            raise ListingLinkError(f"Sayfa hata yanıtı verdi (HTTP {response.status}).")
        if len(page.content().encode("utf-8")) > MAX_PAGE_BYTES:
            raise ListingLinkError("Sayfa boyutu izin verilen sınırı aşıyor.")
        if _is_challenge(page):
            raise ListingLinkError("Bot doğrulaması/CAPTCHA görüldü; sayfada işlem yapılmadan durduruldu.", blocked=True)
        return _extract_record(page, url)
    except PlaywrightError as exc:
        raise ListingLinkError("Sayfa yüklenemedi veya yönlendirme güvenlik nedeniyle engellendi.") from exc
    finally:
        context.close()


def import_listing_links(urls: List[str]) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    """Fetch submitted links independently; blocked links do not prevent other URLs from being checked."""
    records: List[Dict[str, Any]] = []
    results: List[Dict[str, str]] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for url in urls:
                try:
                    records.append(_read_one(browser, url))
                    results.append({"url": _display_url(url), "status": "ok", "message": "İlan verisi okundu."})
                except ListingLinkError as exc:
                    results.append({
                        "url": _display_url(url),
                        "status": "blocked" if exc.blocked else "error",
                        "message": str(exc),
                    })
        finally:
            browser.close()
    return records, results
