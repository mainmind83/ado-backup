"""Wiki backup: export wiki metadata and pages as markdown.

Note: the ADO wiki page-content API may return HTTP 404 for empty wikis or
wikis with no published pages. That is treated as a warning, not an error.
"""

import json
import os

import requests

from ado.client import encode_path_segment
from logger import get_logger


def _http_status(exc):
    """Return the HTTP status code of a requests.HTTPError, or None."""
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None) if response is not None else None


def _flatten_pages(page):
    """Collect all page paths from a wiki page tree (excludes the '/' root)."""
    paths = []
    path = page.get("path")
    if path and path != "/":
        paths.append(path)
    for sub in page.get("subPages") or []:
        paths.extend(_flatten_pages(sub))
    return paths


def backup_wikis(client, project, dest_dir):
    """Back up all wikis of a project. Returns the number of wikis backed up."""
    log = get_logger()
    wikis_dir = os.path.join(dest_dir, "wikis")
    os.makedirs(wikis_dir, exist_ok=True)
    count = 0

    data = client.get(
        f"/{encode_path_segment(project)}/_apis/wiki/wikis",
        params={"api-version": "7.1"},
    )

    for wiki in data.get("value", []):
        wiki_id = wiki["id"]
        wiki_name = wiki.get("name") or wiki_id
        wiki_dir = os.path.join(wikis_dir, wiki_name)
        pages_dir = os.path.join(wiki_dir, "pages")
        os.makedirs(pages_dir, exist_ok=True)

        with open(os.path.join(wiki_dir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(wiki, f, indent=2)

        # List the page tree.
        try:
            tree = client.get(
                f"/{encode_path_segment(project)}/_apis/wiki/wikis/{wiki_id}/pages",
                params={"api-version": "7.1", "recursionLevel": "full"},
            )
        except requests.HTTPError as exc:
            if _http_status(exc) == 404:
                log.warning(
                    f"wikis: {project}/{wiki_name} has no pages (404) — "
                    f"empty or unpublished wiki, skipping pages"
                )
                count += 1
                continue
            raise

        page_paths = _flatten_pages(tree)
        saved = 0
        for page_path in page_paths:
            try:
                content = client.get_text(
                    f"/{encode_path_segment(project)}/_apis/wiki/wikis/{wiki_id}/pages",
                    params={"path": page_path, "api-version": "7.1"},
                    headers={"Accept": "text/plain"},
                )
            except requests.HTTPError as exc:
                if _http_status(exc) == 404:
                    log.warning(
                        f"wikis: {project}/{wiki_name} page '{page_path}' "
                        f"returned 404 — empty or unpublished page, skipping"
                    )
                    continue
                raise

            rel = page_path.strip("/")
            file_path = os.path.join(pages_dir, *rel.split("/")) + ".md"
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            saved += 1

        log.info(f"wikis: {project}/{wiki_name} backed up ({saved} pages)")
        count += 1

    return count
