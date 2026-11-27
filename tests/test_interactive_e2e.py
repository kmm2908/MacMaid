"""`python main.py` driven end to end in a pseudo-terminal, as a person would."""
import json
import os
import pty
import re
import select
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

RUNNER = str(Path(__file__).with_name("interactive_runner.py"))
ANSI = re.compile(rb"\x1b\[[0-9;?]*[A-Za-z]")
PROMPT = re.compile(r"\((?:Y/n|y/N)\)")
CTRL_C = b"\x03"
ENTER = b"\r"


def _put(path: Path, data: bytes) -> None:
    old = time.time() - 400 * 86400
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    os.utime(path, (old, old))


@pytest.fixture
def root(tmp_path):
    root = Path(os.path.realpath(tmp_path))
    home = root / "home"
    _put(home / ".Trash" / "gone.bin", b"x" * 2048)
    _put(home / "Library" / "Caches" / "com.example.app" / "blob", b"c" * 4096)
    _put(home / "Documents" / "movie [final].mkv", b"m" * (2 * 1024 * 1024))
    _put(home / "Desktop" / "movie copy.mkv", b"m" * (2 * 1024 * 1024))
    for name in ("syscaches", "syslogs", "volumes"):
        (root / name).mkdir()
    (root / "config.json").write_text(json.dumps({
        "scan_paths": ["~/Documents", "~/Desktop"],
        "dev_scan_paths": ["~/Projects"],
        "large_file_threshold_mb": 1,
    }))
    return root


def drive(root: Path, answer, *args: str) -> tuple[int, str, list[str]]:
    """Run to exit, calling answer(number, question) at each prompt."""
    env = dict(os.environ, HOME=str(root / "home"), MM_ROOT=str(root), TERM="xterm",
               COLUMNS="400", LINES="50",
               # moving HOME would otherwise hide a --user install of the dependencies
               PYTHONUSERBASE=os.environ.get("PYTHONUSERBASE") or _user_base())
    main_fd, child_fd = pty.openpty()
    proc = subprocess.Popen([sys.executable, "-B", RUNNER, *args], stdin=child_fd, stdout=child_fd,
                            stderr=child_fd, env=env, start_new_session=True)
    os.close(child_fd)
    raw, answered_up_to, asked = b"", 0, []
    deadline = time.time() + 60
    try:
        while time.time() < deadline:
            if select.select([main_fd], [], [], 0.3)[0]:
                try:
                    chunk = os.read(main_fd, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                if b"\x1b[6n" in chunk:  # the prompt asks where the cursor is
                    os.write(main_fd, b"\x1b[1;1R")
                raw += chunk
                continue
            text = ANSI.sub(b"", raw).decode("utf-8", "replace")
            pending = text[answered_up_to:]
            if PROMPT.search(pending):
                question = [ln for ln in re.split(r"[\r\n]", pending) if PROMPT.search(ln)][-1]
                asked.append(question.strip())
                answered_up_to = len(text)
                os.write(main_fd, answer(len(asked), question))
            elif proc.poll() is not None:
                break
        else:
            pytest.fail("main.py did not finish: " + ANSI.sub(b"", raw).decode("utf-8", "replace")[-2000:])
        code = proc.wait(timeout=10)
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
        os.close(main_fd)
    return code, ANSI.sub(b"", raw).decode("utf-8", "replace"), asked


def _user_base() -> str:
    import site
    return site.getuserbase()


def _files(root: Path) -> set[str]:
    return {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}


def test_yes_to_everything_cleans_and_offers_no_file_twice(root):
    code, screen, asked = drive(root, lambda n, q: b"y")

    assert code == 0, screen
    assert not (root / "home" / ".Trash" / "gone.bin").exists()
    assert (root / "binned" / "movie [final].mkv").exists()
    assert (root / "binned" / "movie copy.mkv").exists()
    # the copy went in Large & Old Files, so Duplicates has nothing left to ask
    assert not any("Duplicates" in q for q in asked), asked
    assert "could not be removed" not in screen
    # totals add up across both batches: the cache and the two 2 MB copies
    assert "Cleaned: 4 items, 4 MB freed" in screen


def test_no_to_everything_changes_nothing(root):
    before = _files(root)

    code, screen, _ = drive(root, lambda n, q: b"n")

    assert code == 0, screen
    assert _files(root) == before
    assert "Cleaned: 0 items" in screen


def test_ctrl_c_stops_the_run(root):
    before = _files(root)

    # any prompt after Ctrl-C would delete something
    code, screen, asked = drive(root, lambda n, q: CTRL_C if n == 1 else b"y")

    assert code == 0, screen
    assert len(asked) == 1, asked
    assert _files(root) == before
    assert "Stopped" in screen


def test_ctrl_c_during_file_review_moves_none_of_that_batch(root):
    before = _files(root)
    moves = []

    def answer(n, question):
        if "Move to Trash" in question:
            moves.append(question)
            return b"y" if len(moves) == 1 else CTRL_C
        return b"y" if "Large" in question else b"n"

    code, screen, asked = drive(root, answer)

    assert code == 0, screen
    assert _files(root) == before
    assert "Move to Trash" in asked[-1], asked


def test_file_names_with_square_brackets_are_shown_in_full(root):
    code, screen, _ = drive(root, lambda n, q: b"n" if "Review Duplicates" not in q else b"y")

    assert code == 0, screen
    table = screen.split("Review Large")[0]
    assert "movie [final].mkv" in table
    # and in the line printed before asking about that one file
    assert "movie [final].mkv \u2014 2 MB (duplicate of" in screen


def test_a_failed_removal_is_written_to_the_error_log(root):
    _put(root / "home" / "Library" / "Caches" / "locked.cache" / "blob", b"c" * 4096)

    code, screen, _ = drive(root, lambda n, q: b"y" if "Caches" in q else b"n")

    assert code == 0, screen
    assert "could not be removed" in screen
    assert "locked.cache" in (root / "error.log").read_text()


def test_permanent_mode_says_so_before_deleting(root):
    code, screen, asked = drive(root, lambda n, q: b"y", "--permanent")

    assert code == 0, screen
    assert any("Delete permanently?" in q for q in asked), asked
    assert not any("Move to Trash" in q for q in asked), asked
    assert any("Permanently delete Caches?" in q for q in asked), asked
    assert not (root / "binned").exists()


def test_enter_alone_empties_no_trash_and_moves_no_reviewed_file(root):
    code, screen, asked = drive(root, lambda n, q: ENTER)

    assert code == 0, screen
    assert any("Clean Trash?" in q and "(y/N)" in q for q in asked), asked
    assert (root / "home" / ".Trash" / "gone.bin").exists()
    assert (root / "home" / "Documents" / "movie [final].mkv").exists()
    assert (root / "home" / "Desktop" / "movie copy.mkv").exists()
    assert any("Move to Trash" in q for q in asked), asked
    # a cache goes to the Trash and can come back, so Enter still cleans it
    assert (root / "binned" / "com.example.app").exists(), screen


def test_enter_alone_deletes_nothing_in_permanent_mode(root):
    before = _files(root)

    code, screen, asked = drive(root, lambda n, q: ENTER, "--permanent")

    assert code == 0, screen
    assert any("Delete permanently?" in q for q in asked), asked
    assert _files(root) == before
