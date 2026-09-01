"""dev_junk must not trash artefacts belonging to installed software.

On 2026-08-30 the daily sweep stripped node_modules out of six installed VS Code
extensions. The discriminator is whether the artefact's own directory holds
version-controlled source — an ancestor `.git` proves nothing, because installed
software lives untracked inside checkouts — plus a deny-list of the places
software installs itself to, for the case where the installed thing IS a
checkout.

These fixtures use REAL git repositories on purpose: a hand-planted `.git`
marker would test the stand-in rather than the rule. Most negative tests plant a
genuine project artefact alongside the installed one and assert that exactly the
project artefact comes back, so "correctly excluded" cannot be confused with
"the scanner rejects everything".
"""
import os
import subprocess
import time

from modules import dev_junk

GIT_ID = ["-c", "user.email=t@example.com", "-c", "user.name=Test"]


def _git(cwd: str, *args: str) -> None:
    """Fixture creation only — the developer's global config, hooks and signing
    key stay out of the fixtures. Production git behaviour is deliberately NOT
    isolated this way; see conftest.py."""
    env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
    subprocess.run(
        ["git", *GIT_ID, *args], cwd=cwd, check=True,
        capture_output=True, text=True, env=env,
    )


def _file(path: str, name: str = "f.txt", body: str = "x" * 10) -> str:
    os.makedirs(path, exist_ok=True)
    fp = os.path.join(path, name)
    with open(fp, "w") as f:
        f.write(body)
    return fp


def _repo(root: str) -> str:
    """A real repository with one tracked file at its root."""
    os.makedirs(root, exist_ok=True)
    _git(root, "init", "-q")
    _file(root, "README.md", "# repo\n")
    _git(root, "add", "README.md")
    _git(root, "commit", "-qm", "init")
    return root


def _project(root: str, rel: str) -> str:
    """A tracked node package inside `root` whose node_modules MUST be offered."""
    proj = os.path.join(root, rel)
    _file(proj, "package.json", "{}")
    _git(root, "add", os.path.join(rel, "package.json"))
    _file(os.path.join(proj, "node_modules", "dep"), "index.js")
    return os.path.join(proj, "node_modules")


def _paths(base: str) -> list:
    items: list = []
    dev_junk._scan_path(base, items)
    return [i["path"] for i in items]


# --- installed software ------------------------------------------------------


def test_installed_extension_inside_a_repo_not_offered(tmp_path):
    """The production topology: a repo at the scan ROOT must not bless what it
    does not track. VS Code extensions ship their own package.json, so a
    manifest-existence check alone would let them through."""
    root = _repo(str(tmp_path))
    wanted = _project(root, "myproject")
    ext = os.path.join(root, ".vscode", "extensions", "publisher.ext-1.2.3")
    _file(ext, "package.json", '{"name": "ext"}')
    _file(os.path.join(ext, "node_modules", "dep"), "index.js")

    assert _paths(root) == [wanted]


def test_installed_software_that_is_itself_a_checkout_not_offered(tmp_path):
    """A tool installed by `git clone` + `npm install` is a valid checkout with a
    tracked manifest — structurally identical to a project. Only its location
    tells them apart, which is what the deny-list is for."""
    root = str(tmp_path)
    wanted = _project(_repo(os.path.join(root, "work")), "myproject")
    tool = os.path.join(root, ".local", "share", "sometool")
    _repo(tool)
    _file(tool, "package.json", "{}")
    _git(tool, "add", "package.json")
    _file(os.path.join(tool, "node_modules", "dep"), "index.js")

    assert _paths(root) == [wanted]


def test_untracked_python_tree_inside_a_repo_not_offered(tmp_path):
    """A vendored or installed Python tree inside a genuine checkout."""
    root = _repo(str(tmp_path))
    _file(os.path.join(root, "src"), "mod.py", "x = 1\n")
    _git(root, "add", "src/mod.py")
    wanted = os.path.join(root, "src", "__pycache__")
    _file(wanted, "mod.cpython-312.pyc")

    pkg = os.path.join(root, ".venv", "lib", "python3.12", "site-packages", "flask")
    _file(pkg, "app.py", "x = 1\n")
    _file(os.path.join(pkg, "__pycache__"), "app.cpython-312.pyc")

    assert _paths(root) == [wanted]


