from pathlib import Path

from snrd_kg.state import BatchState, StateStore


def test_state_upsert_and_get(tmp_path: Path):
    db = tmp_path / "state.sqlite3"
    store = StateStore(db)
    batch = BatchState(
        window="2024-01-01__2024-01-31",
        page=1,
        batch=1,
        ids=["id1", "id2"],
        applied=False,
        cypher_path="out/cypher/a.cypher",
        cypher_hash="h",
        config_hash="c",
    )
    store.upsert_batch(batch)
    loaded = store.get_batch(batch.window, 1, 1)
    assert loaded is not None
    assert loaded.ids == ["id1", "id2"]
