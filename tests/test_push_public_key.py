"""Regression: /api/push/public-key should never 501.

Before this fix the endpoint returned 501 whenever VAPID wasn't configured,
which filled every user's console with a red error on every page view.
It now returns 200 with key=null and the client hides the opt-in UI.
"""
import os
from unittest.mock import patch


def test_push_public_key_returns_null_when_vapid_unset(client, monkeypatch):
    # Belt and suspenders — ensure VAPID isn't set for this test.
    monkeypatch.setattr("app.VAPID_PUBLIC_KEY", "")
    monkeypatch.setattr("app.VAPID_PRIVATE_KEY", "")
    resp = client.get("/api/push/public-key")
    assert resp.status_code == 200
    assert resp.get_json() == {"key": None}


def test_push_public_key_returns_key_when_vapid_set(client, monkeypatch):
    monkeypatch.setattr("app.VAPID_PUBLIC_KEY", "BVapidPubKey123")
    monkeypatch.setattr("app.VAPID_PRIVATE_KEY", "vapid-priv")
    resp = client.get("/api/push/public-key")
    assert resp.status_code == 200
    assert resp.get_json() == {"key": "BVapidPubKey123"}