def test_tracked_neighbour_does_not_vouch_for_an_untracked_manifest(tmp_path):
    """A tracked README beside an installed, untracked package.json is not a
    project: the manifest itself must carry the git evidence."""
    root = _repo(str(tmp_path))
    bundled = os.path.join(root, "bundled")
    _file(bundled, "NOTICE.txt", "third party\n")
    _git(root, "add", "bundled/NOTICE.txt")
    _file(bundled, "package.json", "{}")
    _file(os.path.join(bundled, "node_modules", "dep"), "index.js")

    assert _paths(root) == []


def test_inherited_git_dir_cannot_vouch_for_a_directory(tmp_path, monkeypatch):
    """GIT_DIR/GIT_WORK_TREE override `git -C`, so an inherited pair would let a
    real repository's index answer for a directory that is in no repository."""
    real = _repo(str(tmp_path / "real"))
    _file(real, "package.json", "{}")          # so the leaked index carries the
    _git(real, "add", "package.json")          # very name the rule looks for
    outside = str(tmp_path / "outside")
    _file(outside, "package.json", "{}")
    _file(os.path.join(outside, "node_modules", "dep"), "index.js")
    monkeypatch.setenv("GIT_DIR", os.path.join(real, ".git"))

    assert _paths(outside) == []


def test_marker_excludes_a_fully_tracked_installed_checkout(tmp_path):
    """Causally exercise the `.vscode` marker: this extension is a real checkout
    with a TRACKED package.json, so the tracked-name test alone would offer it
    and only the marker list declines it."""
    root = _repo(str(tmp_path))
    wanted = _project(root, "myproject")
    ext = os.path.join(root, ".vscode", "extensions", "publisher.ext-1.2.3")
    _repo(ext)
    _file(ext, "package.json", '{"name": "ext"}')
    _git(ext, "add", "package.json")
    _file(os.path.join(ext, "node_modules", "dep"), "index.js")

    assert _paths(root) == [wanted]


def test_home_install_root_excludes_a_tracked_checkout(tmp_path, monkeypatch):
    """`~/bin`, `~/opt`, `~/.config` and friends hold installed things only."""
    home = str(tmp_path / "home")
    monkeypatch.setenv("HOME", home)
    wanted = _project(_repo(os.path.join(home, "work")), "myproject")
    tool = os.path.join(home, "bin", "sometool")
    _repo(tool)
    _file(tool, "package.json", "{}")
    _git(tool, "add", "package.json")
    _file(os.path.join(tool, "node_modules", "dep"), "index.js")

    assert _paths(home) == [wanted]


def test_marker_matching_is_case_insensitive_and_segment_bounded():
    assert dev_junk._is_installed_software_path("/x/.VSCode/extensions/a")
    assert dev_junk._is_installed_software_path("/x/Library/Application Support/a")
    # a directory merely *containing* a marker word is not a marker segment
    assert not dev_junk._is_installed_software_path("/x/my.cache-tool/src")
    assert not dev_junk._is_installed_software_path("/x/venvs/project")


def test_relative_scan_root_cannot_sidestep_the_markers(tmp_path, monkeypatch):
    """The markers are matched on the resolved path, not the walk path."""
    root = _repo(str(tmp_path))
    ext = os.path.join(root, ".vscode", "extensions", "e")
    _repo(ext)
    _file(ext, "package.json", "{}")
    _git(ext, "add", "package.json")
    _file(os.path.join(ext, "node_modules", "dep"), "index.js")
    monkeypatch.chdir(os.path.join(root, ".vscode"))

    assert _paths("extensions") == []


