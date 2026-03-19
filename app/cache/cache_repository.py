import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

CACHE_DIR = Path("cache_data")
CACHE_FILE = CACHE_DIR / "investments_cache.json"

CACHE_KEYS = {
    "curves": "curves",
    "inflation": "inflation",
    "br_stocks": "br_stocks",
    "us_stocks": "us_stocks",
    "crypto": "crypto",
    "currencies": "currencies",
}

DEFAULT_TTL_HOURS = 24


class CacheRepository:
    def __init__(self):
        self._ensure_cache_dir()

    def _ensure_cache_dir(self) -> None:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _load_cache(self) -> dict:
        if not CACHE_FILE.exists():
            return {"updated_at": None, "data": {}}
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error("Failed to load cache: %s", e)
            return {"updated_at": None, "data": {}}

    def _save_cache(self, cache: dict) -> None:
        try:
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
        except IOError as e:
            logger.error("Failed to save cache: %s", e)

    def get(self, key: str) -> Optional[dict]:
        cache = self._load_cache()
        data = cache.get("data", {})
        return data.get(key)

    def set(self, key: str, value: Any) -> None:
        cache = self._load_cache()
        now = datetime.now(timezone.utc).isoformat()
        if "data" not in cache:
            cache["data"] = {}
        cache["data"][key] = value
        cache["updated_at"] = now
        self._save_cache(cache)
        logger.debug("Cache updated for key: %s", key)

    def get_all(self) -> dict:
        cache = self._load_cache()
        return cache

    def get_updated_at(self) -> Optional[str]:
        cache = self._load_cache()
        return cache.get("updated_at")

    def is_cache_fresh(self, key: str, max_age_hours: int = DEFAULT_TTL_HOURS) -> bool:
        cache = self._load_cache()
        updated_at = cache.get("updated_at")
        if not updated_at:
            return False
        try:
            updated = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            age_hours = (now - updated).total_seconds() / 3600
            return age_hours < max_age_hours
        except Exception:
            return False

    def clear(self) -> None:
        if CACHE_FILE.exists():
            CACHE_FILE.unlink()
            logger.info("Cache cleared")


cache_repository = CacheRepository()