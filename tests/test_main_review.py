import json
import signal
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
import main


def test_save_results_writes_json(tmp_path):
    results = [{"category": "Large & Old Files", "items": [], "risk": "review"}]
    fake_path = tmp_path / "results.json"
    with patch.object(main, "RESULTS_PATH", fake_path):
        main.save_results(results)
    assert json.loads(fake_path.read_text()) == results


def test_save_results_overwrites_existing(tmp_path):
    fake_path = tmp_path / "results.json"
    fake_path.write_text('{"old": true}')
    results = [{"category": "caches", "items": []}]
    with patch.object(main, "RESULTS_PATH", fake_path):
        main.save_results(results)
    assert json.loads(fake_path.read_text()) == results


def test_review_exits_if_no_results_file(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "RESULTS_PATH", tmp_path / "nonexistent.json")
    monkeypatch.setattr(sys, "argv", ["main.py", "--review"])
    with pytest.raises(SystemExit):
        main.main()


def test_review_calls_reviewer_start_with_large_files_items(tmp_path, monkeypatch):
    items = [{"path": "/tmp/a.dmg", "label": "a.dmg", "size_bytes": 1_000_000_000, "meta": {}}]
    results = [
        {"category": "Large & Old Files", "risk": "review", "items": items,
         "total_size_bytes": 1_000_000_000, "suggestion": "", "action": "trash"},
        {"category": "caches", "risk": "safe", "items": [], "total_size_bytes": 0,
         "suggestion": "", "action": "trash"},
    ]
    fake_path = tmp_path / "results.json"
    fake_path.write_text(json.dumps(results))

    monkeypatch.setattr(main, "RESULTS_PATH", fake_path)
    monkeypatch.setattr(sys, "argv", ["main.py", "--review"])

    started = []
    with patch("main.reviewer.start", side_effect=lambda i: started.append(i)):
        with pytest.raises(SystemExit):
            main.main()

    assert len(started) == 1
    assert started[0] == {"Large & Old Files": items}


def test_review_exits_if_large_files_empty(tmp_path, monkeypatch):
    results = [{"category": "Large & Old Files", "risk": "review", "items": [],
                "total_size_bytes": 0, "suggestion": "", "action": "trash"}]
    fake_path = tmp_path / "results.json"
    fake_path.write_text(json.dumps(results))

    monkeypatch.setattr(main, "RESULTS_PATH", fake_path)
    monkeypatch.setattr(sys, "argv", ["main.py", "--review"])
    with pytest.raises(SystemExit):
        main.main()


def test_unattended_mode_saves_results(tmp_path, monkeypatch):
    """save_results() is called during unattended_mode()."""
    monkeypatch.setattr(main, "RESULTS_PATH", tmp_path / "results.json")
    results = [{"category": "caches", "risk": "safe", "items": [], "total_size_bytes": 0,
                "suggestion": "", "action": "trash"}]
    with patch("main.reporter.print_unattended_report", return_value="report"), \
         patch("main.history.record"), \
         patch("main.emailer.send_report"):
        main.unattended_mode(results, False, "", no_email=True)

    assert (tmp_path / "results.json").exists()
    saved = json.loads((tmp_path / "results.json").read_text())
    assert saved == results


def test_unattended_email_includes_review_link_when_large_files_present(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "RESULTS_PATH", tmp_path / "results.json")
    items = [{"path": "/tmp/a.dmg", "label": "a.dmg", "size_bytes": 1_000_000_000, "meta": {}}]
    results = [
        {"category": "Large & Old Files", "risk": "review", "items": items,
         "total_size_bytes": 1_000_000_000, "suggestion": "", "action": "trash"},
    ]
    sent_bodies = []
    with patch("main.reporter.print_unattended_report", return_value="report text"), \
         patch("main.history.record"), \
         patch("main._start_review_server"), \
         patch("main.emailer.send_report", side_effect=lambda s, b, t, **kw: sent_bodies.append(b)):
        main.unattended_mode(results, False, "test@example.com", no_email=False)

    assert len(sent_bodies) == 1
    assert f"Review files: http://localhost:{main.reviewer.REVIEW_PORT}" in sent_bodies[0]


