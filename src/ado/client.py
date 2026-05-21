"""Thin Azure DevOps REST API client over requests.Session.

Handles authentication, retries with exponential backoff, HTTP 429 rate
limiting and continuation-token pagination.
"""

import time

import requests

from logger import get_logger

DEFAULT_TIMEOUT = 30
DEFAULT_MAX_RETRIES = 3


class ADOError(Exception):
    """Generic Azure DevOps API error."""


class ADOAuthError(ADOError):
    """Raised on HTTP 401 — authentication failed."""


class ADOClient:
    """Minimal ADO API client. Use get() for JSON, get_text() for raw text."""

    def __init__(self, organization, pat, base_url=None,
                 timeout=DEFAULT_TIMEOUT, max_retries=DEFAULT_MAX_RETRIES):
        self.organization = organization
        self.base_url = (base_url or f"https://dev.azure.com/{organization}").rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.log = get_logger()

        self.session = requests.Session()
        # ADO PAT auth: HTTP Basic with empty username, PAT as password.
        self.session.auth = ("", pat)
        self.session.headers.update({"Accept": "application/json"})

    def _full_url(self, path):
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self.base_url}{path}"

    def _request(self, path, params=None, headers=None):
        """Perform a GET with retry/backoff. Returns the requests.Response."""
        url = self._full_url(path)
        last_exc = None

        for attempt in range(self.max_retries):
            is_last = attempt == self.max_retries - 1
            try:
                resp = self.session.get(
                    url, params=params, headers=headers, timeout=self.timeout
                )
            except (requests.Timeout, requests.ConnectionError) as exc:
                last_exc = exc
                self.log.warning(
                    f"request to {url} failed ({exc.__class__.__name__}), "
                    f"attempt {attempt + 1}/{self.max_retries}"
                )
                if not is_last:
                    time.sleep(2 ** attempt)
                continue

            if resp.status_code == 401:
                raise ADOAuthError(f"authentication failed (401) for {url}")

            if resp.status_code == 429:
                if is_last:
                    raise ADOError(
                        f"rate limited (429) after {self.max_retries} attempts: {url}"
                    )
                retry_after = resp.headers.get("Retry-After")
                delay = int(retry_after) if retry_after else 2 ** attempt
                self.log.warning(f"rate limited (429) for {url}, retrying in {delay}s")
                time.sleep(delay)
                continue

            if resp.status_code >= 500:
                if is_last:
                    resp.raise_for_status()
                self.log.warning(
                    f"server error {resp.status_code} for {url}, retrying"
                )
                time.sleep(2 ** attempt)
                continue

            # 2xx/3xx/4xx (except 401/429): raise for non-success, else return.
            resp.raise_for_status()
            return resp

        raise ADOError(
            f"request to {url} failed after {self.max_retries} attempts"
        ) from last_exc

    def get(self, path, params=None):
        """GET a JSON resource. Auto-follows continuation-token pagination."""
        params = dict(params or {})
        resp = self._request(path, params)
        data = resp.json()

        token = resp.headers.get("x-ms-continuationtoken")
        if token and isinstance(data, dict) and "value" in data:
            values = list(data["value"])
            while token:
                page_params = dict(params)
                page_params["continuationToken"] = token
                resp = self._request(path, page_params)
                page = resp.json()
                values.extend(page.get("value", []))
                token = resp.headers.get("x-ms-continuationtoken")
            data = dict(data)
            data["value"] = values
            data["count"] = len(values)

        return data

    def get_text(self, path, params=None, headers=None):
        """GET a resource and return the raw response body as text."""
        resp = self._request(path, params, headers)
        return resp.text
