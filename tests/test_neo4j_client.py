from snrd_kg.neo4j_client import _split_cypher_statements


def test_split_cypher_statements_multiple_statements():
    cypher = "\n".join(
        [
            "CREATE CONSTRAINT publication_id IF NOT EXISTS FOR (p:Publication) REQUIRE p.id IS UNIQUE;",
            "CREATE CONSTRAINT author_norm IF NOT EXISTS FOR (a:Author) REQUIRE a.name_normalized IS UNIQUE;",
        ]
    )
    statements = _split_cypher_statements(cypher)
    assert len(statements) == 2
    assert statements[0].startswith("CREATE CONSTRAINT publication_id")
    assert statements[1].startswith("CREATE CONSTRAINT author_norm")


def test_split_cypher_statements_keeps_semicolons_inside_strings():
    cypher = "\n".join(
        [
            "MERGE (p:Publication {id:'abc'}) SET p.title='Parte 1; Parte 2';",
            "MERGE (u:URL {value:'https://example.org/a;b'}) MERGE (p)-[:HAS_URL]->(u);",
        ]
    )
    statements = _split_cypher_statements(cypher)
    assert len(statements) == 2
    assert "Parte 1; Parte 2" in statements[0]
    assert "https://example.org/a;b" in statements[1]


def test_split_cypher_statements_supports_query_without_trailing_semicolon():
    cypher = "MERGE (p:Publication {id:'abc'}) RETURN p"
    statements = _split_cypher_statements(cypher)
    assert statements == ["MERGE (p:Publication {id:'abc'}) RETURN p"]