def test_symlinked_scan_root_cannot_sidestep_the_markers(tmp_path):
    root = _repo(str(tmp_path))
    ext = os.path.join(root, ".vscode", "extensions", "e")
    _repo(ext)
    _file(ext, "package.json", "{}")
    _git(ext, "add", "package.json")
    _file(os.path.join(ext, "node_modules", "dep"), "index.js")
    alias = os.path.join(root, "looks-like-a-project")
    os.symlink(ext, alias)

    assert _paths(alias) == []


def test_node_modules_outside_any_repo_not_offered(tmp_path):
    root = str(tmp_path)
    wanted = _project(_repo(os.path.join(root, "work")), "myproject")
    app = os.path.join(root, "vendor-dist", "resources")   # no bundle suffix
    _file(app, "package.json", "{}")
    _file(os.path.join(app, "node_modules", "dep"), "index.js")

    assert _paths(root) == [wanted]


def test_empty_git_marker_is_not_a_repository(tmp_path):
    """A directory named .git with nothing in it must not count as a checkout."""
    root = str(tmp_path)
    wanted = _project(_repo(os.path.join(root, "work")), "myproject")
    proj = os.path.join(root, "not-really-a-repo")
    os.makedirs(os.path.join(proj, ".git"), exist_ok=True)
    _file(proj, "package.json", "{}")
    _file(os.path.join(proj, "node_modules", "dep"), "index.js")

    assert _paths(root) == [wanted]


def test_dangling_gitdir_file_is_not_a_repository(tmp_path):
    root = str(tmp_path)
    wanted = _project(_repo(os.path.join(root, "work")), "myproject")
    proj = os.path.join(root, "broken-worktree")
    os.makedirs(proj, exist_ok=True)
    _file(proj, ".git", "gitdir: /nowhere/.git/worktrees/x\n")
    _file(proj, "package.json", "{}")
    _file(os.path.join(proj, "node_modules", "dep"), "index.js")

    assert _paths(root) == [wanted]


def test_loose_pyc_outside_any_repo_not_offered(tmp_path):
    root = str(tmp_path)
    wanted = _project(_repo(os.path.join(root, "work")), "myproject")
    _file(os.path.join(root, "Application", "lib"), "shipped.pyc")

    assert _paths(root) == [wanted]


def test_loose_pyc_in_installed_software_not_offered(tmp_path):
    """A frozen app can ship .pyc with the .py stripped — deleting one is
    permanent, so the deny-list covers bytecode too."""
    root = _repo(str(tmp_path))
    _file(root, "mod.py", "x = 1\n")
    _git(root, "add", "mod.py")
    _file(root, "mod.pyc")
    cached = os.path.join(root, ".cache", "sometool")
    _file(cached, "mod.py", "x = 1\n")
    _file(cached, "mod.pyc")

    assert _paths(root) == [os.path.join(root, "mod.pyc")]


# --- genuine project junk (the exclusion must not swallow this) --------------


def test_project_node_modules_still_offered(tmp_path):
    root = _repo(str(tmp_path))
    wanted = _project(root, "myproject")

    assert _paths(root) == [wanted]


def test_node_modules_without_tracked_manifest_not_offered(tmp_path):
    """Belt and braces: tracked source beside it, but no manifest at all."""
    root = _repo(str(tmp_path))
    _file(os.path.join(root, "node_modules", "dep"), "index.js")

    assert _paths(root) == []


def test_project_pycache_still_offered(tmp_path):
    root = _repo(str(tmp_path))
    src = os.path.join(root, "src")
    _file(src, "mod.py", "x = 1\n")
    _git(root, "add", "src/mod.py")
    _file(os.path.join(src, "__pycache__"), "mod.cpython-312.pyc")

    assert _paths(root) == [os.path.join(src, "__pycache__")]


def test_mypy_and_pytest_caches_still_offered(tmp_path):
    root = _repo(str(tmp_path))
    _file(root, "pyproject.toml", "[project]\n")
    _git(root, "add", "pyproject.toml")
    _file(os.path.join(root, ".mypy_cache"), "cache.json")
    _file(os.path.join(root, ".pytest_cache"), "lastfailed")

    assert sorted(_paths(root)) == sorted(
        [os.path.join(root, ".mypy_cache"), os.path.join(root, ".pytest_cache")]
    )


