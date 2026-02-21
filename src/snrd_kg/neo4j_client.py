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
        with self.driver.session() as session:
            session.run(cypher).consume()
