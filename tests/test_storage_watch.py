import json
from datetime import datetime, timedelta
from unittest.mock import patch

import storage_watch as sw
from scheduler import build_storage_plist

GB = 1_000_000_000
NOW = datetime(2026, 11, 5, 12, 0)


def test_level_is_ok_at_or_above_the_warning_line():
    assert sw.level(30 * GB, 25, 10) == "ok"
    assert sw.level(25 * GB, 25, 10) == "ok"


def test_level_warns_below_25_gb():
    assert sw.level(24 * GB, 25, 10) == "warn"


def test_level_is_urgent_below_10_gb():
    assert sw.level(4.7 * GB, 25, 10) == "urgent"


def test_ok_never_alerts():
    assert not sw.should_alert("ok", {}, NOW, 24)


def test_first_warning_alerts():
    assert sw.should_alert("warn", {}, NOW, 24)


def test_same_level_within_realert_window_stays_quiet():
    state = {"level": "warn", "alerted_at": (NOW - timedelta(hours=3)).isoformat()}
    assert not sw.should_alert("warn", state, NOW, 24)


def test_same_level_after_realert_window_alerts_again():
    state = {"level": "warn", "alerted_at": (NOW - timedelta(hours=25)).isoformat()}
    assert sw.should_alert("warn", state, NOW, 24)


def test_escalation_to_urgent_alerts_at_once():
    state = {"level": "warn", "alerted_at": (NOW - timedelta(minutes=5)).isoformat()}
    assert sw.should_alert("urgent", state, NOW, 24)


def test_easing_from_urgent_to_warn_stays_quiet_inside_window():
    state = {"level": "urgent", "alerted_at": (NOW - timedelta(hours=1)).isoformat()}
    assert not sw.should_alert("warn", state, NOW, 24)


def test_unreadable_state_timestamp_alerts_rather_than_silences():
    assert sw.should_alert("warn", {"level": "warn", "alerted_at": "garbage"}, NOW, 24)


def test_top_users_puts_trash_first_then_largest(tmp_path):
    for name, size in (("Trash", 2_000), ("Downloads", 90_000), ("Caches", 300_000)):
        (tmp_path / name).mkdir()
        (tmp_path / name / "blob").write_bytes(b"x" * size)
    (tmp_path / "Missing").mkdir()
    (tmp_path / "Missing").rmdir()
    users_cfg = [(n, tmp_path / n) for n in ("Trash", "Downloads", "Caches", "Missing")]
    with patch.object(sw, "SPACE_USERS", users_cfg):
        users = sw.top_users()
    assert [name for name, _ in users] == ["Trash", "Caches", "Downloads"]
    assert dict(users)["Caches"] >= 300_000


def _run_check(tmp_path, free, state=None):
    state_path = tmp_path / "state.json"
    if state is not None:
        state_path.write_text(json.dumps(state))
    sent, notes = [], []
    with patch.object(sw, "STATE_PATH", state_path), \
         patch.object(sw, "free_bytes", return_value=free), \
         patch.object(sw, "top_users", return_value=[("Trash", 72 * GB), ("Downloads", 5 * GB)]), \
         patch.object(sw.emailer, "send_report", side_effect=lambda *a, **k: sent.append((a, k)) or True), \
         patch.object(sw, "notify", side_effect=lambda t, m: notes.append((t, m))), \
         patch.object(sw.cfg, "get", side_effect=lambda k: {"storage_warn_gb": 25, "storage_urgent_gb": 10,
                                                             "storage_realert_hours": 24,
                                                             "email_report_to": "me@example.com"}.get(k)):
        lvl = sw.check(now=NOW)
    return lvl, sent, notes, state_path


def test_check_urgent_sends_urgent_email_and_notification_naming_the_trash(tmp_path):
    lvl, sent, notes, _ = _run_check(tmp_path, int(4.7 * GB))
    assert lvl == "urgent"
    assert len(sent) == 1 and len(notes) == 1
    (subject, body, to), kwargs = sent[0]
    assert to == "me@example.com"
    assert kwargs.get("urgent") and not kwargs.get("action")
    assert "4.7 GB" in subject
    assert body.index("Trash") < body.index("Downloads")
    assert "72.0 GB" in body


def test_check_warn_sends_action_email_not_urgent(tmp_path):
    _, sent, _, _ = _run_check(tmp_path, 20 * GB)
    assert sent[0][1].get("action") and not sent[0][1].get("urgent")


def test_check_records_alert_so_the_next_hour_is_quiet(tmp_path):
    _, sent1, _, state_path = _run_check(tmp_path, 20 * GB)
    saved = json.loads(state_path.read_text())
    _, sent2, notes2, _ = _run_check(tmp_path, 20 * GB, state=saved)
    assert len(sent1) == 1 and sent2 == [] and notes2 == []


