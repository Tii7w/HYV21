# humanize.py
import random
import time
import asyncio
from functools import wraps

def human_delay(min_s=1.4, max_s=4.2):
    time.sleep(random.uniform(min_s, max_s))

async def async_human_delay(min_s=1.4, max_s=4.2):
    await asyncio.sleep(random.uniform(min_s, max_s))

def exponential_backoff_retry(max_retries=4, base_delay=2.0):
    """429 ve 5xx için üstel bekleme"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt == max_retries - 1:
                        raise
                    delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                    print(f"Retry {attempt+1}/{max_retries} - {delay:.1f}s bekleniyor... ({e})")
                    time.sleep(delay)
            raise last_exception
        return wrapper
    return decorator