"""Freeze the public HTTP contract while internal code is refactored."""
from app.main import app


EXPECTED = {
    ("GET", "/"),
    ("GET", "/health"),
    ("GET", "/api/heat-treatment-analysis"),
    ("GET", "/api/dashboard"),
    ("GET", "/api/documents"),
    ("POST", "/api/documents"),
    ("PATCH", "/api/documents/{doc_id}"),
    ("DELETE", "/api/documents/{doc_id}"),
    ("POST", "/api/documents/{doc_id}/restore"),
    ("GET", "/api/latest/ndt"),
    ("GET", "/api/latest/welding"),
    ("POST", "/api/login"),
    ("GET", "/api/me"),
    ("GET", "/api/meta/projects"),
    ("GET", "/api/meta/zones"),
    ("GET", "/api/ndt/ng"),
    ("GET", "/api/permissions"),
    ("GET", "/api/pipeline-quality-daily"),
    ("GET", "/api/pipeline/{pipeline_no}"),
    ("GET", "/api/pipelines"),
    ("GET", "/api/quality-analysis"),
    ("POST", "/api/refresh"),
    ("POST", "/api/register"),
    ("GET", "/api/roles"),
    ("POST", "/api/roles"),
    ("GET", "/api/sheets/public"),
    ("GET", "/api/sheets/{doc_id}"),
    ("POST", "/api/sheets/{doc_id}/sync"),
    ("GET", "/api/tencent/config"),
    ("PUT", "/api/tencent/config"),
    ("POST", "/api/tencent/poll/set"),
    ("GET", "/api/tencent/poll/status"),
    ("POST", "/api/tencent/poll/trigger"),
    ("POST", "/api/tencent/sync"),
    ("POST", "/api/tencent/webhook"),
    ("GET", "/api/users"),
    ("POST", "/api/users"),
    ("PATCH", "/api/users/{user_id}"),
    ("DELETE", "/api/users/{user_id}"),
}

schema = app.openapi()
actual = {
    (method.upper(), path)
    for path, operations in schema["paths"].items()
    for method in operations
}
assert actual == EXPECTED, f"API contract changed: missing={EXPECTED - actual}, added={actual - EXPECTED}"
assert any(getattr(route, "path", None) == "/ws/dashboard" for route in app.routes)

print(f"[OK] {len(EXPECTED)} HTTP operations and dashboard WebSocket contract")
