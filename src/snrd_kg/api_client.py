from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import requests

LOGGER = logging.getLogger(__name__)


@dataclass
class ApiConfig:
    base_url: str = "https://repositoriosdigitales.mincyt.gob.ar"
    timeout_s: int = 30
    retries: int = 5
    backoff_s: float = 1.5


class SnrdApiClient:
    def __init__(self, config: ApiConfig):
        self.config = config
        self.session = requests.Session()
        self.api_base = f"{self.config.base_url.rstrip('/')}/vufind/api/v1"

    def _request(self, path: str, params: list[tuple[str, str]]) -> dict[str, Any]:
        url = f"{self.api_base}{path}"
        for attempt in range(1, self.config.retries + 1):
            try:
                response = self.session.get(url, params=params, timeout=self.config.timeout_s)
                if response.status_code == 429:
                    wait = self.config.backoff_s * attempt
                    LOGGER.warning("rate_limited", extra={"attempt": attempt, "wait": wait})
                    time.sleep(wait)
                    continue
                if response.status_code >= 500:
                    wait = self.config.backoff_s * attempt
                    LOGGER.warning("server_error", extra={"attempt": attempt, "wait": wait})
                    time.sleep(wait)
                    continue
                response.raise_for_status()
                return response.json()
            except requests.RequestException:
                if attempt == self.config.retries:
                    raise
                wait = self.config.backoff_s * attempt
                LOGGER.warning("request_retry", extra={"attempt": attempt, "wait": wait})
                time.sleep(wait)
        raise RuntimeError("Retries exhausted")

    def search(
        self,
        *,
        lookfor: str,
        type_: str,
        page: int,
        limit: int,
        filters: list[str],
        fields: list[str],
        facets: list[str],
        sort: str | None,
    ) -> dict[str, Any]:
        params: list[tuple[str, str]] = [
            ("lookfor", lookfor),
            ("type", type_),
            ("page", str(page)),
            ("limit", str(limit)),
        ]
        params.extend(("filter[]", value) for value in filters)
        params.extend(("field[]", value) for value in fields)
        params.extend(("facet[]", value) for value in facets)
        if sort:
            params.append(("sort", sort))
        return self._request("/search", params)

    def record(self, ids: list[str], fields: list[str]) -> dict[str, Any]:
        params: list[tuple[str, str]] = []
        params.extend(("id[]", value) for value in ids)
        params.extend(("field[]", value) for value in fields)
        return self._request("/record", params)

    @staticmethod
    def extract_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
        for key in ("records", "result", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                inner = value.get("records") or value.get("items")
                if isinstance(inner, list):
                    return inner
        return []

    @staticmethod
    def extract_total(payload: dict[str, Any]) -> int | None:
        for key in ("resultCount", "total", "totalRecords", "count"):
            value = payload.get(key)
            if isinstance(value, int):
                return value
        result = payload.get("result")
        if isinstance(result, dict):
            for key in ("resultCount", "total", "totalRecords", "count"):
                value = result.get(key)
                if isinstance(value, int):
                    return value
        return None
