"""Tests for the wiki backup module, including the empty-wiki 404 handling."""

import logging

import requests

from backup.wikis import backup_wikis


class _FakeHTTPResponse:
    def __init__(self, status_code):
        self.status_code = status_code


def _http_error(status):
    err = requests.HTTPError(f"HTTP {status}")
    err.response = _FakeHTTPResponse(status)
    return err


class FakeClient:
    """Stand-in for ADOClient driven by in-memory fixtures."""

    def __init__(self, wikis, page_tree, page_contents):
        self.wikis = wikis
        self.page_tree = page_tree          # dict or _http_error to raise
        self.page_contents = page_contents  # {path: content or None for 404}

    def get(self, path, params=None):
        if path.endswith("/wikis"):
            return {"value": self.wikis}
        if path.endswith("/pages"):
            if isinstance(self.page_tree, Exception):
                raise self.page_tree
            return self.page_tree
        raise AssertionError(f"unexpected path {path}")

    def get_text(self, path, params=None, headers=None):
        content = self.page_contents.get(params["path"])
        if content is None:
            raise _http_error(404)
        return content


def test_page_hierarchy_is_preserved(tmp_path):
    tree = {
        "path": "/",
        "subPages": [
            {"path": "/Home", "subPages": []},
            {"path": "/Guide", "subPages": [
                {"path": "/Guide/Setup", "subPages": []},
            ]},
        ],
    }
    contents = {
        "/Home": "# Home",
        "/Guide": "# Guide",
        "/Guide/Setup": "# Setup",
    }
    client = FakeClient([{"id": "w1", "name": "Project1.wiki"}], tree, contents)

    count = backup_wikis(client, "Project1", str(tmp_path))

    assert count == 1
    pages = tmp_path / "wikis" / "Project1.wiki" / "pages"
    assert (pages / "Home.md").read_text(encoding="utf-8") == "# Home"
    assert (pages / "Guide.md").is_file()
    # Nested path preserved as a subfolder.
    assert (pages / "Guide" / "Setup.md").read_text(encoding="utf-8") == "# Setup"
    assert (tmp_path / "wikis" / "Project1.wiki" / "meta.json").is_file()


def test_page_content_404_is_warning_not_error(tmp_path, caplog):
    tree = {
        "path": "/",
        "subPages": [
            {"path": "/Home", "subPages": []},
            {"path": "/Draft", "subPages": []},   # no content -> 404
        ],
    }
    contents = {"/Home": "# Home"}  # "/Draft" missing -> get_text raises 404
    client = FakeClient([{"id": "w1", "name": "Project1.wiki"}], tree, contents)

    with caplog.at_level(logging.WARNING, logger="ado_backup"):
        count = backup_wikis(client, "Project1", str(tmp_path))

    # Run completed without raising; the wiki still counts.
    assert count == 1
    pages = tmp_path / "wikis" / "Project1.wiki" / "pages"
    assert (pages / "Home.md").is_file()
    assert not (pages / "Draft.md").exists()

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("404" in r.message and "Draft" in r.message for r in warnings)
    assert not any(r.levelno >= logging.ERROR for r in caplog.records)


def test_empty_wiki_pages_listing_404_is_warning(tmp_path, caplog):
    client = FakeClient(
        [{"id": "w1", "name": "Empty.wiki"}],
        page_tree=_http_error(404),
        page_contents={},
    )

    with caplog.at_level(logging.WARNING, logger="ado_backup"):
        count = backup_wikis(client, "Project1", str(tmp_path))

    assert count == 1
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("404" in r.message for r in warnings)
    assert not any(r.levelno >= logging.ERROR for r in caplog.records)
