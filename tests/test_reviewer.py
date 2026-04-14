import json
import reviewer


SAMPLE_ITEMS = [
    {
        "path": "/Users/fred/Downloads/big.dmg",
        "label": "big.dmg",
        "size_bytes": 2_000_000_000,
        "meta": {"last_modified": "2025-01-01", "age_days": 365},
    },
    {
        "path": "/Users/fred/Documents/old.zip",
        "label": "old.zip",
        "size_bytes": 500_000_000,
        "meta": {"last_modified": "2024-06-01", "age_days": 600},
    },
]


def test_get_files_returns_items():
    app = reviewer._make_app(SAMPLE_ITEMS)
    client = app.test_client()
    resp = client.get("/api/files")
    assert resp.status_code == 200
    assert resp.get_json() == SAMPLE_ITEMS


def test_index_returns_html():
    app = reviewer._make_app(SAMPLE_ITEMS)
    client = app.test_client()
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"MacMaid" in resp.data
    assert b"<table" in resp.data
