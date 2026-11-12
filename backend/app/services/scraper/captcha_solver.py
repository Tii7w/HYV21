# captcha_solver.py
import random
import time
from playwright.sync_api import Page

def solve_press_and_hold(page: Page, timeout: int = 20) -> bool:
    """
    Sahibinden / HUMAN Security tarzı "basılı tut" captcha'sını çözer.
    Gerçekçi mouse down + hold + micro-movement + up yapar.
    """
    # Olası selector'lar (site değişirse burayı güncelle)
    selectors = [
        "#px-captcha",
        "div[id*='captcha']",
        "button:has-text('Basılı tut')",
        "button:has-text('Press and hold')",
        "div.px-captcha-container button",
        "[class*='press-and-hold']",
        "div[role='button']",
    ]

    button = None
    for sel in selectors:
        try:
            button = page.wait_for_selector(sel, timeout=4000, state="visible")
            if button:
                break
        except:
            continue

    if not button:
        print("Press-and-hold butonu bulunamadı")
        return False

    box = button.bounding_box()
    if not box:
        return False

    # Butonun ortasına git
    x = box["x"] + box["width"] / 2
    y = box["y"] + box["height"] / 2

    # İnsan gibi yaklaş
    page.mouse.move(x + random.randint(-15, 15), y + random.randint(-10, 10))
    time.sleep(random.uniform(0.3, 0.7))

    # Basılı tut
    page.mouse.down()

    # Hold süresi (genelde 2.8 – 4.5 saniye arası + jitter)
    hold_time = random.uniform(2.9, 4.6)
    start = time.time()

    while time.time() - start < hold_time:
        # Mikro hareket (jitter) – kritik
        page.mouse.move(
            x + random.uniform(-3.5, 3.5),
            y + random.uniform(-2.5, 2.5)
        )
        time.sleep(random.uniform(0.04, 0.11))

    page.mouse.up()
    time.sleep(random.uniform(1.2, 2.0))

    # Başarı kontrolü (challenge kayboldu mu?)
    try:
        still_there = page.query_selector("#px-captcha, div[id*='captcha']")
        return still_there is None
    except:
        return True