def test_unattended_email_no_review_link_when_no_large_files(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "RESULTS_PATH", tmp_path / "results.json")
    results = [{"category": "caches", "risk": "safe", "items": [], "total_size_bytes": 0,
                "suggestion": "", "action": "trash"}]
    sent_bodies = []
    with patch("main.reporter.print_unattended_report", return_value="report text"), \
         patch("main.history.record"), \
         patch("main.emailer.send_report", side_effect=lambda s, b, t, **kw: sent_bodies.append(b)):
        main.unattended_mode(results, False, "test@example.com", no_email=False)

    assert len(sent_bodies) == 1
    assert "localhost" not in sent_bodies[0]


def test_unattended_dry_run_does_not_save_results(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "RESULTS_PATH", tmp_path / "results.json")
    results = [{"category": "caches", "risk": "safe", "items": [], "total_size_bytes": 0,
                "suggestion": "", "action": "trash"}]
    with patch("main.reporter.print_unattended_report", return_value="report"), \
         patch("main.history.record"), \
         patch("main.emailer.send_report"):
        main.unattended_mode(results, False, "", no_email=True, dry_run=True)

    assert not (tmp_path / "results.json").exists()


def _result(category: str, risk: str, action: str = "trash", items: int = 1) -> dict:
    return {"category": category, "risk": risk, "action": action,
            "items": [{"path": f"/tmp/{category}", "label": category, "size_bytes": 1,
                       "meta": {}}][:items]}


def test_every_trashable_review_category_with_items_is_offered_for_review():
    results = [
        _result("Large & Old Files", "review"),
        _result("Mail Store", "review"),
        _result("iOS Backups", "review"),
        _result("A Future Module", "review"),
        _result("Duplicates", "review", items=0),
        _result("Caches", "safe"),
        _result("Login Items", "inform-only", action="none"),
    ]
    assert list(main._load_review_categories(results)) == [
        "Large & Old Files", "Mail Store", "iOS Backups", "A Future Module"]


@pytest.mark.parametrize("action", ["empty-trash", "none"])
def test_review_category_the_page_cannot_act_on_correctly_is_not_offered(action):
    # The page can only move to Trash, so any other action must stay out of it.
    assert main._load_review_categories([_result("Large & Old Files", "review", action=action)]) == {}


def test_real_mail_and_ios_scan_results_reach_the_review_page(tmp_path, monkeypatch):
    for module, attr in ((main.mail, "MAIL_DIR"), (main.ios_backups, "BACKUP_DIR")):
        folder = tmp_path / attr / "one"
        folder.mkdir(parents=True)
        (folder / "x.bin").write_bytes(b"x")
        monkeypatch.setattr(module, attr, str(tmp_path / attr))
    cats = main._load_review_categories([main.mail.scan(), main.ios_backups.scan()])
    assert list(cats) == ["Mail Store", "iOS Backups"]


OURS = f"/usr/bin/python3 {Path(main.__file__).resolve()} --serve"


def _fake_port(holders: dict[str, str]):
    """subprocess.run and os.kill over a pretend port: {pid: command line}."""
    def run(cmd, **_kwargs):
        if cmd[0] == "lsof":
            assert cmd == ["lsof", "-ti", f"tcp:{main.reviewer.REVIEW_PORT}", "-sTCP:LISTEN"]
            return MagicMock(stdout="".join(f"{pid}\n" for pid in holders))
        assert cmd[0] == "ps"
        return MagicMock(stdout=holders[cmd[-1]] + "\n")

    def kill(pid, _sig):
        del holders[str(pid)]

    return run, kill


def _start(holders: dict[str, str], exited: int | None = None):
    run, kill = _fake_port(holders)
    with patch("main.subprocess.run", side_effect=run), patch("main.os.kill", side_effect=kill) as killed, \
         patch("main.subprocess.Popen") as popen, patch("main.urllib.request.urlopen") as urlopen, \
         patch("main.time.sleep"):
        popen.return_value.poll.return_value = exited
        started = main._start_review_server()
    return started, killed, popen, urlopen


