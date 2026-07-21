"""Low-risk security regression checks for authentication and CORS."""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_security.db"
if os.path.exists("test_security.db"):
    os.remove("test_security.db")

from fastapi.testclient import TestClient

from app.main import app


with TestClient(app) as client:
    response = client.get("/api/me")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"

    preflight = client.options(
        "/api/dashboard",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "*"
    assert "access-control-allow-credentials" not in preflight.headers

print("[OK] authentication boundary and wildcard CORS baseline")
