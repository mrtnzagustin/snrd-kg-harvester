from __future__ import annotations

import json
from typing import Any

from .normalize import normalize_text

MAX_AUTHOR_LEN = 300
MAX_AUTHOR_NORM_LEN = 300
MAX_SUBJECT_LEN = 400
MAX_SUBJECT_NORM_LEN = 400
MAX_INSTITUTION_LEN = 500
MAX_REPOSITORY_LEN = 500
MAX_URL_LEN = 2000


def _q(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _dedupe_keep_order(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _flatten_text_values(value: Any) -> list[str]:
    out: list[str] = []

    def walk(v: Any) -> None:
        if v is None:
            return
        if isinstance(v, str):
            text = v.strip()
            if text:
                out.append(text)
            return
        if isinstance(v, dict):
            if "url" in v:
                walk(v.get("url"))
                return
            if "value" in v:
                walk(v.get("value"))
                return
            for inner in v.values():
                walk(inner)
            return
        if isinstance(v, (list, tuple, set)):
            for inner in v:
                walk(inner)
            return
        walk(str(v))

    walk(value)
    return out


def _extract_authors(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        names: list[str] = []
        # VuFind shape: {"primary": {"Name": {"role": [...]}},"secondary": {...}}
        for maybe_group in value.values():
            if isinstance(maybe_group, dict):
                for maybe_name in maybe_group.keys():
                    if isinstance(maybe_name, str) and maybe_name.strip():
                        names.append(maybe_name.strip())
        if names:
            return _dedupe_keep_order(names)
    return _dedupe_keep_order(_flatten_text_values(value))


def _extract_subjects(value: Any) -> list[str]:
    return _dedupe_keep_order(_flatten_text_values(value))


def _extract_urls(value: Any) -> list[str]:
    urls: list[str] = []
    for candidate in _flatten_text_values(value):
        if "://" in candidate or candidate.startswith("www."):
            urls.append(candidate)
    return _dedupe_keep_order(urls)


def _first_text(*values: Any) -> str:
    for value in values:
        texts = _flatten_text_values(value)
        if texts:
            return texts[0]
    return ""


def _sanitize_entity_text(value: str, max_len: int) -> str | None:
    text = " ".join(value.strip().split())
    if not text:
        return None
    if len(text) > max_len:
        return None
    return text


def build_constraints_cypher() -> str:
    return "\n".join(
        [
            "CREATE CONSTRAINT publication_id IF NOT EXISTS FOR (p:Publication) REQUIRE p.id IS UNIQUE;",
            "CREATE CONSTRAINT author_norm IF NOT EXISTS FOR (a:Author) REQUIRE a.name_normalized IS UNIQUE;",
            "CREATE CONSTRAINT institution_norm IF NOT EXISTS FOR (i:Institution) REQUIRE i.name_normalized IS UNIQUE;",
            "CREATE CONSTRAINT repository_norm IF NOT EXISTS FOR (r:Repository) REQUIRE r.name_normalized IS UNIQUE;",
            "CREATE CONSTRAINT subject_norm IF NOT EXISTS FOR (s:Subject) REQUIRE s.name_normalized IS UNIQUE;",
            "CREATE CONSTRAINT url_value IF NOT EXISTS FOR (u:URL) REQUIRE u.value IS UNIQUE;",
        ]
    )


def build_publication_cypher(record: dict[str, Any]) -> str:
    rid = str(record.get("id", "")).strip()
    if not rid:
        return ""
    rid_q = _q(rid)
    title = _first_text(record.get("title"), record.get("dc.title"), record.get("title_short"))
    description = _first_text(record.get("description"), record.get("summary"), record.get("dc.description"))
    date = _first_text(record.get("publishDate"), record.get("date"), record.get("dc.date"))
    type_snrd = _first_text(record.get("type_snrd"), record.get("dc.type.snrd"), record.get("format"), record.get("type"))
    language = _first_text(record.get("language"), record.get("languages"), record.get("dc.language"))
    publisher = _first_text(record.get("publisher"), record.get("dc.publisher"))
    rights = _first_text(record.get("rights"), record.get("dc.rights"))
    source = _first_text(record.get("source"), record.get("dc.source"))
    raw_json = json.dumps(record, ensure_ascii=False)
    lines = [
        "MERGE (p:Publication {id:'"
        + rid_q
        + "'}) SET p.title = '"
        + _q(title)
        + "', p.description = '"
        + _q(description)
        + "', p.date = '"
        + _q(date)
        + "', p.type_snrd = '"
        + _q(type_snrd)
        + "', p.language = '"
        + _q(language)
        + "', p.publisher = '"
        + _q(publisher)
        + "', p.rights = '"
        + _q(rights)
        + "', p.source = '"
        + _q(source)
        + "', p.raw_json = '"
        + _q(raw_json)
        + "';",
    ]

    for author in _extract_authors(record.get("author") or record.get("authors") or record.get("dc.creator")):
        author_clean = _sanitize_entity_text(author, MAX_AUTHOR_LEN)
        if not author_clean:
            continue
        norm = normalize_text(author_clean)
        if norm and len(norm) <= MAX_AUTHOR_NORM_LEN:
            lines.append(
                f"MERGE (p:Publication {{id:'{rid_q}'}}) "
                f"MERGE (a:Author {{name_normalized:'{_q(norm)}'}}) SET a.name='{_q(author_clean)}' "
                f"MERGE (a)-[:AUTHORED]->(p);"
            )

    inst = record.get("instname_str") or record.get("institution")
    if inst:
        inst = _sanitize_entity_text(str(inst), MAX_INSTITUTION_LEN)
    if inst:
        inorm = normalize_text(inst)
        lines.append(
            f"MERGE (p:Publication {{id:'{rid_q}'}}) "
            f"MERGE (i:Institution {{name_normalized:'{_q(inorm)}'}}) SET i.name='{_q(inst)}' "
            f"MERGE (p)-[:AFFILIATED_WITH]->(i);"
        )

    repo = record.get("reponame_str") or record.get("repository")
    if repo:
        repo = _sanitize_entity_text(str(repo), MAX_REPOSITORY_LEN)
    if repo:
        rnorm = normalize_text(repo)
        lines.append(
            f"MERGE (p:Publication {{id:'{rid_q}'}}) "
            f"MERGE (r:Repository {{name_normalized:'{_q(rnorm)}'}}) SET r.name='{_q(repo)}' "
            f"MERGE (p)-[:IN_REPOSITORY]->(r);"
        )

    for subject in _extract_subjects(record.get("topic") or record.get("subjects") or record.get("dc.subject")):
        subject_clean = _sanitize_entity_text(subject, MAX_SUBJECT_LEN)
        if not subject_clean:
            continue
        snorm = normalize_text(subject_clean)
        if snorm and len(snorm) <= MAX_SUBJECT_NORM_LEN:
            lines.append(
                f"MERGE (p:Publication {{id:'{rid_q}'}}) "
                f"MERGE (s:Subject {{name_normalized:'{_q(snorm)}'}}) SET s.name='{_q(subject_clean)}' "
                f"MERGE (p)-[:HAS_SUBJECT]->(s);"
            )

    for url in _extract_urls(record.get("url") or record.get("urls") or record.get("fulltext")):
        url_clean = _sanitize_entity_text(url, MAX_URL_LEN)
        if not url_clean:
            continue
        lines.append(
            f"MERGE (p:Publication {{id:'{rid_q}'}}) MERGE (u:URL {{value:'{_q(url_clean)}'}}) MERGE (p)-[:HAS_URL]->(u);"
        )

    return "\n".join(lines)


def build_batch_cypher(records: list[dict[str, Any]]) -> str:
    chunks = [build_publication_cypher(record) for record in records]
    return "\n".join(part for part in chunks if part)
