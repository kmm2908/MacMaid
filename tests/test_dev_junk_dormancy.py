"""node_modules is only junk when nobody is working on the project any more.

The 2026-09-01 guard offered a `node_modules` when git tracked `package.json`
beside it. That proves the tree is *reinstallable*, not that it is disposable —
so the rule written to spare installed software is exactly what selected live
projects. Measured 2026-09-08: all 22 node_modules the sweep offered belonged to
repositories committed to that same day, 519 of them were sitting in the volume
Trash, and one project had lost the same directory eight times.

Deleting a live dependency tree produces no error anywhere: the cleaner reports
success and the next test run fails as if the code had regressed. So the rule
fails closed, and it takes TWO things — an old repository AND no sign of recent
local work, because an old commit date says nothing about a fresh clone that was
installed this morning or a checkout being edited without commits.

These fixtures use REAL repositories with REAL commit dates and REAL mtimes,
because those are the things under test. Every negative case is paired with a
positive one, so "correctly spared" cannot be confused with "nothing is ever
offered" — a sweep that offers nothing has removed the feature, not fixed it.
"""
import os
import subprocess
import time

from modules import dev_junk

GIT_ID = ["-c", "user.email=t@example.com", "-c", "user.name=Test"]
DORMANT = dev_junk.DORMANT_DAYS_DEFAULT + 220   # comfortably past the window


def _git(cwd: str, *args: str, when: float | None = None) -> None:
    """Fixture creation only — the developer's global config, hooks and signing
    key stay out of the fixtures. `when` back-dates BOTH dates: git reads the
    committer date, and setting only the author date changes nothing."""
    env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
    if when is not None:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = f"{int(when)} +0000"
    subprocess.run(
        ["git", *GIT_ID, *args], cwd=cwd, check=True,
        capture_output=True, text=True, env=env,
    )


def _file(path: str, name: str, body: str = "x" * 10) -> str:
    os.makedirs(path, exist_ok=True)
    fp = os.path.join(path, name)
    with open(fp, "w") as f:
        f.write(body)
    return fp


def _age(path: str, days: float) -> None:
    stamp = time.time() - days * 86400
    os.utime(path, (stamp, stamp))


def _repo(root: str, age_days: float) -> str:
    """A real repository whose newest commit is `age_days` old."""
    os.makedirs(root, exist_ok=True)
    _git(root, "init", "-q")
    _file(root, "README.md", "# repo\n")
    _git(root, "add", "README.md")
    _git(root, "commit", "-qm", "init", when=time.time() - age_days * 86400)
    return root


def _project(root: str, age_days: float, rel: str = "myproject",
             mtime_age_days: float | None = None) -> str:
    """A committed node package with an installed node_modules.

    `age_days` sets the commit date; `mtime_age_days` sets the file mtimes and
    defaults to the same, which is what an untouched project on disk looks
    like. They are separable so a test can isolate one rule from the other.
    """
    when = time.time() - age_days * 86400
    files_age = age_days if mtime_age_days is None else mtime_age_days
    proj = os.path.join(root, rel)
    manifest = _file(proj, "package.json", "{}")
    _git(root, "add", os.path.join(rel, "package.json"))
    _git(root, "commit", "-qm", f"add {rel}", when=when)
    nm = os.path.join(proj, "node_modules")
    _file(os.path.join(nm, "dep"), "index.js")
    for p in (manifest, os.path.join(nm, "dep"), nm, proj):
        _age(p, files_age)
    return nm


def _paths(base: str) -> list:
    items: list = []
    dev_junk._scan_path(base, items)
    return [i["path"] for i in items]


# --- the reported fault ------------------------------------------------------


def test_live_project_node_modules_is_not_offered(tmp_path):
    """Driven through the real scan path: a project committed to today keeps its
    dependencies, tracked manifest or not."""
    root = _repo(str(tmp_path), age_days=0)
    _project(root, age_days=0)

    assert _paths(root) == []


def test_dormant_project_node_modules_is_still_offered(tmp_path):
    """The control. A sweep that offers nothing has removed the feature rather
    than fixed it, so an abandoned checkout must still be reclaimed."""
    root = _repo(str(tmp_path), age_days=DORMANT)
    wanted = _project(root, age_days=DORMANT)

    assert _paths(root) == [wanted]


def test_only_the_dormant_one_comes_back_from_a_single_scan(tmp_path):
    """Both halves in one walk, so 'correctly spared' cannot be read off a
    scanner that has simply stopped offering anything."""
    live = _repo(os.path.join(str(tmp_path), "live"), age_days=1)
    dead = _repo(os.path.join(str(tmp_path), "dead"), age_days=DORMANT)
    _project(live, age_days=1)
    wanted = _project(dead, age_days=DORMANT)

    assert _paths(str(tmp_path)) == [wanted]


