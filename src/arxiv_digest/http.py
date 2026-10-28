"""Shared bounded retries for read-only academic API requests."""

import time
import urllib.error
import urllib.request

RETRY_STATUS = {429, 500, 502, 503, 504}


def get_text(request: urllib.request.Request, timeout: int, retries: int = 2) -> str:
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            if error.code not in RETRY_STATUS or attempt == retries:
                raise
        except urllib.error.URLError:
            if attempt == retries:
                raise
        time.sleep(1.5 * (2 ** attempt))
    raise RuntimeError("unreachable retry state")
