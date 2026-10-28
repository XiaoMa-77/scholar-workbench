"""Transient failures retry; permanent failures exit immediately."""

import io
import urllib.error
import urllib.request
from unittest.mock import Mock

import pytest

from arxiv_digest.http import get_text


@pytest.mark.parametrize("code", [429, 500, 502, 503, 504])
def test_transient_http_failure_retries(monkeypatch, code):
    request = urllib.request.Request("https://example.org")
    error = urllib.error.HTTPError(request.full_url, code, "temporary", {}, None)
    opener = Mock(side_effect=[error, io.BytesIO(b"payload")])
    sleeper = Mock()
    monkeypatch.setattr("arxiv_digest.http.urllib.request.urlopen", opener)
    monkeypatch.setattr("arxiv_digest.http.time.sleep", sleeper)
    assert get_text(request, 30) == "payload"
    assert opener.call_count == 2
    sleeper.assert_called_once_with(1.5)


def test_permanent_http_failure_is_not_retried(monkeypatch):
    request = urllib.request.Request("https://example.org")
    error = urllib.error.HTTPError(request.full_url, 403, "forbidden", {}, None)
    opener = Mock(side_effect=error)
    monkeypatch.setattr("arxiv_digest.http.urllib.request.urlopen", opener)
    with pytest.raises(urllib.error.HTTPError):
        get_text(request, 30)
    assert opener.call_count == 1


def test_network_failure_has_bounded_retries(monkeypatch):
    opener = Mock(side_effect=urllib.error.URLError("unavailable"))
    monkeypatch.setattr("arxiv_digest.http.urllib.request.urlopen", opener)
    monkeypatch.setattr("arxiv_digest.http.time.sleep", lambda _: None)
    with pytest.raises(urllib.error.URLError):
        get_text(urllib.request.Request("https://example.org"), 30)
    assert opener.call_count == 3