def test_an_earlier_review_server_is_asked_to_stop_and_replaced() -> None:
    started, killed, popen, urlopen = _start({"4242": OURS})
    assert started is True
    killed.assert_called_once_with(4242, signal.SIGTERM)
    popen.assert_called_once()
    assert not any("/api/quit" in str(c) for c in urlopen.call_args_list)


def test_another_program_on_the_port_is_left_alone() -> None:
    started, killed, popen, _ = _start({"77": "/usr/local/bin/node server.js --serve"})
    assert started is False
    killed.assert_not_called()
    popen.assert_not_called()


def test_a_new_server_that_exits_is_not_reported_as_ready() -> None:
    started, _, _, urlopen = _start({}, exited=1)
    assert started is False
    urlopen.assert_not_called()


def test_email_has_no_review_link_when_the_server_did_not_start(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(main, "RESULTS_PATH", tmp_path / "results.json")
    results = [{"category": "Large & Old Files", "risk": "review", "action": "trash", "suggestion": "",
                "total_size_bytes": 1, "items": [{"path": "/tmp/a", "label": "a", "size_bytes": 1, "meta": {}}]}]
    sent = []
    with patch("main.reporter.print_unattended_report", return_value="report text"), \
         patch("main.history.record"), patch("main._start_review_server", return_value=False), \
         patch("main.emailer.send_report", side_effect=lambda s, b, t, **kw: sent.append((b, kw["html_body"]))):
        main.unattended_mode(results, False, "test@example.com", no_email=False)

    body, html = sent[0]
    assert "localhost" not in body + html
    assert "main.py --review" in body


def _review_result(category, paths):
    items = [{"path": p, "label": p.rsplit("/", 1)[-1], "size_bytes": 10, "meta": {}} for p in paths]
    return {"category": category, "risk": "review", "action": "trash", "items": items,
            "total_size_bytes": 10 * len(items), "suggestion": ""}


def test_a_file_moved_in_one_review_step_is_not_offered_again_in_a_later_one():
    import cleaner
    results = [_review_result("Large & Old Files", ["/d/old.dmg"]),
               _review_result("Duplicates", ["/d/old.dmg", "/d/other.dmg"])]
    asked = []

    def confirm(question, default):
        asked.append(question)
        return True

    def clean(items, **kw):
        return cleaner.CleanResult(moved=len(items), moved_paths=[i["path"] for i in items])

    with patch("main._confirm", side_effect=confirm), patch("main.reporter.print_item_detail") as shown, \
         patch("main.cleaner_mod.clean_items", side_effect=clean) as cleaned:
        total = main.interactive_mode(results, permanent=False)

    offered = [c.args[0]["path"] for c in shown.call_args_list]
    assert offered == ["/d/old.dmg", "/d/other.dmg"]
    assert [[i["path"] for i in c.args[0]] for c in cleaned.call_args_list] == [["/d/old.dmg"], ["/d/other.dmg"]]
    assert total.moved_paths == ["/d/old.dmg", "/d/other.dmg"]


@pytest.mark.parametrize("permanent, words", [(False, "Move your WHOLE mail folder"),
                                              (True, "Permanently delete your WHOLE mail folder")])
def test_the_terminal_review_names_the_whole_mail_folder_before_moving_it(permanent, words, capsys):
    results = [_review_result("Mail Store", ["/Users/x/Library/Mail"])]
    asked = []

    def confirm(question, default):
        asked.append((question, default))
        return not question.startswith("  ")

    with patch("main._confirm", side_effect=confirm), \
         patch("main.console", main.Console(width=300, force_terminal=False)), \
         patch("main.cleaner_mod.clean_items") as cleaned:
        main.interactive_mode(results, permanent=permanent)

    item_question, default = asked[1]
    assert words in item_question and default is False
    cleaned.assert_not_called()
    assert "Mail kept only on this Mac would be lost" in capsys.readouterr().out


def test_other_review_items_get_no_mail_warning(capsys):
    results = [_review_result("Large & Old Files", ["/d/big.dmg"])]
    with patch("main._confirm", return_value=False) as confirm, \
         patch("main.console", main.Console(width=300, force_terminal=False)):
        main.interactive_mode(results, permanent=False)
    assert "WHOLE mail" not in capsys.readouterr().out
    assert "WHOLE mail" not in str(confirm.call_args_list)