def test_check_back_to_ok_clears_state_so_next_drop_alerts(tmp_path):
    state = {"level": "warn", "alerted_at": NOW.isoformat()}
    _, sent, _, state_path = _run_check(tmp_path, 60 * GB, state=state)
    assert sent == []
    assert json.loads(state_path.read_text()) == {"level": "ok"}


def test_check_ok_skips_measuring_space_users(tmp_path):
    with patch.object(sw, "top_users") as tu:
        state_path = tmp_path / "s.json"
        with patch.object(sw, "STATE_PATH", state_path), \
             patch.object(sw, "free_bytes", return_value=60 * GB):
            sw.check(now=NOW)
    tu.assert_not_called()


def test_failed_email_is_not_recorded_so_next_run_retries(tmp_path):
    state_path = tmp_path / "state.json"
    results = [False, True]
    sends = []

    def send(*a, **k):
        sends.append(a)
        return results[len(sends) - 1]

    with patch.object(sw, "STATE_PATH", state_path), \
         patch.object(sw, "free_bytes", return_value=20 * GB), \
         patch.object(sw, "top_users", return_value=[]), \
         patch.object(sw.emailer, "send_report", side_effect=send), \
         patch.object(sw, "notify"):
        sw.check(now=NOW)
        sw.check(now=NOW + timedelta(hours=1))
    assert len(sends) == 2
    assert json.loads(state_path.read_text())["level"] == "warn"


def test_state_file_that_is_not_an_object_is_treated_as_empty(tmp_path):
    lvl, sent, _, _ = _run_check(tmp_path, 20 * GB, state=[])
    assert lvl == "warn" and len(sent) == 1


def test_notification_goes_out_before_folders_are_measured():
    order = []
    with patch.object(sw, "notify", side_effect=lambda *a: order.append("notify")), \
         patch.object(sw, "top_users", side_effect=lambda: order.append("measure") or []), \
         patch.object(sw.emailer, "send_report", return_value=True):
        sw._alert("urgent", 4 * GB)
    assert order == ["notify", "measure"]


def test_alert_wording_does_not_tell_him_to_clear_a_folder():
    sent = []
    with patch.object(sw, "top_users", return_value=[("Documents", 40 * GB)]), \
         patch.object(sw.emailer, "send_report", side_effect=lambda *a, **k: sent.append((a, k)) or True), \
         patch.object(sw, "notify"):
        sw._alert("urgent", 4 * GB)
    (_, body, _), kwargs = sent[0]
    text = body + kwargs["urgent"]
    assert "loses nothing" not in text and "clear the largest" not in text.lower()
    assert "selected" in body.lower()


def test_bad_threshold_config_falls_back_to_defaults(tmp_path):
    state_path = tmp_path / "state.json"
    bad = {"storage_warn_gb": "lots", "storage_urgent_gb": -3, "storage_realert_hours": None}
    with patch.object(sw, "STATE_PATH", state_path), \
         patch.object(sw, "free_bytes", return_value=20 * GB), \
         patch.object(sw, "top_users", return_value=[]), \
         patch.object(sw.emailer, "send_report", return_value=True), \
         patch.object(sw, "notify"), \
         patch.object(sw.cfg, "get", side_effect=lambda k: bad.get(k, "x@example.com")):
        assert sw.check(now=NOW) == "warn"


def test_storage_plist_runs_hourly_check():
    plist = build_storage_plist()
    assert "<key>StartInterval</key>" in plist
    assert "<integer>3600</integer>" in plist
    assert "--storage-check" in plist
    assert "com.macmaid.storage" in plist


def test_main_storage_check_flag_runs_check():
    import main
    with patch.object(main.sys, "argv", ["main.py", "--storage-check"]), \
         patch("storage_watch.check", return_value="ok") as chk, \
         patch.object(main.reporter, "print_banner") as banner:
        main.main()
    chk.assert_called_once()
    banner.assert_not_called()


def test_unreadable_folder_is_reported_unknown_not_zero(tmp_path):
    locked = tmp_path / "locked"
    (locked / "inner").mkdir(parents=True)
    (locked / "inner" / "blob").write_bytes(b"x" * 50_000)
    (locked / "inner").chmod(0)
    try:
        assert sw._dir_bytes(locked) is None
    finally:
        (locked / "inner").chmod(0o755)


def test_alert_body_says_when_a_folder_could_not_be_measured():
    sent = []
    with patch.object(sw, "top_users", return_value=[("Trash", None), ("Caches", 4 * GB)]), \
         patch.object(sw.emailer, "send_report", side_effect=lambda *a, **k: sent.append(a) or True), \
         patch.object(sw, "notify"):
        sw._alert("warn", 20 * GB)
    body = sent[0][1]
    assert "Trash: could not be measured" in body
    assert "Trash: 0.0 GB" not in body
