"""Theme settings route tests."""

from __future__ import annotations


def test_theme_settings_get_and_post(app, client, login, base_data):
    """User should be able to open and save theme settings."""
    from app.models import User

    login(base_data["owner_user_id"])

    get_resp = client.get("/theme/settings", follow_redirects=False)
    assert get_resp.status_code == 200

    post_resp = client.post(
        "/theme/settings",
        data={
            "bg_type": "image",
            "bg_image": "bg-main.jpg",
            "theme": "dark",
            "style": "modern",
        },
        follow_redirects=False,
    )
    assert post_resp.status_code == 302
    assert "/theme/settings" in post_resp.headers.get("Location", "")

    with app.app_context():
        user = User.query.get(base_data["owner_user_id"])
        pref = user.get_theme_preference()
        assert pref["bg_type"] == "image"
        assert pref["theme"] == "dark"
        assert pref["style"] == "modern"
