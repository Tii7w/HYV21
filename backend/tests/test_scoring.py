from datetime import date, timedelta

from app.agent import scorer
from app.agent.market import MarketAnalyzer, PoolItem

TODAY = date(2026, 11, 10)


def test_formula_weights():
    assert scorer.opportunity_score(100, 100, 100) == 100
    assert scorer.opportunity_score(50, 80, 90) == round(50 * 0.4 + 80 * 0.3 + 90 * 0.3, 1)


def test_classification_boundaries():
    assert scorer.classify(90) == "Olağanüstü fırsat"
    assert scorer.classify(89.9) == "Yüksek fırsat"
    assert scorer.classify(80) == "Yüksek fırsat"
    assert scorer.classify(65) == "İncelenmeye değer"
    assert scorer.classify(64.9) == "Normal ilan"


def test_discount_and_subscores_are_normalized():
    assert scorer.discount_percent(100, 83) == 17
    assert scorer.price_advantage_score(-5) == 0
    assert scorer.price_advantage_score(50) == 100
    assert scorer.freshness_score(TODAY, TODAY, 14) == 100
    assert scorer.freshness_score(TODAY - timedelta(days=14), TODAY, 14) == 0
    assert scorer.freshness_score(None, TODAY, 14) == 0


def test_eligibility_never_relaxed():
    ok, _ = scorer.is_eligible(85, 18, 70, False, 8, 65, 10, 5)
    assert ok
    for args, reason in (
        ((85, 18, 70, False, 3, 65, 10, 5), "Yetersiz emsal"),
        ((85, 5, 70, False, 8, 65, 10, 5), "Fiyat avantajı yetersiz"),
        ((85, 50, 70, True, 8, 65, 10, 5), "Şüpheli ilan"),
        ((60, 18, 70, False, 8, 65, 10, 5), "Skor eşiğin altında"),
    ):
        assert scorer.is_eligible(*args) == (False, reason)


def item(i, **overrides):
    base = dict(
        id=i, is_demo=False, main_category="emlak", category="satilik-konut", property_type="Daire", currency="TL",
        city="Bursa", district="Nilüfer", neighbourhood="Ataevler", rooms="2+1", m2=100, age=5, price=5_000_000,
        unit=50_000.0, listed_at=TODAY - timedelta(days=i % 20), brand=None, series=None, model=None, year=None, km=None,
        fuel=None, transmission=None, damage_class="bilinmiyor",
    )
    base.update(overrides)
    return PoolItem(**base)


def analyzer(pool, min_comparables=5):
    return MarketAnalyzer(pool, TODAY, TODAY - timedelta(days=30), TODAY, min_comparables, "derin")


def test_flat_is_not_compared_with_villa():
    villas = [item(i, rooms="5+1", property_type="Villa", m2=300, unit=30_000.0) for i in range(1, 10)]
    flats = [item(i, unit=50_000.0 + i * 100) for i in range(10, 16)]
    subject = item(99, unit=40_000.0)
    result = analyzer(villas + flats + [subject]).find_comparables(subject)
    assert result.sufficient
    assert all(o.rooms == "2+1" and o.property_type == "Daire" for o in result.items)


def test_car_years_are_not_mixed():
    car = dict(main_category="vasita", category="otomobil", property_type=None, rooms=None, m2=None, unit=None, age=None,
               brand="Renault", series="Clio", model="1.5 dCi", fuel="Dizel", transmission="Manuel", km=60_000, damage_class="temiz")
    old = [item(i, **car, year=2010, price=400_000) for i in range(1, 10)]
    new = [item(i, **car, year=2020, price=1_000_000 + i) for i in range(10, 16)]
    subject = item(99, **car, year=2020, price=820_000)
    result = analyzer(old + new + [subject]).find_comparables(subject)
    assert result.sufficient and {o.year for o in result.items} == {2020}


def test_insufficient_sample_lowers_confidence():
    a = analyzer([item(i) for i in range(1, 4)] + [item(99)])
    result = a.find_comparables(item(99))
    assert not result.sufficient and result.best_count == 3
    assert a.confidence(result, 30) <= 20


def test_outliers_trimmed():
    pool = [item(i, unit=50_000.0 + i * 50) for i in range(1, 10)] + [item(50, unit=5_000.0)]
    result = analyzer(pool).find_comparables(item(99, unit=45_000.0))
    assert result.outliers_removed == 1 and result.stats.minimum > 40_000
