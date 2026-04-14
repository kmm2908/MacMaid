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


from unittest.mock import patch, MagicMock
import cleaner


def test_delete_calls_clean_items_with_matching_paths():
    app = reviewer._make_app(SAMPLE_ITEMS)
    client = app.test_client()

    fake_result = cleaner.CleanResult(moved=1, errors=0, bytes_freed=2_000_000_000)
    with patch("reviewer.cleaner_mod.clean_items", return_value=fake_result) as mock_clean:
        resp = client.post(
            "/api/delete",
            data=json.dumps({"paths": ["/Users/fred/Downloads/big.dmg"]}),
            content_type="application/json",
        )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["moved"] == 1
    assert data["bytes_freed"] == 2_000_000_000
    # Only the matched item was passed to clean_items
    passed_items = mock_clean.call_args[0][0]
    assert len(passed_items) == 1
    assert passed_items[0]["path"] == "/Users/fred/Downloads/big.dmg"


def test_reveal_calls_open_r():
    app = reviewer._make_app(SAMPLE_ITEMS)
    client = app.test_client()

    with patch("subprocess.run") as mock_run:
        resp = client.post(
            "/api/reveal",
            data=json.dumps({"path": "/Users/fred/Downloads/big.dmg"}),
            content_type="application/json",
        )

    assert resp.status_code == 200
    cmd = mock_run.call_args[0][0]
    assert cmd == ["open", "-R", "/Users/fred/Downloads/big.dmg"]


def test_delete_unknown_path_returns_zero_moved():
    app = reviewer._make_app(SAMPLE_ITEMS)
    client = app.test_client()

    fake_result = cleaner.CleanResult(moved=0, errors=0, bytes_freed=0)
    with patch("reviewer.cleaner_mod.clean_items", return_value=fake_result):
        resp = client.post(
            "/api/delete",
            data=json.dumps({"paths": ["/does/not/exist.dmg"]}),
            content_type="application/json",
        )

    assert resp.get_json()["moved"] == 0