def test_loose_pyc_beside_its_own_tracked_source_still_offered(tmp_path):
    root = _repo(str(tmp_path))
    _file(root, "mod.py", "x = 1\n")
    _git(root, "add", "mod.py")
    _file(root, "mod.pyc")

    assert _paths(root) == [os.path.join(root, "mod.pyc")]


def test_orphan_pyc_beside_unrelated_tracked_source_not_offered(tmp_path):
    """`mod.py` being tracked says nothing about `stale.pyc` beside it — that is
    exactly the source-stripped shape."""
    root = _repo(str(tmp_path))
    _file(root, "mod.py", "x = 1\n")
    _git(root, "add", "mod.py")
    _file(root, "mod.cpython-312.pyc")
    _file(root, "stale.pyc")

    assert _paths(root) == [os.path.join(root, "mod.cpython-312.pyc")]


def test_pycache_holding_bytecode_without_source_not_offered(tmp_path):
    """One orphan inside __pycache__ condemns the whole directory: the cleaner
    removes it wholesale, so partial evidence is not evidence."""
    root = _repo(str(tmp_path))
    good = os.path.join(root, "good")
    _file(good, "mod.py", "x = 1\n")
    _git(root, "add", "good/mod.py")
    _file(os.path.join(good, "__pycache__"), "mod.cpython-312.pyc")

    mixed = os.path.join(root, "mixed")
    _file(mixed, "mod.py", "x = 1\n")
    _git(root, "add", "mixed/mod.py")
    _file(os.path.join(mixed, "__pycache__"), "mod.cpython-312.pyc")
    _file(os.path.join(mixed, "__pycache__"), "stripped.cpython-312.pyc")

    assert _paths(root) == [os.path.join(good, "__pycache__")]


def test_linked_git_worktree_is_recognised(tmp_path):
    """The owner works in linked worktrees; their junk must still be cleaned."""
    main = _repo(str(tmp_path / "main"))
    wt = str(tmp_path / "wt")
    _git(main, "worktree", "add", "-q", "-b", "feature", wt)
    _file(wt, "package.json", "{}")
    _git(wt, "add", "package.json")
    _file(os.path.join(wt, "node_modules", "dep"), "index.js")

    assert _paths(wt) == [os.path.join(wt, "node_modules")]


def test_missing_git_binary_declines_rather_than_offers(tmp_path, monkeypatch):
    root = _repo(str(tmp_path))
    _project(root, "myproject")

    def boom(*a, **k):
        raise FileNotFoundError("git")

    monkeypatch.setattr(dev_junk.subprocess, "run", boom)

    assert _paths(root) == []


def test_hung_git_declines_rather_than_offers(tmp_path, monkeypatch):
    """A hang must be bounded and must decline — so the call has to CARRY the
    timeout, not merely handle the exception."""
    root = _repo(str(tmp_path))
    _project(root, "myproject")
    seen = []

    def hang(*a, **k):
        seen.append(k.get("timeout"))
        raise subprocess.TimeoutExpired(cmd="git", timeout=dev_junk.GIT_TIMEOUT_SECONDS)

    monkeypatch.setattr(dev_junk.subprocess, "run", hang)

    assert _paths(root) == []
    assert seen and all(t == dev_junk.GIT_TIMEOUT_SECONDS for t in seen), seen


def test_application_bundle_is_installed_software_anywhere(tmp_path):
    """HOME_INSTALL_ROOTS cannot reach the external volume; a .app bundle with a
    tracked manifest inside a checkout must still be declined."""
    root = _repo(str(tmp_path))
    wanted = _project(root, "myproject")
    res = os.path.join(root, "Applications", "Foo.app", "Contents", "Resources")
    _repo(res)
    _file(res, "package.json", "{}")
    _git(res, "add", "package.json")
    _file(os.path.join(res, "node_modules", "dep"), "index.js")

    assert _paths(root) == [wanted]


