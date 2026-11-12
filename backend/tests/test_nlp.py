from app.agent.nlp import RuleBasedAnalyzer, TfIdfIndex, cosine

nlp = RuleBasedAnalyzer()


def keys(text, sensitivity="orta"):
    return set(nlp.analyze("", text, sensitivity).keys)


def test_urgent_positive():
    result = nlp.analyze("", "Acil satılıktır.")
    assert "urgent" in result.keys
    assert result.score >= 50


def test_urgent_negated():
    result = nlp.analyze("", "Acil satılık değildir.")
    assert "urgent" not in result.keys
    assert any(item["key"] == "urgent" for item in result.negated)
    assert result.score == 0


def test_market_parity_is_not_price_evidence():
    result = nlp.analyze("Piyasa altı daire", "Fiyatlar piyasadaki fiyatlarla aynıdır.")
    assert result.parity
    assert "below_market" not in result.keys


def test_price_drop_amount():
    result = nlp.analyze("", "Fiyatı 500 bin TL düşürdüm, pazarlık payı vardır.")
    assert {"price_drop", "negotiable"} <= set(result.keys)
    assert result.price_drop_amount == 500_000


def test_non_sale_urgency_and_real_estate_word():
    # 'acil çıkış' satış aciliyeti değildir; 'taşınmaz' gayrimenkul demektir, taşınma değil.
    assert keys("Binada acil çıkış merdiveni var. Taşınmaz değerleme raporu mevcut.") == set()


def test_negated_negotiation_and_swap():
    assert keys("Pazarlık yoktur, takas yapılmaz.", "yuksek") == set()


def test_debt_and_moving():
    assert {"need_sale", "moving"} <= keys("Borçtan dolayı satıyorum, yurt dışına taşınacağım.")


def test_sensitivity_changes_score_not_detection():
    low = nlp.analyze("", "Yatırımlık daire.", "dusuk")
    high = nlp.analyze("", "Yatırımlık daire.", "yuksek")
    assert "investment" in low.keys and "investment" in high.keys
    assert low.score == 0 < high.score


def test_risk_negation_stays_inside_clause():
    result = nlp.analyze("", "Daire ipoteklidir. Borcu yoktur.")
    assert any(r["label"] == "İpotek ifadesi" for r in result.risks)
    clean = nlp.analyze("", "Tapuda ipotek yoktur.")
    assert not clean.risks


def test_tfidf_similarity():
    index = TfIdfIndex(["acil satılık daire nilüfer", "acil satılık daire nilüfer", "kiralık ofis kadıköy"])
    a, b, c = (index.vector(d) for d in ("acil satılık daire nilüfer", "acil satılık daire nilüfer", "kiralık ofis kadıköy"))
    assert cosine(a, b) > 0.99 and cosine(a, c) < 0.1
