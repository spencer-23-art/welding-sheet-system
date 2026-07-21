"""Regression test for the unauthenticated big-screen settings panel API."""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_tencent_panel.db"
if os.path.exists("test_tencent_panel.db"):
    os.remove("test_tencent_panel.db")

from fastapi.testclient import TestClient

from app.main import app


def run():
    with TestClient(app) as client:
        response = client.get("/api/tencent/config")
        assert response.status_code == 200, response.text
        payload = response.json()
        assert "access_token" not in payload
        assert payload["has_token"] is False
        print("[OK] Big-screen settings can read token status without exposing the token")


if __name__ == "__main__":
    run()