def test_git_ceiling_directories_is_honoured(tmp_path, monkeypatch):
    """GIT_CEILING_DIRECTORIES *restricts* discovery — stripping it would widen
    the search past a boundary the user set deliberately."""
    root = _repo(str(tmp_path))
    _project(root, "myproject")
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", root)

    assert _paths(os.path.join(root, "myproject")) == []


def test_tracked_but_deleted_manifest_is_not_evidence(tmp_path):
    """`ls-files` reports index entries, not files: a tracked package.json that
    has been deleted from the working tree must not vouch for node_modules."""
    root = _repo(str(tmp_path))
    wanted = _project(root, "keeper")
    gone = os.path.join(root, "gone")
    _file(gone, "package.json", "{}")
    _git(root, "add", "gone/package.json")
    _git(root, "commit", "-qm", "add")
    os.remove(os.path.join(gone, "package.json"))
    _file(os.path.join(gone, "node_modules", "dep"), "index.js")

    assert _paths(root) == [wanted]


def test_git_is_queried_once_per_directory_across_scan_roots(tmp_path, monkeypatch):
    """One cache and one budget for the whole scan, not one per configured root."""
    root = _repo(str(tmp_path))
    _project(root, "a")
    calls = []
    real_run = subprocess.run

    def counting(*a, **k):
        calls.append(a[0][2])          # the `-C <dir>` argument
        return real_run(*a, **k)

    monkeypatch.setattr(dev_junk.subprocess, "run", counting)
    monkeypatch.setattr(dev_junk, "DEV_SCAN_PATHS", [root, root])
    monkeypatch.setattr(dev_junk, "XCODE_DERIVED", str(tmp_path / "nope"))
    monkeypatch.setattr(dev_junk, "PIP_CACHE", str(tmp_path / "nope"))
    monkeypatch.setattr(dev_junk, "NPM_CACHE", str(tmp_path / "nope"))

    result = dev_junk.scan()

    # the root is listed twice, so the artefact is found twice — but git is
    # asked about each directory only once, because one cache spans the scan
    assert len(result["items"]) == 2
    assert len(calls) >= 1, "git was never consulted"
    assert len(calls) == len(set(calls)), calls


def test_git_budget_counts_git_time_and_stops_further_calls(tmp_path, monkeypatch):
    """The budget must bound time spent IN GIT and apply across candidates —
    a per-call timeout alone allows N x GIT_TIMEOUT_SECONDS."""
    root = _repo(str(tmp_path))
    for name in ("a", "b", "c"):
        _project(root, name)
    calls = []

    class _Done:
        returncode = 1
        stdout = b""
        stderr = b"fatal: not a git repository"

    def slow(*a, **k):
        calls.append(a[0][2])
        time.sleep(0.05)
        return _Done()

    monkeypatch.setattr(dev_junk.subprocess, "run", slow)
    monkeypatch.setattr(dev_junk, "GIT_SCAN_BUDGET_SECONDS", 0.04)

    assert _paths(root) == []
    assert len(calls) == 1, calls   # budget spent by the first call


def test_scan_reports_when_the_git_budget_runs_out(tmp_path, monkeypatch):
    root = _repo(str(tmp_path))
    for name in ("a", "b"):
        _project(root, name)

    class _Done:
        returncode = 1
        stdout = b""
        stderr = b"fatal: not a git repository"

    def slow(*a, **k):
        time.sleep(0.05)
        return _Done()

    monkeypatch.setattr(dev_junk.subprocess, "run", slow)
    monkeypatch.setattr(dev_junk, "GIT_SCAN_BUDGET_SECONDS", 0.04)
    monkeypatch.setattr(dev_junk, "DEV_SCAN_PATHS", [root])
    for const in ("XCODE_DERIVED", "PIP_CACHE", "NPM_CACHE"):
        monkeypatch.setattr(dev_junk, const, str(tmp_path / "nope"))

    assert "incomplete" in dev_junk.scan()["suggestion"]


