"""
retry.py
========
Provides a retry decorator with exponential backoff.

Usage:
    from retry import with_retry

    @with_retry
    def my_flaky_function():
        ...

Or wrap a call inline:
    result = with_retry(my_function, arg1, arg2)

Settings come from config.py:
    RETRY_MAX_ATTEMPTS = 3   (total tries including the first)
    RETRY_BASE_DELAY   = 2.0 (seconds; doubles each retry: 2s, 4s, 8s, ...)
"""

import time
import logging
import functools
from config import RETRY_MAX_ATTEMPTS, RETRY_BASE_DELAY

log = logging.getLogger(__name__)


def with_retry(func=None, *, max_attempts: int = None, base_delay: float = None):
    """
    Decorator / wrapper that retries a function on any exception.

    Can be used in two ways:

    As a decorator (uses settings from config.py):
        @with_retry
        def fetch_data(): ...

    As a decorator with custom settings:
        @with_retry(max_attempts=5, base_delay=1.0)
        def fetch_data(): ...
    """
    _max  = max_attempts or RETRY_MAX_ATTEMPTS
    _base = base_delay   or RETRY_BASE_DELAY

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, _max + 1):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:
                    last_exc = e
                    if attempt == _max:
                        log.error(
                            f"  ✗ '{fn.__name__}' failed after {_max} attempts. "
                            f"Last error: {e}"
                        )
                        raise
                    delay = _base * (2 ** (attempt - 1))   # 2s, 4s, 8s, ...
                    log.warning(
                        f"  ⚠ '{fn.__name__}' attempt {attempt}/{_max} failed: {e}. "
                        f"Retrying in {delay:.0f}s..."
                    )
                    time.sleep(delay)
        return wrapper

    # Called as @with_retry (no parentheses) → func is the decorated function
    if func is not None:
        return decorator(func)

    # Called as @with_retry(...) → return the decorator
    return decorator