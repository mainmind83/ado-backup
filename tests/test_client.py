"""Tests for the ADO REST client: pagination, rate limiting and retries."""

import requests
import responses

from ado.client import ADOClient, ADOError

BASE = "https://dev.azure.com/testorg"


def _client():
    return ADOClient("testorg", "testpat")


@responses.activate
def test_pagination_is_followed():
    url = f"{BASE}/_apis/git/repositories"
    responses.add(
        responses.GET, url,
        json={"value": [{"id": 1}, {"id": 2}], "count": 2},
        headers={"x-ms-continuationtoken": "page2"},
    )
    responses.add(
        responses.GET, url,
        json={"value": [{"id": 3}], "count": 1},
    )

    data = _client().get("/_apis/git/repositories")

    assert [r["id"] for r in data["value"]] == [1, 2, 3]
    assert data["count"] == 3
    assert len(responses.calls) == 2


@responses.activate
def test_429_triggers_retry(monkeypatch):
    monkeypatch.setattr("ado.client.time.sleep", lambda _s: None)
    url = f"{BASE}/_apis/projects"
    responses.add(responses.GET, url, status=429, headers={"Retry-After": "1"})
    responses.add(responses.GET, url, json={"value": []})

    data = _client().get("/_apis/projects")

    assert data == {"value": []}
    assert len(responses.calls) == 2


@responses.activate
def test_timeout_raises_after_three_attempts(monkeypatch):
    monkeypatch.setattr("ado.client.time.sleep", lambda _s: None)
    url = f"{BASE}/_apis/projects"
    responses.add(responses.GET, url, body=requests.exceptions.Timeout())

    try:
        _client().get("/_apis/projects")
        assert False, "expected ADOError"
    except ADOError:
        pass

    assert len(responses.calls) == 3