def test_an_operational_git_failure_is_degraded_not_a_plain_no(tmp_path, monkeypatch):
    """`not a git repository` is an ordinary answer; dubious ownership is not."""
    root = _repo(str(tmp_path))
    _project(root, "myproject")

    class _Refused:
        returncode = 128
        stdout = b""
        stderr = b"fatal: detected dubious ownership in repository"

    monkeypatch.setattr(dev_junk.subprocess, "run", lambda *a, **k: _Refused())
    monkeypatch.setattr(dev_junk, "DEV_SCAN_PATHS", [root])
    for const in ("XCODE_DERIVED", "PIP_CACHE", "NPM_CACHE"):
        monkeypatch.setattr(dev_junk, const, str(tmp_path / "nope"))

    assert "incomplete" in dev_junk.scan()["suggestion"]


def test_a_plain_non_repository_answer_is_not_degraded(tmp_path, monkeypatch):
    outside = str(tmp_path / "outside")
    _file(outside, "package.json", "{}")
    _file(os.path.join(outside, "node_modules", "dep"), "index.js")
    monkeypatch.setattr(dev_junk, "DEV_SCAN_PATHS", [outside])
    for const in ("XCODE_DERIVED", "PIP_CACHE", "NPM_CACHE"):
        monkeypatch.setattr(dev_junk, const, str(tmp_path / "nope"))

    result = dev_junk.scan()

    assert result["items"] == []
    assert "incomplete" not in result["suggestion"], result["suggestion"]


def test_literal_pathspecs_cannot_silently_empty_the_evidence(tmp_path, monkeypatch):
    """GIT_LITERAL_PATHSPECS=1 makes `:(glob)*` a literal filename: git exits 0
    with no output, so every candidate is declined and the scan still calls
    itself complete."""
    root = _repo(str(tmp_path))
    wanted = _project(root, "myproject")
    monkeypatch.setenv("GIT_LITERAL_PATHSPECS", "1")

    assert _paths(root) == [wanted]


def test_bytecode_beside_a_tracked_non_source_file_not_offered(tmp_path):
    """A checkout holding only a tracked README and source-stripped bytecode —
    outside every marker — is exactly the frozen-application shape."""
    root = str(tmp_path)
    wanted = os.path.join(_repo(os.path.join(root, "work")), "src", "__pycache__")
    _file(os.path.dirname(wanted), "mod.py", "x = 1\n")
    _git(os.path.join(root, "work"), "add", "src/mod.py")
    _file(wanted, "mod.cpython-312.pyc")

    shipped = _repo(os.path.join(root, "vendor-tool", "lib"))   # README only
    _file(os.path.join(shipped, "__pycache__"), "mod.cpython-312.pyc")
    _file(shipped, "orphan.pyc")

    assert _paths(root) == [wanted]


def test_untracked_python_tree_without_a_marker_not_offered(tmp_path):
    """Git directness, not the .venv marker, must carry this one."""
    root = _repo(str(tmp_path))
    _file(os.path.join(root, "src"), "mod.py", "x = 1\n")
    _git(root, "add", "src/mod.py")
    wanted = os.path.join(root, "src", "__pycache__")
    _file(wanted, "mod.cpython-312.pyc")

    vendored = os.path.join(root, "third_party", "flask")       # no marker
    _file(vendored, "app.py", "x = 1\n")
    _file(os.path.join(vendored, "__pycache__"), "app.cpython-312.pyc")

    assert _paths(root) == [wanted]


