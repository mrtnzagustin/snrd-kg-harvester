from __future__ import annotations

import json
import logging
import os
from datetime import date
from pathlib import Path

import typer
from dotenv import find_dotenv, load_dotenv

from .api_client import ApiConfig, SnrdApiClient
from .cypher_builder import build_constraints_cypher
from .harvester import HarvestConfig, Harvester
from .neo4j_client import Neo4jClient, Neo4jConfig
from .state import JsonStateStore, StateStore

app = typer.Typer(help="SNRD -> Neo4j KG Harvester")

# Load environment from a nearby .env file, keeping any already-exported values.
load_dotenv(find_dotenv(usecwd=True), override=False)


def _parse_date(value: str) -> date:
    return date.fromisoformat(value[:10])


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format='{"ts":"%(asctime)s","level":"%(levelname)s","name":"%(name)s","msg":"%(message)s"}',
    )


def _build_state(mode: str):
    if mode == "json":
        return JsonStateStore(Path("state/checkpoints.json"))
    return StateStore(Path("state/checkpoints.sqlite3"))


def _build_neo4j(enabled: bool) -> Neo4jClient | None:
    if not enabled:
        return None
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "neo4j")
    return Neo4jClient(Neo4jConfig(uri=uri, user=user, password=password))


@app.command("init-neo4j")
def init_neo4j(log_level: str = "INFO") -> None:
    _setup_logging(log_level)
    neo4j = _build_neo4j(True)
    assert neo4j
    neo4j.apply_cypher(build_constraints_cypher())
    neo4j.close()
    typer.echo("Constraints creadas/actualizadas.")


@app.command("harvest")
def harvest(
    from_date: str = typer.Option(..., "--from-date"),
    until_date: str = typer.Option(..., "--until-date"),
    lookfor: str = typer.Option("*", "--lookfor"),
    type_: str = typer.Option("AllFields", "--type"),
    filter: list[str] = typer.Option(None, "--filter"),
    fields: list[str] = typer.Option(None, "--fields"),
    batch_size: int = typer.Option(30, "--batch-size"),
    sort: str = typer.Option("year", "--sort"),
    only_generate: bool = typer.Option(False, "--only-generate"),
    apply: bool = typer.Option(True, "--apply/--no-apply"),
    window_size: str = typer.Option("month", "--window-size"),
    page_start: int = typer.Option(1, "--page-start"),
    page_end: int | None = typer.Option(None, "--page-end"),
    checkpoint_mode: str = typer.Option("sqlite", "--checkpoint-mode"),
    record_strategy: str = typer.Option("auto", "--record-strategy"),
    log_level: str = "INFO",
) -> None:
    _setup_logging(log_level)
    api = SnrdApiClient(ApiConfig(base_url=os.getenv("SNRD_BASE_URL", "https://repositoriosdigitales.mincyt.gob.ar")))
    state = _build_state(checkpoint_mode)
    neo4j = _build_neo4j(enabled=apply and not only_generate)
    cfg = HarvestConfig(
        from_date=_parse_date(from_date),
        until_date=_parse_date(until_date),
        lookfor=lookfor,
        type_=type_,
        filters=filter or [],
        fields=fields or [],
        sort=sort,
        batch_size=batch_size,
        only_generate=only_generate,
        apply=apply,
        window_size=window_size,
        page_start=page_start,
        page_end=page_end,
        record_strategy=record_strategy,
    )
    Harvester(api=api, state=state, neo4j=neo4j).harvest(cfg)
    if neo4j:
        neo4j.close()


@app.command("resume")
def resume(checkpoint_mode: str = typer.Option("sqlite", "--checkpoint-mode"), log_level: str = "INFO") -> None:
    _setup_logging(log_level)
    state = _build_state(checkpoint_mode)
    neo4j = _build_neo4j(True)
    assert neo4j
    unapplied = state.list_unapplied()
    for batch in unapplied:
        path = Path(batch.cypher_path)
        if path.exists():
            cypher = path.read_text(encoding="utf-8")
            neo4j.apply_cypher(cypher)
            batch.applied = True
            state.upsert_batch(batch)
    neo4j.close()
    typer.echo(f"Resume aplicado en {len(unapplied)} batches pendientes")


@app.command("replay")
def replay(
    from_window: str = typer.Option(..., "--from"),
    until_window: str = typer.Option(..., "--until"),
    checkpoint_mode: str = typer.Option("sqlite", "--checkpoint-mode"),
    log_level: str = "INFO",
) -> None:
    _setup_logging(log_level)
    state = _build_state(checkpoint_mode)
    neo4j = _build_neo4j(True)
    assert neo4j
    candidates = state.list_unapplied(from_window, until_window)
    replayed = 0
    for batch in candidates:
        path = Path(batch.cypher_path)
        if not path.exists():
            continue
        neo4j.apply_cypher(path.read_text(encoding="utf-8"))
        batch.applied = True
        state.upsert_batch(batch)
        replayed += 1
    neo4j.close()
    typer.echo(json.dumps({"replayed": replayed, "from": from_window, "until": until_window}))


def main() -> None:
    # Disable Click's Windows glob expansion so lookfor='*' remains literal.
    app(windows_expand_args=False)


if __name__ == "__main__":
    main()
