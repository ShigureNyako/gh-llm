from __future__ import annotations

import json
import os
from hashlib import sha256
from pathlib import Path
from typing import cast


class CacheStore:
    def __init__(self, cache_dir: Path | None = None) -> None:
        self._cache_dir = cache_dir or _default_cache_dir()

    def get_json(self, namespace: str, key: str) -> dict[str, object] | None:
        path = self._path(namespace=namespace, key=key)
        if not path.exists():
            return None
        raw: object = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return None
        raw_dict = cast("dict[object, object]", raw)
        return {str(k): v for k, v in raw_dict.items()}

    def set_json(self, namespace: str, key: str, value: dict[str, object]) -> None:
        path = self._path(namespace=namespace, key=key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def _path(self, *, namespace: str, key: str) -> Path:
        safe_namespace = namespace.replace("/", "_")
        digest = sha256(key.encode("utf-8")).hexdigest()
        return self._cache_dir / safe_namespace / f"{digest}.json"


def _default_cache_dir() -> Path:
    xdg_cache = os.environ.get("XDG_CACHE_HOME")
    if xdg_cache:
        return Path(xdg_cache) / "gh-llm"
    return Path.home() / ".cache" / "gh-llm"
