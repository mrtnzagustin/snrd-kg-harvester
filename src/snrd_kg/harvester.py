from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from dateutil.relativedelta import relativedelta

from .api_client import SnrdApiClient
from .cypher_builder import build_batch_cypher
from .neo4j_client import Neo4jClient
from .state import BatchState, StateStore

LOGGER = logging.getLogger(__name__)


@dataclass
class HarvestConfig:
    from_date: date
    until_date: date
    lookfor: str = "*"
    type_: str = "AllFields"
    filters: list[str] | None = None
    fields: list[str] | None = None
    facets: list[str] | None = None
    sort: str | None = "year"
    limit: int = 100
    page_start: int = 1
    page_end: int | None = None
    batch_size: int = 30
    window_size: str = "month"
    only_generate: bool = False
    apply: bool = True
    out_dir: Path = Path("out")
    state_db: Path = Path("state/checkpoints.sqlite3")
    record_strategy: str = "auto"


class Harvester:
    def __init__(self, api: SnrdApiClient, state: StateStore, neo4j: Neo4jClient | None = None):
        self.api = api
        self.state = state
        self.neo4j = neo4j
        self._warned_year_fallback = False

    def _iter_windows(self, start: date, end: date, mode: str) -> Iterable[tuple[date, date]]:
        current = start
        while current <= end:
            if mode == "day":
                wnd_end = min(current, end)
                yield current, wnd_end
                current += timedelta(days=1)
            elif mode == "year":
                wnd_end = min(date(current.year, 12, 31), end)
                yield current, wnd_end
                current = wnd_end + timedelta(days=1)
            else:
                month_end = (current + relativedelta(day=31))
                wnd_end = min(month_end, end)
                yield current, wnd_end
                current = wnd_end + timedelta(days=1)

    @staticmethod
    def _window_label(start: date, end: date) -> str:
        return f"{start.isoformat()}__{end.isoformat()}"

    @staticmethod
    def _date_filter_candidates(start: date, end: date) -> list[str]:
        return [
            f"publishDate:[{start.isoformat()} TO {end.isoformat()}]",
            f"publishDate:[{start.year}-01-01 TO {end.year}-12-31]",
            f"publishDate:{start.year}",
        ]

    def _discover_filter(self, cfg: HarvestConfig, page: int, start: date, end: date) -> tuple[str, dict[str, Any]]:
        last_filter: str | None = None
        last_payload: dict[str, Any] | None = None
        last_exc: Exception | None = None
        for date_filter in self._date_filter_candidates(start, end):
            last_filter = date_filter
            try:
                payload = self.api.search(
                    lookfor=cfg.lookfor,
                    type_=cfg.type_,
                    page=page,
                    limit=cfg.limit,
                    filters=(cfg.filters or []) + [date_filter],
                    fields=cfg.fields or [],
                    facets=cfg.facets or [],
                    sort=cfg.sort,
                )
                last_payload = payload
                records = self.api.extract_records(payload)
                total = self.api.extract_total(payload)
                LOGGER.debug(
                    "filter_probe page=%s filter=%s records=%s total=%s",
                    page,
                    date_filter,
                    len(records),
                    total,
                )
                if records or (isinstance(total, int) and total > 0):
                    return date_filter, payload
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                LOGGER.warning("date_filter_failed filter=%s", date_filter)
        if last_payload is not None and last_filter is not None:
            return last_filter, last_payload
        if last_exc:
            raise last_exc
        raise RuntimeError("Unable to discover date filter")

    def _extract_ids(self, records: list[dict[str, Any]]) -> list[str]:
        ids = []
        for rec in records:
            rid = rec.get("id")
            if rid:
                ids.append(str(rid))
        return ids

    def _should_use_record(self, cfg: HarvestConfig, records: list[dict[str, Any]]) -> bool:
        if cfg.record_strategy == "record":
            return True
        if cfg.record_strategy == "search":
            return False
        required = ("description", "author", "authors", "topic", "subjects")
        return not all(any(k in rec for k in required) for rec in records)

    def harvest(self, cfg: HarvestConfig) -> None:
        config_snapshot = {
            "lookfor": cfg.lookfor,
            "type": cfg.type_,
            "filters": cfg.filters,
            "fields": cfg.fields,
            "facets": cfg.facets,
            "sort": cfg.sort,
            "batch_size": cfg.batch_size,
            "window_size": cfg.window_size,
        }
        config_hash = StateStore.hash_config(config_snapshot)

        for wnd_start, wnd_end in self._iter_windows(cfg.from_date, cfg.until_date, cfg.window_size):
            window = self._window_label(wnd_start, wnd_end)
            page = cfg.page_start
            while True:
                if cfg.page_end is not None and page > cfg.page_end:
                    break
                date_filter, payload = self._discover_filter(cfg, page, wnd_start, wnd_end)
                if (
                    not self._warned_year_fallback
                    and cfg.window_size != "year"
                    and date_filter.startswith("publishDate:")
                    and date_filter.removeprefix("publishDate:").isdigit()
                ):
                    LOGGER.warning(
                        "date filter fallback reached year granularity (%s); "
                        "for less duplicate work use --window-size year",
                        date_filter,
                    )
                    self._warned_year_fallback = True
                records = self.api.extract_records(payload)
                LOGGER.info(
                    "window=%s page=%s filter=%s records=%s total=%s",
                    window,
                    page,
                    date_filter,
                    len(records),
                    self.api.extract_total(payload),
                )
                if not records:
                    break
                ids = self._extract_ids(records)
                if not ids:
                    break

                detailed_records = records
                if self._should_use_record(cfg, records):
                    detailed_records = []
                    for ix, id_batch in enumerate(_chunks(ids, cfg.batch_size), start=1):
                        existing = self.state.get_batch(window, page, ix)
                        if existing and Path(existing.cypher_path).exists():
                            if existing.applied or cfg.only_generate:
                                continue
                            if cfg.apply and self.neo4j:
                                self.neo4j.apply_cypher(Path(existing.cypher_path).read_text(encoding="utf-8"))
                                existing.applied = True
                                self.state.upsert_batch(existing)
                            continue

                        details_payload = self.api.record(id_batch, cfg.fields or [])
                        detail_records = self.api.extract_records(details_payload) or [
                            v for v in details_payload.values() if isinstance(v, dict) and "id" in v
                        ]
                        if not detail_records:
                            detail_records = [r for r in records if str(r.get("id")) in set(id_batch)]
                        cypher = build_batch_cypher(detail_records)
                        cypher_path = cfg.out_dir / "cypher" / window / str(page) / f"batch_{ix}.cypher"
                        cypher_path.parent.mkdir(parents=True, exist_ok=True)
                        cypher_path.write_text(cypher, encoding="utf-8")
                        cypher_hash = StateStore.hash_text(cypher)
                        applied = False
                        if cfg.apply and not cfg.only_generate and self.neo4j:
                            self.neo4j.apply_cypher(cypher)
                            applied = True
                        self.state.upsert_batch(
                            BatchState(
                                window=window,
                                page=page,
                                batch=ix,
                                ids=id_batch,
                                applied=applied,
                                cypher_path=str(cypher_path),
                                cypher_hash=cypher_hash,
                                config_hash=config_hash,
                            )
                        )
                        detailed_records.extend(detail_records)
                else:
                    for ix, rec_batch in enumerate(_chunks(detailed_records, cfg.batch_size), start=1):
                        id_batch = self._extract_ids(rec_batch)
                        cypher = build_batch_cypher(rec_batch)
                        cypher_path = cfg.out_dir / "cypher" / window / str(page) / f"batch_{ix}.cypher"
                        cypher_path.parent.mkdir(parents=True, exist_ok=True)
                        cypher_path.write_text(cypher, encoding="utf-8")
                        applied = False
                        if cfg.apply and not cfg.only_generate and self.neo4j:
                            self.neo4j.apply_cypher(cypher)
                            applied = True
                        self.state.upsert_batch(
                            BatchState(
                                window=window,
                                page=page,
                                batch=ix,
                                ids=id_batch,
                                applied=applied,
                                cypher_path=str(cypher_path),
                                cypher_hash=StateStore.hash_text(cypher),
                                config_hash=config_hash,
                            )
                        )

                manifest_path = cfg.out_dir / "manifests" / window / f"{page}.json"
                manifest_path.parent.mkdir(parents=True, exist_ok=True)
                manifest = {
                    "window": window,
                    "page": page,
                    "timestamp": datetime.utcnow().isoformat(),
                    "date_filter": date_filter,
                    "total": self.api.extract_total(payload),
                    "ids": ids,
                    "count": len(ids),
                }
                manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

                if len(records) < cfg.limit:
                    break
                page += 1


def _chunks(seq: list[Any], size: int) -> Iterable[list[Any]]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]