def test_every_redirecting_git_variable_is_stripped(tmp_path, monkeypatch):
    """Causal cover for all of _GIT_ENV_STRIP, not just GIT_DIR."""
    root = _repo(str(tmp_path))
    _project(root, "myproject")
    seen = {}

    def capture(*a, **k):
        seen.update(k["env"])
        raise FileNotFoundError("git")

    # named literally, so a variable dropped from _GIT_ENV_STRIP is caught
    must_go = (
        "GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_DISCOVERY_ACROSS_FILESYSTEM", "GIT_NAMESPACE", "GIT_PREFIX",
        "GIT_LITERAL_PATHSPECS", "GIT_GLOB_PATHSPECS", "GIT_NOGLOB_PATHSPECS",
        "GIT_ICASE_PATHSPECS",
    )
    for var in must_go:
        monkeypatch.setenv(var, "1")
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", "/must/reach/git")
    monkeypatch.setattr(dev_junk.subprocess, "run", capture)

    _paths(root)

    assert not (set(must_go) & set(seen)), sorted(set(must_go) & set(seen))
    assert seen.get("GIT_CEILING_DIRECTORIES") == "/must/reach/git"


def test_scan_reports_when_git_could_not_be_consulted(tmp_path, monkeypatch):
    """Fail-closed selection is silent; an incomplete scan must not read as a
    clean machine."""
    root = _repo(str(tmp_path))
    _project(root, "myproject")

    def boom(*a, **k):
        raise FileNotFoundError("git")

    monkeypatch.setattr(dev_junk.subprocess, "run", boom)
    monkeypatch.setattr(dev_junk, "DEV_SCAN_PATHS", [root])
    for const in ("XCODE_DERIVED", "PIP_CACHE", "NPM_CACHE"):
        monkeypatch.setattr(dev_junk, const, str(tmp_path / "nope"))

    result = dev_junk.scan()

    assert result["items"] == []
    assert "incomplete" in result["suggestion"], result["suggestion"]


def test_scan_says_nothing_about_completeness_when_git_works(tmp_path, monkeypatch):
    root = _repo(str(tmp_path))
    _project(root, "myproject")
    monkeypatch.setattr(dev_junk, "DEV_SCAN_PATHS", [root])
    for const in ("XCODE_DERIVED", "PIP_CACHE", "NPM_CACHE"):
        monkeypatch.setattr(dev_junk, const, str(tmp_path / "nope"))

    result = dev_junk.scan()

    assert len(result["items"]) == 1
    assert "incomplete" not in result["suggestion"], result["suggestion"]


def test_a_project_under_a_home_install_root_is_deliberately_skipped(tmp_path, monkeypatch):
    """Documented trade-off, pinned so it cannot change silently: ~/bin, ~/opt,
    ~/go, ~/.config and ~/Library are treated as installed-only, so a genuine
    project living there is never offered."""
    home = str(tmp_path / "home")
    monkeypatch.setenv("HOME", home)
    proj = _repo(os.path.join(home, "go", "src", "mine"))
    _file(proj, "package.json", "{}")
    _git(proj, "add", "package.json")
    _file(os.path.join(proj, "node_modules", "dep"), "index.js")

    assert _paths(home) == []


MUST_BE_DENIED = (
    "/.vscode/", "/.cursor/", "/.codex/", "/.claude/plugins/", "/.npm/",
    "/.nvm/", "/.cache/", "/.cargo/", "/.local/share/", "/.venv/",
    "/site-packages/", "/library/application support/",
)
MUST_BE_PY_EVIDENCE = ("pyproject.toml", "setup.py", "pytest.ini", "requirements.txt")


def test_the_deny_lists_still_contain_what_this_fix_was_about():
    """A literal floor: derived-only coverage cannot notice a deleted entry."""
    missing = [m for m in MUST_BE_DENIED if m not in dev_junk.INSTALLED_SOFTWARE_MARKERS]
    assert not missing, missing
    assert ".app" in dev_junk.BUNDLE_SUFFIXES
    assert set(MUST_BE_PY_EVIDENCE) <= dev_junk.PY_PROJECT_FILES
    for root in ("Library", "bin", ".local"):
        assert root in dev_junk.HOME_INSTALL_ROOTS, root


