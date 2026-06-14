#!/usr/bin/env bash
# Regenerate web/src/lib/api/schema.d.ts from the live FastAPI OpenAPI spec.
# Mirrors the CI drift check (.github/workflows/ci.yml). Run by pre-commit and
# manually via `npm run generate:api` is the server-based alternative.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

OPENAPI_JSON="$(mktemp -t openapi.XXXXXX.json)"
trap 'rm -f "$OPENAPI_JSON"' EXIT

JWT_SECRET="${JWT_SECRET:-ci-test-secret-must-be-at-least-32bytes!!}" \
uv run python - <<'PY' > "$OPENAPI_JSON"
import json, os
from app.main.config.settings import (
    AppSettings, AuthSettings, DatabaseSettings,
    ObservabilitySettings, RedisSettings,
)
from app.main.api.app_factory import make_app

app = make_app(
    app_settings=AppSettings(debug=False),
    database_settings=DatabaseSettings(database_url="postgresql+asyncpg://x:y@localhost/z"),
    redis_settings=RedisSettings(redis_url="redis://localhost:6379/0"),
    auth_settings=AuthSettings(jwt_secret=os.environ["JWT_SECRET"], cookie_secure=True),
    observability_settings=ObservabilitySettings(log_format="console", otel_enabled=False),
)
print(json.dumps(app.openapi()))
PY

cd web
npx --no-install openapi-typescript "$OPENAPI_JSON" --output src/lib/api/schema.d.ts
