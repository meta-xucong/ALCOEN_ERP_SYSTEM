"""Upload limit regression tests."""

from __future__ import annotations


def test_max_content_length_matches_deployment_limit(app):
    """Flask should accept uploads up to the same limit as nginx."""
    assert app.config["MAX_CONTENT_LENGTH"] == 50 * 1024 * 1024
