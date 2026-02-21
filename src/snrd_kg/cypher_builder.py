from __future__ import annotations

import json
from typing import Any

from .normalize import normalize_text


def _q(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(x) for x in value if x]
    return [str(value)]


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
    title = str(record.get("title") or record.get("title_short") or "")
    description = str(record.get("description") or record.get("summary") or "")
    date = str(record.get("publishDate") or record.get("date") or "")
    type_snrd = str(record.get("format") or record.get("type") or "")
    language = str(record.get("language") or "")
    publisher = str(record.get("publisher") or "")
    rights = str(record.get("rights") or "")
    source = str(record.get("source") or "")
    raw_json = json.dumps(record, ensure_ascii=False)
    lines = [
        f"MERGE (p:Publication {{id:'{_q(rid)}'}})",
        "SET p.title = '" + _q(title) + "', p.description = '" + _q(description) + "', "
        "p.date = '" + _q(date) + "', p.type_snrd = '" + _q(type_snrd) + "', "
        "p.language = '" + _q(language) + "', p.publisher = '" + _q(publisher) + "', "
        "p.rights = '" + _q(rights) + "', p.source = '" + _q(source) + "', "
        "p.raw_json = '" + _q(raw_json) + "';",
    ]

    for author in _as_list(record.get("author") or record.get("authors")):
        norm = normalize_text(author)
        if norm:
            lines.append(
                f"MERGE (a:Author {{name_normalized:'{_q(norm)}'}}) SET a.name='{_q(author)}' "
                f"MERGE (a)-[:AUTHORED]->(p);"
            )

    inst = record.get("instname_str") or record.get("institution")
    if inst:
        inst = str(inst)
        inorm = normalize_text(inst)
        lines.append(
            f"MERGE (i:Institution {{name_normalized:'{_q(inorm)}'}}) SET i.name='{_q(inst)}' "
            f"MERGE (p)-[:AFFILIATED_WITH]->(i);"
        )

    repo = record.get("reponame_str") or record.get("repository")
    if repo:
        repo = str(repo)
        rnorm = normalize_text(repo)
        lines.append(
            f"MERGE (r:Repository {{name_normalized:'{_q(rnorm)}'}}) SET r.name='{_q(repo)}' "
            f"MERGE (p)-[:IN_REPOSITORY]->(r);"
        )

    for subject in _as_list(record.get("topic") or record.get("subjects")):
        snorm = normalize_text(subject)
        if snorm:
            lines.append(
                f"MERGE (s:Subject {{name_normalized:'{_q(snorm)}'}}) SET s.name='{_q(subject)}' "
                f"MERGE (p)-[:HAS_SUBJECT]->(s);"
            )

    for url in _as_list(record.get("url") or record.get("urls") or record.get("fulltext")):
        lines.append(f"MERGE (u:URL {{value:'{_q(url)}'}}) MERGE (p)-[:HAS_URL]->(u);")

    return "\n".join(lines)


def build_batch_cypher(records: list[dict[str, Any]]) -> str:
    chunks = [build_publication_cypher(record) for record in records]
    return "\n".join(part for part in chunks if part)
