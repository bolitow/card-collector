"""Écrit le schéma OpenAPI sur la sortie standard : `pnpm gen:api` en tire les types de l'interface."""

import json

from app.main import app

if __name__ == "__main__":
    print(json.dumps(app.openapi(), ensure_ascii=False))
