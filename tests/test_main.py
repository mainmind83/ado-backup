"""Tests for the startup version check.

The check is read-only and must never crash startup, so the tests focus on
the three observable branches: up-to-date, outdated, and network failure.
"""

from unittest.mock import MagicMock, patch

import requests

import main


def _resp(tag):
    r = MagicMock()
    r.json.return_value = {"tag_name": tag}
    r.raise_for_status.return_value = None
    return r


def test_up_to_date_logs_single_info_line():
    log = MagicMock()
    with patch("main.requests.get", return_value=_resp(f"v{main.__version__}")):
        main._check_latest_version(log)
    log.info.assert_called_once()
    assert "is the latest release" in log.info.call_args.args[0]
    log.warning.assert_not_called()


def test_newer_release_logs_update_hint_with_url():
    log = MagicMock()
    with patch("main.requests.get", return_value=_resp("v99.0.0")):
        main._check_latest_version(log)
    message = log.info.call_args.args[0]
    assert f"running v{main.__version__}" in message
    assert "latest is v99.0.0" in message
    assert "releases/tag/v99.0.0" in message
    log.warning.assert_not_called()


def test_network_failure_is_swallowed_as_warning():
    log = MagicMock()
    with patch("main.requests.get",
               side_effect=requests.ConnectionError("dns fail")):
        main._check_latest_version(log)
    log.warning.assert_called_once()
    assert "skipped" in log.warning.call_args.args[0]
    log.info.assert_not_called()
