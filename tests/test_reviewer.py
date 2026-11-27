import json
import re
from unittest.mock import patch

import pytest

import cleaner
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


def session_token(client):
    return re.search(r"var TOKEN='([^']+)'", client.get("/").get_data(as_text=True)).group(1)


def auth(client):
    return {"X-MacMaid-Token": session_token(client)}


def test_get_files_returns_items():
    app = reviewer._make_app({"Large & Old Files": SAMPLE_ITEMS})
    client = app.test_client()
    resp = client.get("/api/files")
    assert resp.status_code == 200
    assert resp.get_json() == SAMPLE_ITEMS


def test_index_returns_html():
    app = reviewer._make_app({"Large & Old Files": SAMPLE_ITEMS})
    client = app.test_client()
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"MacMaid" in resp.data
    assert b"<table" in resp.data


def test_delete_calls_clean_items_with_matching_paths(tmp_path):
    app = reviewer._make_app({"Large & Old Files": SAMPLE_ITEMS})
    client = app.test_client()

    fake_result = cleaner.CleanResult(moved=1, errors=0, bytes_freed=2_000_000_000,
                                      moved_paths=["/Users/fred/Downloads/big.dmg"])
    with patch("reviewer.cleaner_mod.clean_items", return_value=fake_result) as mock_clean, \
         patch("reviewer.RESULTS_PATH", tmp_path / "results.json"):
        resp = client.post(
            "/api/delete",
            data=json.dumps({"paths": ["/Users/fred/Downloads/big.dmg"]}),
            content_type="application/json",
            headers=auth(client),
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
    app = reviewer._make_app({"Large & Old Files": SAMPLE_ITEMS})
    client = app.test_client()

    with patch("subprocess.run") as mock_run, patch("os.path.exists", return_value=True):
        resp = client.post(
            "/api/reveal",
            data=json.dumps({"path": "/Users/fred/Downloads/big.dmg"}),
            content_type="application/json",
            headers=auth(client),
        )

    assert resp.status_code == 200
    cmd = mock_run.call_args[0][0]
    assert cmd == ["open", "-R", "/Users/fred/Downloads/big.dmg"]


def test_delete_unknown_path_returns_zero_moved(tmp_path):
    app = reviewer._make_app({"Large & Old Files": SAMPLE_ITEMS})
    client = app.test_client()

    fake_result = cleaner.CleanResult(moved=0, errors=0, bytes_freed=0)
    with patch("reviewer.cleaner_mod.clean_items", return_value=fake_result), \
         patch("reviewer.RESULTS_PATH", tmp_path / "results.json"):
        resp = client.post(
            "/api/delete",
            data=json.dumps({"paths": ["/does/not/exist.dmg"]}),
            content_type="application/json",
            headers=auth(client),
        )

    assert resp.get_json()["moved"] == 0


def test_delete_removes_a_shared_path_from_every_tab(tmp_path):
    app = reviewer._make_app({"Large & Old Files": SAMPLE_ITEMS, "Duplicates": SAMPLE_ITEMS[:1]})
    client = app.test_client()
    gone = SAMPLE_ITEMS[0]["path"]
    fake_result = cleaner.CleanResult(moved=1, moved_paths=[gone])
    with patch("reviewer.cleaner_mod.clean_items", return_value=fake_result), \
         patch("reviewer.RESULTS_PATH", tmp_path / "results.json"):
        client.post("/api/delete", json={"paths": [gone]}, headers=auth(client))

    assert client.get("/api/files/Duplicates").get_json() == []
    assert client.get("/api/files/Large%20%26%20Old%20Files").get_json() == SAMPLE_ITEMS[1:]


FOREIGN_HOSTS = ["evil.example:5888", "localhost.evil.example", "127.0.0.1.evil.example:5888", ""]
LOCAL_HOSTS = ["localhost", "localhost:5888", "127.0.0.1:5888", "[::1]:5888"]
POSTS = ["/api/delete", "/api/reveal", "/api/quit"]


@pytest.mark.parametrize("host", FOREIGN_HOSTS)
def test_a_foreign_host_name_is_refused_even_with_the_token(host):
    client = reviewer._make_app({"Large & Old Files": SAMPLE_ITEMS}).test_client()
    token = session_token(client)

    for url in ("/", "/api/tabs", "/api/files"):
        resp = client.get(url, headers={"Host": host})
        assert resp.status_code == 403, url
        assert b"big.dmg" not in resp.data and token.encode() not in resp.data
    with patch("reviewer.cleaner_mod.clean_items") as clean:
        resp = client.post("/api/delete", json={"paths": [SAMPLE_ITEMS[0]["path"]]},
                           headers={"Host": host, **auth(client)})
    assert resp.status_code == 403
    clean.assert_not_called()


@pytest.mark.parametrize("host", LOCAL_HOSTS)
def test_local_host_names_are_served(host):
    client = reviewer._make_app({"Large & Old Files": SAMPLE_ITEMS}).test_client()
    assert client.get("/api/files", headers={"Host": host}).status_code == 200


@pytest.mark.parametrize("token", [None, "", "wrong", "café"])
@pytest.mark.parametrize("url", POSTS)
def test_actions_without_this_sessions_token_do_nothing(url, token, tmp_path):
    client = reviewer._make_app({"Large & Old Files": SAMPLE_ITEMS}).test_client()
    headers = {} if token is None else {"X-MacMaid-Token": token}
    body = {"paths": [SAMPLE_ITEMS[0]["path"]], "path": SAMPLE_ITEMS[0]["path"]}

    # Thread is patched so an unguarded /api/quit cannot SIGINT the test run.
    with patch("reviewer.cleaner_mod.clean_items", return_value=cleaner.CleanResult()) as clean, \
         patch("reviewer.RESULTS_PATH", tmp_path / "results.json"), \
         patch("reviewer.subprocess.run") as run, \
         patch("reviewer.os.path.exists", return_value=True), \
         patch("reviewer.threading.Thread") as thread:
        resp = client.post(url, json=body, headers=headers)

    assert resp.status_code == 403
    assert "Reload" in resp.get_json()["error"]
    clean.assert_not_called()
    run.assert_not_called()
    thread.assert_not_called()


def test_each_session_has_its_own_token():
    first, second = (reviewer._make_app({"Large & Old Files": SAMPLE_ITEMS}).test_client() for _ in range(2))
    assert session_token(first) != session_token(second)
    with patch("reviewer.threading.Thread") as thread:
        assert second.post("/api/quit", headers=auth(first)).status_code == 403
        assert second.post("/api/quit", headers=auth(second)).status_code == 200
    thread.assert_called_once()


def test_the_page_cannot_be_framed_by_another_site():
    client = reviewer._make_app({"Large & Old Files": SAMPLE_ITEMS}).test_client()
    assert client.get("/").headers["X-Frame-Options"] == "DENY"
    assert client.get("/").headers["Cache-Control"] == "no-store"