def test_a_project_one_day_short_of_the_window_is_spared(tmp_path):
    """Every file is long untouched, so only the commit date can decide this —
    otherwise an activity veto answers and the boundary goes untested."""
    root = _repo(str(tmp_path), age_days=179)
    _project(root, age_days=179, mtime_age_days=DORMANT)

    assert _paths(root) == []


# --- local activity the commit date cannot see -------------------------------


def test_a_fresh_clone_of_an_old_project_is_spared(tmp_path):
    """Every commit is years old and the dependencies went in this morning.
    The repository looks abandoned; the working copy plainly is not."""
    root = _repo(str(tmp_path), age_days=DORMANT)
    nm = _project(root, age_days=DORMANT)
    _age(nm, 0)

    assert _paths(root) == []


def test_an_old_checkout_with_work_in_flight_is_spared(tmp_path):
    """Edited for months without a commit: nothing in the dates says so, and a
    dirty tracked file is the only thing that does."""
    root = _repo(str(tmp_path), age_days=DORMANT)
    _project(root, age_days=DORMANT)
    _file(root, "README.md", "# still working on this\n")

    assert _paths(root) == []


def test_untracked_work_beside_the_dependencies_spares_the_project(tmp_path):
    """`git status -uno` never reports an untracked or gitignored file, and a
    build output or a scratch file written today is somebody working."""
    root = _repo(str(tmp_path), age_days=DORMANT)
    _project(root, age_days=DORMANT)
    proj = os.path.join(root, "myproject")
    notes = _file(proj, "notes.txt")
    # Age the directory back after creating it, then EDIT the file: rewriting a
    # file leaves its directory's mtime alone, so only reading the entry itself
    # can see this. Creating one would bump the directory and prove nothing.
    _age(proj, DORMANT)
    _age(notes, DORMANT)
    assert _paths(root) != []                       # dormant until it is edited

    with open(notes, "w") as f:
        f.write("picked this back up today")

    assert _paths(root) == []


def test_this_modules_own_git_queries_do_not_look_like_activity(tmp_path):
    """`git status` takes a lock inside `.git`, which moves its mtime. Counting
    that as work would make every repository look busy — including this one,
    on the second candidate in the same directory."""
    root = _repo(str(tmp_path), age_days=DORMANT)
    wanted = _project(root, age_days=DORMANT, rel=".")
    _age(os.path.join(root, "README.md"), DORMANT)
    _age(root, DORMANT)   # `.git` is the only fresh thing left in here

    assert _paths(root) == [os.path.normpath(wanted)]


def test_a_manifest_edited_today_spares_the_project(tmp_path):
    """A committed dependency bump that has not been installed yet still means
    somebody is here."""
    root = _repo(str(tmp_path), age_days=DORMANT)
    _project(root, age_days=DORMANT)
    _age(os.path.join(root, "myproject", "package.json"), 0)

    assert _paths(root) == []


def test_a_newer_commit_on_another_branch_spares_the_project(tmp_path):
    """A checkout parked on a stale branch is not an abandoned repository.
    Reading HEAD alone would call it one."""
    root = _repo(str(tmp_path), age_days=DORMANT)
    wanted = _project(root, age_days=DORMANT)
    assert _paths(root) == [wanted]          # dormant until the branch exists

    _git(root, "checkout", "-q", "-b", "current")
    _file(root, "NOTES.md", "active work\n")
    _git(root, "add", "NOTES.md")
    _git(root, "commit", "-qm", "recent work on another branch")
    _git(root, "checkout", "-q", "-")
    _age(os.path.join(root, "myproject", "node_modules"), DORMANT)

    assert _paths(root) == []


# --- the window --------------------------------------------------------------


def test_the_window_comes_from_config(tmp_path, monkeypatch):
    """A shorter window must actually shorten it — otherwise the 180 is baked in
    and the config key is decoration."""
    root = _repo(str(tmp_path), age_days=60)
    wanted = _project(root, age_days=60)

    assert _paths(root) == []

    real = dev_junk.cfg.get
    monkeypatch.setattr(
        dev_junk.cfg, "get",
        lambda k: 30 if k == "dev_junk_dormant_days" else real(k),
    )
    assert _paths(root) == [wanted]


def test_a_window_that_would_switch_the_guard_off_falls_back_to_the_default(
        tmp_path, monkeypatch):
    """0, a negative, a bool or a non-number would make every project dormant —
    the incident this rule exists to stop — or raise mid-scan. None of them may
    be honoured."""
    root = _repo(str(tmp_path), age_days=1)
    _project(root, age_days=1)
    real = dev_junk.cfg.get

    for bad in (0, -1, True, float("inf"), float("nan"), "soon", None, [180]):
        monkeypatch.setattr(
            dev_junk.cfg, "get",
            lambda k, _b=bad: _b if k == "dev_junk_dormant_days" else real(k),
        )
        assert dev_junk._dormant_days() == float(dev_junk.DORMANT_DAYS_DEFAULT), bad
        assert _paths(root) == [], bad