def test_every_installed_software_marker_is_matched(tmp_path):
    """Each entry of all three deny-lists, not just the two used in fixtures."""
    assert dev_junk.INSTALLED_SOFTWARE_MARKERS, "deny-list emptied"
    for marker in dev_junk.INSTALLED_SOFTWARE_MARKERS:
        path = "/somewhere" + marker + "pkg"
        assert dev_junk._is_installed_software_path(path), marker
    for suffix in dev_junk.BUNDLE_SUFFIXES:
        assert dev_junk._is_installed_software_path(f"/somewhere/Thing{suffix}/x"), suffix
    home = os.path.realpath(os.path.expanduser("~"))
    for root in dev_junk.HOME_INSTALL_ROOTS:
        assert dev_junk._is_installed_software_path(os.path.join(home, root, "x")), root
    assert not dev_junk._is_installed_software_path("/Volumes/Ext Data/VSC Projects/x")


def test_every_py_project_file_is_evidence_for_a_tool_cache(tmp_path):
    assert dev_junk.PY_PROJECT_FILES, "evidence set emptied"
    for i, name in enumerate(sorted(dev_junk.PY_PROJECT_FILES)):
        root = _repo(str(tmp_path / f"r{i}"))
        _file(root, name, "x\n")
        _git(root, "add", name)
        _file(os.path.join(root, ".pytest_cache"), "lastfailed")

        assert _paths(root) == [os.path.join(root, ".pytest_cache")], name


def test_dotted_module_bytecode_needs_its_own_source(tmp_path):
    """Python maps `pkg.mod.py` to `pkg.mod.cpython-312.pyc`. A tracked
    `pkg.py` must not authorise bytecode belonging to a stripped `pkg.mod.py`."""
    root = _repo(str(tmp_path))
    _file(root, "pkg.py", "x = 1\n")
    _git(root, "add", "pkg.py")
    _file(root, "pkg.mod.cpython-312.pyc")
    _file(root, "pkg.cpython-312.pyc")

    assert _paths(root) == [os.path.join(root, "pkg.cpython-312.pyc")]


def test_dotted_module_bytecode_offered_when_its_source_is_tracked(tmp_path):
    root = _repo(str(tmp_path))
    _file(root, "pkg.mod.py", "x = 1\n")
    _git(root, "add", "pkg.mod.py")
    _file(root, "pkg.mod.cpython-312.opt-1.pyc")

    assert _paths(root) == [os.path.join(root, "pkg.mod.cpython-312.opt-1.pyc")]


def test_tool_caches_need_python_evidence(tmp_path):
    """The negative half of the .mypy_cache/.pytest_cache branch, outside any
    deny-listed path: a repo holding only a README proves nothing."""
    root = str(tmp_path)
    proj = _repo(os.path.join(root, "work"))
    _file(proj, "pyproject.toml", "[project]\n")
    _git(proj, "add", "pyproject.toml")
    _file(os.path.join(proj, ".pytest_cache"), "lastfailed")

    docs = _repo(os.path.join(root, "docs-only"))          # README only
    _file(os.path.join(docs, ".pytest_cache"), "lastfailed")
    _file(os.path.join(docs, ".mypy_cache"), "cache.json")

    assert _paths(root) == [os.path.join(proj, ".pytest_cache")]


def test_a_translated_git_error_is_still_an_ordinary_no(tmp_path, monkeypatch):
    """git's diagnostics are localised; the classification must not be."""
    outside = str(tmp_path / "outside")
    _file(outside, "package.json", "{}")
    _file(os.path.join(outside, "node_modules", "dep"), "index.js")
    monkeypatch.setenv("LC_ALL", "fr_FR.UTF-8")
    monkeypatch.setenv("LANG", "fr_FR.UTF-8")
    monkeypatch.setattr(dev_junk, "DEV_SCAN_PATHS", [outside])
    for const in ("XCODE_DERIVED", "PIP_CACHE", "NPM_CACHE"):
        monkeypatch.setattr(dev_junk, const, str(tmp_path / "nope"))

    result = dev_junk.scan()

    assert result["items"] == []
    assert "incomplete" not in result["suggestion"], result["suggestion"]
