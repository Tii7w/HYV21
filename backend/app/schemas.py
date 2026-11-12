"""
HKY Estates V2 - API şemaları
Filtreler ve ayarlar burada doğrulanır; agent ile ana sayfa aynı filtre tanımını kullanır.
"""

from datetime import date
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

EMLAK_CATEGORIES = ["satilik-konut", "kiralik-konut", "satilik-isyeri", "kiralik-isyeri", "satilik-arsa", "diger-emlak"]
VASITA_CATEGORIES = ["otomobil", "arazi-suv-pickup", "motosiklet", "ticari-arac", "diger-vasita"]
CONFIDENCE_MINIMUMS = {"Düşük": 0.0, "Orta": 45.0, "Yüksek": 70.0}


class ListingFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_mode: Literal["real", "demo"] = "real"
    main_category: Optional[Literal["emlak", "vasita"]] = None
    categories: List[str] = []

    country: str = "Türkiye"
    cities: List[str] = []
    districts: List[str] = []
    neighbourhoods: List[str] = []

    currency: str = "TL"
    price_min: Optional[int] = Field(default=None, ge=0)
    price_max: Optional[int] = Field(default=None, ge=0)
    unit_price_min: Optional[int] = Field(default=None, ge=0)
    unit_price_max: Optional[int] = Field(default=None, ge=0)
    below_regional_avg: bool = False
    below_regional_median: bool = False

    m2_basis: Literal["brut", "net"] = "brut"
    m2_min: Optional[int] = Field(default=None, ge=0)
    m2_max: Optional[int] = Field(default=None, ge=0)
    rooms: List[str] = []
    living_rooms: List[int] = []
    building_age_min: Optional[int] = Field(default=None, ge=0)
    building_age_max: Optional[int] = Field(default=None, ge=0)
    floors: List[str] = []
    total_floors_min: Optional[int] = Field(default=None, ge=0)
    total_floors_max: Optional[int] = Field(default=None, ge=0)
    heating: List[str] = []
    bathrooms: List[int] = []
    balcony: Optional[bool] = None
    elevator: Optional[bool] = None
    parking: Optional[bool] = None
    in_site: Optional[bool] = None
    deed_status: List[str] = []
    credit_eligible: Optional[bool] = None
    furnished: Optional[bool] = None

    brands: List[str] = []
    series: List[str] = []
    year_min: Optional[int] = None
    year_max: Optional[int] = None
    km_min: Optional[int] = Field(default=None, ge=0)
    km_max: Optional[int] = Field(default=None, ge=0)
    fuels: List[str] = []
    transmissions: List[str] = []
    engine_cc_min: Optional[int] = Field(default=None, ge=0)
    engine_cc_max: Optional[int] = Field(default=None, ge=0)
    engine_hp_min: Optional[int] = Field(default=None, ge=0)
    engine_hp_max: Optional[int] = Field(default=None, ge=0)
    body_types: List[str] = []
    drive_types: List[str] = []
    colors: List[str] = []
    damage_record: Optional[bool] = None
    paint_status: List[str] = []
    changed_parts_max: Optional[int] = Field(default=None, ge=0)
    heavy_damage: Optional[bool] = None
    seller_types: List[str] = []

    # İki tarih aralığı bağımsızdır: biri emsal havuzunu, diğeri aday ilanları belirler.
    market_window_days: int = Field(default=30, ge=1, le=365)
    market_from: Optional[date] = None
    market_to: Optional[date] = None
    opportunity_window_days: Optional[int] = Field(default=14, ge=1, le=365)
    opportunity_from: Optional[date] = None
    opportunity_to: Optional[date] = None

    urgent: bool = False
    need_sale: bool = False
    below_market: bool = False
    price_dropped: bool = False
    negotiable: bool = False
    bargain: bool = False
    swap: bool = False
    high_investment: bool = False
    cheapest_in_region: bool = False
    only_opportunities: bool = False
    min_score: Optional[float] = Field(default=None, ge=0, le=100)
    min_advantage: Optional[float] = None
    min_confidence: Optional[Literal["Düşük", "Orta", "Yüksek"]] = None

    @model_validator(mode="after")
    def _check_hierarchy(self) -> "ListingFilters":
        if self.districts and not self.cities:
            raise ValueError("İlçe seçmek için önce il seçilmelidir.")
        if self.neighbourhoods and not self.districts:
            raise ValueError("Mahalle seçmek için önce ilçe seçilmelidir.")
        for low, high, label in (
            (self.price_min, self.price_max, "Fiyat"),
            (self.unit_price_min, self.unit_price_max, "Birim fiyat"),
            (self.m2_min, self.m2_max, "m²"),
            (self.km_min, self.km_max, "Kilometre"),
            (self.year_min, self.year_max, "Model yılı"),
        ):
            if low is not None and high is not None and low > high:
                raise ValueError(f"{label} için minimum değer maksimumdan büyük olamaz.")
        return self


