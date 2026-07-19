import httpx


class ApiClient:
    def __init__(self, base_url: str, api_key: str, timeout: float, transport=None):
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"X-API-Key": api_key},
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # --- internal (X-API-Key) ---
    def list_sources(self, is_active: bool = True) -> list[dict]:
        r = self._client.get("/api/internal/sources", params={"is_active": is_active})
        r.raise_for_status()
        return r.json()

    def get_crawl_state(self, source_id: int) -> dict:
        r = self._client.get(f"/api/internal/sources/{source_id}/crawl-state")
        r.raise_for_status()
        return r.json()

    def set_crawl_state(self, source_id: int, last_seen_key: str | None) -> dict:
        r = self._client.post(f"/api/internal/sources/{source_id}/crawl-state",
                              json={"last_seen_key": last_seen_key})
        r.raise_for_status()
        return r.json()

    def submit_offer(self, payload: dict) -> dict:
        r = self._client.post("/api/internal/offers", json=payload)
        r.raise_for_status()
        return r.json()

    def submit_suggestion(self, payload: dict) -> dict:
        r = self._client.post("/api/internal/suggested-sources", json=payload)
        r.raise_for_status()
        return r.json()

    def create_offer_category(self, name: str, slug: str) -> dict:
        r = self._client.post("/api/internal/offer-categories",
                              json={"name": name, "slug": slug})
        r.raise_for_status()
        return r.json()

    def list_bot_accounts(self, platform: str) -> list[dict]:
        r = self._client.get("/api/internal/bot-accounts", params={"platform": platform})
        r.raise_for_status()
        return r.json()

    def set_bot_account_state(self, platform: str, username: str, state: str,
                              cooldown_until=None, note: str | None = None) -> dict:
        r = self._client.post(
            f"/api/internal/bot-accounts/{platform}/{username}/state",
            json={"state": state, "cooldown_until": cooldown_until, "note": note},
        )
        r.raise_for_status()
        return r.json()

    # --- public (no key needed, but harmless to send) ---
    def list_target_categories(self) -> list[dict]:
        r = self._client.get("/api/target-categories")
        r.raise_for_status()
        return r.json()

    def list_offer_categories(self) -> list[dict]:
        r = self._client.get("/api/offer-categories")
        r.raise_for_status()
        return r.json()
