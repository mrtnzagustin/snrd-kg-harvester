from snrd_kg.cypher_builder import build_batch_cypher


def test_build_batch_cypher_contains_merge():
    record = {
        "id": "abc-1",
        "title": "Doc",
        "author": ["Ana Pérez"],
        "instname_str": "CONICET",
        "reponame_str": "Repo X",
        "topic": ["Biología"],
        "url": ["http://x"],
    }
    cypher = build_batch_cypher([record])
    assert "MERGE (p:Publication {id:'abc-1'})" in cypher
    assert "AUTHORED" in cypher


def test_build_batch_cypher_links_relations_to_publication():
    record = {
        "id": "abc-2",
        "title": "Doc",
        "author": ["Ana Perez"],
        "topic": ["Biologia"],
        "url": ["http://x"],
    }
    cypher = build_batch_cypher([record])
    assert "MERGE (p:Publication {id:'abc-2'}) MERGE (a:Author" in cypher
    assert "MERGE (a)-[:AUTHORED]->(p);" in cypher
    assert "MERGE (p:Publication {id:'abc-2'}) MERGE (s:Subject" in cypher
    assert "MERGE (p)-[:HAS_SUBJECT]->(s);" in cypher


def test_build_batch_cypher_supports_vufind_structures():
    record = {
        "id": "abc-3",
        "title": "Doc",
        "authors": {
            "primary": {"Ana Perez": {"role": ["author"]}},
            "secondary": {"Juan Lopez": {"role": ["author"]}},
        },
        "subjects": [["Biologia"], ["Inteligencia Artificial"]],
        "urls": [{"url": "https://example.org/a", "desc": "full text"}],
    }
    cypher = build_batch_cypher([record])
    assert "Ana Perez" in cypher
    assert "Juan Lopez" in cypher
    assert "Biologia" in cypher
    assert "Inteligencia Artificial" in cypher
    assert "https://example.org/a" in cypher
    assert "{'primary'" not in cypher
    assert "['Biologia']" not in cypher


def test_build_batch_cypher_skips_oversized_author_values():
    huge_name = "X" * 20000
    record = {
        "id": "abc-4",
        "title": "Doc",
        "author": [huge_name],
    }
    cypher = build_batch_cypher([record])
    assert "AUTHORED" not in cypher
    assert "name_normalized" not in cypher
