from __future__ import annotations

from dataclasses import dataclass

from neo4j import GraphDatabase


@dataclass
class Neo4jConfig:
    uri: str
    user: str
    password: str


class Neo4jClient:
    def __init__(self, config: Neo4jConfig):
        self.driver = GraphDatabase.driver(config.uri, auth=(config.user, config.password))

    def close(self) -> None:
        self.driver.close()

    def apply_cypher(self, cypher: str) -> None:
        if not cypher.strip():
            return
        statements = _split_cypher_statements(cypher)
        if not statements:
            return
        with self.driver.session() as session:
            for statement in statements:
                session.run(statement).consume()


def _split_cypher_statements(cypher: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    in_single = False
    in_double = False
    in_backtick = False
    escaped = False

    for char in cypher:
        if escaped:
            current.append(char)
            escaped = False
            continue

        if char == "\\" and (in_single or in_double):
            current.append(char)
            escaped = True
            continue

        if char == "'" and not in_double and not in_backtick:
            in_single = not in_single
            current.append(char)
            continue

        if char == '"' and not in_single and not in_backtick:
            in_double = not in_double
            current.append(char)
            continue

        if char == "`" and not in_single and not in_double:
            in_backtick = not in_backtick
            current.append(char)
            continue

        if char == ";" and not in_single and not in_double and not in_backtick:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
            continue

        current.append(char)

    tail = "".join(current).strip()
    if tail:
        statements.append(tail)

    return statements