class SearchRequest(BaseModel):
    filters: ListingFilters = ListingFilters()
    sort: Literal["score", "advantage", "price_asc", "price_desc", "unit_asc", "newest"] = "score"
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=24, ge=1, le=100)


class LoginRequest(BaseModel):
    email: str = Field(max_length=190)
    password: str = Field(max_length=200)


class ProfileIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    filters: ListingFilters


class JobCreate(BaseModel):
    filters: ListingFilters
    source_keys: List[str] = Field(min_length=1)
    profile_id: Optional[int] = None


class ListingLinksImport(BaseModel):
    urls: List[str] = Field(min_length=1, max_length=20)
    authorized: bool


class ScanSettings(BaseModel):
    request_interval_ms: int = Field(default=1000, ge=250, le=60000)
    max_concurrent: int = Field(default=2, ge=1, le=8)
    timeout_seconds: int = Field(default=20, ge=3, le=120)
    max_retries: int = Field(default=3, ge=0, le=6)
    per_minute: int = Field(default=30, ge=1, le=600)
    per_hour: int = Field(default=600, ge=1, le=20000)


class ProxySettings(BaseModel):
    enabled: bool = False
    scheme: Literal["http", "https"] = "http"
    host: str = Field(default="", max_length=200)
    port: Optional[int] = Field(default=None, ge=1, le=65535)
    username: str = Field(default="", max_length=120)
    authorized_use: bool = False


class AgentSettings(BaseModel):
    min_score: float = Field(default=65, ge=0, le=100)
    min_advantage: float = Field(default=10, ge=0, le=90)
    min_comparables: int = Field(default=5, ge=3, le=100)
    nlp_sensitivity: Literal["dusuk", "orta", "yuksek"] = "orta"
    analysis_depth: Literal["hizli", "standart", "derin"] = "standart"
    min_opportunities: int = Field(default=3, ge=1, le=50)


class NotificationSettings(BaseModel):
    popup: bool = True
    browser: bool = False
    min_score: float = Field(default=80, ge=0, le=100)
    dedupe: bool = True
    dedupe_hours: int = Field(default=72, ge=1, le=720)


class AppSettings(BaseModel):
    scan: ScanSettings = ScanSettings()
    proxy: ProxySettings = ProxySettings()
    agent: AgentSettings = AgentSettings()
    notifications: NotificationSettings = NotificationSettings()


class SettingsUpdate(AppSettings):
    # None: mevcut şifre korunur, "": silinir.
    proxy_password: Optional[str] = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _check_proxy(self) -> "SettingsUpdate":
        if self.proxy.enabled:
            if not self.proxy.host or not self.proxy.port:
                raise ValueError("Aktif proxy için host ve port gereklidir.")
            if not self.proxy.authorized_use:
                raise ValueError("Proxy yalnızca izinli ağ yönlendirmesi onayı verilirse etkinleştirilir.")
        return self


class SourceUpdate(BaseModel):
    enabled: Optional[bool] = None
    base_url: Optional[str] = Field(default=None, max_length=500)
    results_path: Optional[str] = Field(default=None, max_length=80)
    next_cursor_path: Optional[str] = Field(default=None, max_length=80)
    cursor_param: Optional[str] = Field(default=None, max_length=40)
    auth_header: Optional[str] = Field(default=None, max_length=60)
    auth_prefix: Optional[str] = Field(default=None, max_length=30)
    authorized_use: Optional[bool] = None
    # None: mevcut anahtar korunur, "": silinir.
    api_key: Optional[str] = Field(default=None, max_length=500)
