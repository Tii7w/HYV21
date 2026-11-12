import pytest

from app.services.scraper.sahibinden_scraper import NotAListingPage, check_results_page


def test_results_page_accepted():
    check_results_page('<table id="searchResultsTable"><tr class="searchResultsItem"></tr></table>')


def test_empty_search_accepted():
    check_results_page("<div>Aramanızla eşleşen ilan bulunamadı.</div>")


@pytest.mark.parametrize(
    "html",
    [
        "",
        "<html><body></body></html>",
        "<html><body><div id='px-captcha'></div>Basılı tutun</body></html>",
        "<html><title>Just a moment...</title></html>",
    ],
)
def test_non_listing_page_is_reported_not_silently_empty(html):
    with pytest.raises(NotAListingPage, match="0 ilan gerçek bir sonuç değil"):
        check_results_page(html)
