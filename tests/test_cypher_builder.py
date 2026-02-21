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