# --- fail-closed on an unanswerable git --------------------------------------


def test_repository_with_no_commits_yet_is_declined_not_counted_as_degraded(tmp_path):
    """A staged manifest with no commit behind it is an ordinary state, not a
    git malfunction: decline it, and do not report the scan as incomplete."""
    root = str(tmp_path)
    _git(root, "init", "-q")
    proj = os.path.join(root, "myproject")
    manifest = _file(proj, "package.json", "{}")
    _git(root, "add", os.path.join("myproject", "package.json"))
    nm = os.path.join(proj, "node_modules")
    _file(nm, "index.js")
    # Everything else back-dated, so the missing commit date is the only thing
    # left that can decline this — otherwise an activity veto answers for it and
    # the test passes whatever the age rule does.
    for path in (manifest, os.path.join(nm, "index.js"), nm, proj):
        _age(path, DORMANT)

    cache = dev_junk._new_cache()
    assert dev_junk._head_age_days(proj, cache) is None
    assert dev_junk._is_project_junk("node_modules", proj, cache) is False
    assert cache[dev_junk._DEGRADED_KEY] == 0


def test_exhausted_git_budget_declines_and_is_counted(tmp_path):
    """Past the budget nothing may be offered on a guess, and the run must say
    so — an incomplete scan that reads as a clean machine is the worse failure."""
    root = _repo(str(tmp_path), age_days=DORMANT)
    _project(root, age_days=DORMANT)
    parent = os.path.join(root, "myproject")

    cache = dev_junk._new_cache()
    dev_junk._tracked_names(parent, cache)  # tracked evidence, cached and free
    cache[dev_junk._SPENT_KEY] = dev_junk.GIT_SCAN_BUDGET_SECONDS + 1

    assert dev_junk._is_project_junk("node_modules", parent, cache) is False
    assert cache[dev_junk._DEGRADED_KEY] == 1


def test_an_unanswerable_status_counts_as_activity(tmp_path, monkeypatch):
    """Everything else says dormant; git cannot say whether work is in flight.
    Under-cleaning is the safe direction, and the run must admit it."""
    root = _repo(str(tmp_path), age_days=DORMANT)
    _project(root, age_days=DORMANT)
    parent = os.path.join(root, "myproject")
    real_run = dev_junk.subprocess.run

    def fail_status(*a, **k):
        if "status" in a[0]:
            raise OSError("git is having a day")
        return real_run(*a, **k)

    monkeypatch.setattr(dev_junk.subprocess, "run", fail_status)
    cache = dev_junk._new_cache()
    assert dev_junk._is_project_junk("node_modules", parent, cache) is False
    assert cache[dev_junk._DEGRADED_KEY] == 1


# --- scope -------------------------------------------------------------------


def test_bytecode_in_a_live_project_is_still_offered(tmp_path):
    """Dormancy applies to node_modules only. A .pyc costs seconds and no
    network to rebuild, and stopping it would quietly gut the rest of the
    module."""
    root = _repo(str(tmp_path), age_days=0)
    proj = os.path.join(root, "pkg")
    _file(proj, "mod.py", "x = 1\n")
    _git(root, "add", os.path.join("pkg", "mod.py"))
    _git(root, "commit", "-qm", "add pkg")
    _file(os.path.join(proj, "__pycache__"), "mod.cpython-312.pyc", "\x00")

    assert _paths(root) == [os.path.join(proj, "__pycache__")]


def test_the_recorded_state_predates_the_size_walk(tmp_path, monkeypatch):
    """`_dir_size()` walks the whole tree, which takes real time on a real
    node_modules. An install finishing during that walk must not be recorded as
    the state the cleaner later checks against, or the race closes itself."""
    root = _repo(str(tmp_path), age_days=DORMANT)
    nm = _project(root, age_days=DORMANT)
    before = os.path.getmtime(nm)
    real_size = dev_junk._dir_size

    def install_midway(path: str) -> int:
        if path == nm:
            _file(nm, "arrived-during-the-walk.js")
        return real_size(path)

    monkeypatch.setattr(dev_junk, "_dir_size", install_midway)
    items: list = []
    dev_junk._scan_path(root, items)

    assert items[0]["meta"]["mtime"] == before
    assert os.path.getmtime(nm) != before      # the fixture really did change it


def test_the_offered_directory_records_what_it_looked_like(tmp_path):
    """The cleaner re-checks this before deleting, so the scan has to record
    it — an item with no mtime is one nothing can revalidate."""
    root = _repo(str(tmp_path), age_days=DORMANT)
    nm = _project(root, age_days=DORMANT)

    items: list = []
    dev_junk._scan_path(root, items)

    assert items[0]["meta"]["mtime"] == os.path.getmtime(nm)
