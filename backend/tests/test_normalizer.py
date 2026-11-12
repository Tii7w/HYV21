from datetime import date

from app.agent.normalizer import NormalizationError, classify_category, normalize_record
from app.providers.manual_import import parse_import_file

TODAY = date(2026, 11, 10)


def test_existing_bot_excel_row():
    record = normalize_record(
        {
            "İlan No": "1234", "Telefon No": "0532 111 22 33", "Kategori": "Satılık Daire",
            "İlçe / Mahalle": "Nilüfer / Ataevler Mah.", "İl": "bursa", "Fiyat": "4.250.000 TL", "m² (Brüt)": "120",
            "Oda Sayısı": "3+1", "İlan Tarihi": "06 Kasım 2026", "Açıklama": "Acil! Arayın 0532 111 22 33",
            "Kimden": "Sahibinden (Ahmet Y.)", "Detay Linki": "javascript:alert(1)",
        },
        "manual_import", False, TODAY,
    )
    assert record["city"] == "Bursa" and record["district"] == "Nilüfer" and record["neighbourhood"] == "Ataevler"
    assert record["price"] == 4_250_000 and record["price_per_m2"] == round(4_250_000 / 120, 2)
    assert record["listed_at"] == date(2026, 11, 6) and record["rooms"] == "3+1"
    assert "0532" not in record["description"] and "[telefon gizlendi]" in record["description"]
    assert record["seller_type"] == "Sahibinden"
    assert record["url"] is None  # Yalnızca http(s) bağlantıları kabul edilir.
    assert "Telefon No" not in record


def test_vehicle_row():
    record = normalize_record(
        {"İlan No": "V1", "Kategori": "Otomobil", "Fiyat": "1.050.000 TL", "Marka": "renault", "Seri": "Clio", "Yıl": "2021",
         "KM": "65.000", "Hasar Durumu": "Ağır Hasar Kayıtlı", "İlan Tarihi": "Dün"},
        "demo", True, TODAY,
    )
    assert record["main_category"] == "vasita" and record["km"] == 65_000 and record["year"] == 2021
    assert record["heavy_damage"] is True and record["damage_record"] is True and record["brand"] == "Renault"


def test_category_detection():
    assert classify_category("Satılık Ticari İmarlı Arsa", False)[:2] == ("emlak", "satilik-arsa")
    assert classify_category("Kiralık Residence", False)[1:] == ("kiralik-konut", "Rezidans")
    assert classify_category("Arazi, SUV & Pickup", False)[:2] == ("vasita", "arazi-suv-pickup")


def test_missing_price_rejected():
    try:
        normalize_record({"İlan No": "1", "Fiyat": "Fiyat sorunuz"}, "manual_import", False, TODAY)
    except NormalizationError:
        return
    raise AssertionError("Fiyatsız kayıt kabul edilmemeli")


def test_import_drops_personal_columns():
    rows, dropped = parse_import_file("liste.csv", "İlan No;Fiyat;Telefon No;Satıcı Adı\n1;100 TL;0532;Ali\n".encode("utf-8"))
    assert dropped == ["Telefon No", "Satıcı Adı"]
    assert rows == [{"İlan No": "1", "Fiyat": "100 TL"}]
