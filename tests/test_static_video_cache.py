"""Regression tests for shared background-video caching."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from flask import url_for


def test_shared_background_videos_are_versioned_and_cacheable(app, client):
    """Background videos should be cached across pages and refreshed after replacement."""
    with app.test_request_context():
        main_video_url = url_for('static', filename='video/video_main.mp4')
        login_video_url = url_for('static', filename='video/video_login.mp4')

    for video_url in (main_video_url, login_video_url):
        query = parse_qs(urlparse(video_url).query)
        assert query.get('v')

        response = client.get(video_url)
        assert response.status_code == 200
        assert response.cache_control.public is True
        assert response.cache_control.max_age == 7 * 24 * 60 * 60


def test_non_video_static_assets_keep_default_cache_behavior(app, client):
    """The targeted video cache rule must not alter ordinary static resources."""
    response = client.get('/static/css/theme-preferences.css')

    assert response.status_code == 200
    assert response.cache_control.max_age is None
