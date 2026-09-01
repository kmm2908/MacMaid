import os
import re
import subprocess
import time
from modules.base import make_result, make_item, TRASH_DIR_NAMES, is_in_trash, is_removable
import config as cfg

DEV_SCAN_PATHS = [os.path.expanduser(p) for p in (cfg.get("dev_scan_paths") or ["~/"])]
XCODE_DERIVED = os.path.expanduser("~/Library/Developer/Xcode/DerivedData")
PIP_CACHE = os.path.expanduser("~/Library/Caches/pip")
NPM_CACHE = os.path.expanduser("~/.npm/_cacache")

TARGET_DIRS = {"node_modules", "__pycache__", ".mypy_cache", ".pytest_cache"}
TARGET_EXTS = {".pyc"}


def _dir_size(path: str) -> int:
    total = 0
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, f))
            except OSError:
                pass
    return total


# Second condition, deliberately belt-and-braces: some installed software IS a
# git checkout (a tool installed by `git clone` + `npm install`), which the
# tracked-neighbour test alone cannot tell from a project. These are the places
# software installs itself to. Matched as path segments, case-insensitively,
# against the RESOLVED path so a relative root or a symlink cannot slip past.
INSTALLED_SOFTWARE_MARKERS = (
    "/.vscode/", "/.vscode-server/", "/.cursor/", "/.codex/", "/.claude/plugins/",
    "/.npm/", "/.nvm/", "/.bun/", "/.deno/", "/.cache/", "/.cargo/", "/.gem/",
    "/.pyenv/", "/.rbenv/", "/.nodenv/", "/.oh-my-zsh/", "/.krew/",
    "/.local/share/", "/.local/lib/", "/.local/bin/",
    "/library/application support/", "/library/python/", "/library/caches/",
    "/.venv/", "/venv/", "/site-packages/",
)

# Whole subtrees of $HOME that hold installed things, never developed ones.
HOME_INSTALL_ROOTS = (
    ".config", ".local", ".asdf", ".sdkman", ".docker", ".terraform.d",
    "Applications", "Library", "bin", "opt", "sdk", "go",
)

# A macOS bundle is installed software wherever it lives — including on the
# external volume, which HOME_INSTALL_ROOTS cannot reach.
BUNDLE_SUFFIXES = (".app", ".framework", ".bundle", ".plugin", ".xpc")

# Variables that REDIRECT git to another repository or index. `git -C` does not
# override them, so an inherited one would let an unrelated repository's index
# answer for a directory that is in no repository at all.
# GIT_CEILING_DIRECTORIES is deliberately NOT here: it *restricts* discovery, so
# stripping it would widen the search past a boundary the user set on purpose.
_GIT_ENV_STRIP = (
    "GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_DISCOVERY_ACROSS_FILESYSTEM", "GIT_NAMESPACE", "GIT_PREFIX",
    # These change what `:(glob)*` MEANS. GIT_LITERAL_PATHSPECS=1 makes it a
    # literal filename, which matches nothing and exits 0 — every candidate
    # declined, and the scan reporting itself complete.
    "GIT_LITERAL_PATHSPECS", "GIT_GLOB_PATHSPECS", "GIT_NOGLOB_PATHSPECS",
    "GIT_ICASE_PATHSPECS",
)

GIT_TIMEOUT_SECONDS = 10
# A scan-wide ceiling on time spent IN GIT, not wall clock: a malfunctioning git
# would otherwise cost `candidate directories × GIT_TIMEOUT_SECONDS`, while a
# wall-clock deadline would instead be eaten by a slow filesystem walk and
# decline candidates git never got to look at. Past it, everything is declined —
# under-cleaning is the safe direction.
# Measured 2026-09-01 on the real configured roots (~/ and /Volumes/Ext Data):
# 313 candidate directories, 1.7s of git time, 69s of wall clock. 60s is ~35x
# the observed need, so it bounds a malfunction without touching a normal run.
GIT_SCAN_BUDGET_SECONDS = 60
# Neither is ever a resolved path, so neither can collide with a cache key.
_SPENT_KEY = ""
_DEGRADED_KEY = "?"

# Tracked evidence that bytecode and tool caches here are regenerable from
# source in this very directory. A frozen application ships .pyc with the .py
# stripped — deleting one of those is permanent, and a tracked README is not
# evidence of anything.
PY_PROJECT_FILES = frozenset({
    "pyproject.toml", "setup.py", "setup.cfg", "tox.ini", "pytest.ini",
    "mypy.ini", "requirements.txt", "Pipfile", "conftest.py",
})


def _new_cache() -> dict:
    return {_SPENT_KEY: 0.0, _DEGRADED_KEY: 0}


def _is_installed_software_path(path: str) -> bool:
    """Match against the RESOLVED path: a relative scan root such as `.vscode`,
    or a symlink pointing into one, would otherwise sidestep every marker."""
    real = os.path.realpath(path).lower()
    if any(marker in real + os.sep for marker in INSTALLED_SOFTWARE_MARKERS):
        return True
    if any(
        seg.endswith(BUNDLE_SUFFIXES)
        for seg in real.split(os.sep)
    ):
        return True
    home = os.path.realpath(os.path.expanduser("~")).lower()
    return any(
        (real + os.sep).startswith(os.path.join(home, d.lower()) + os.sep)
        for d in HOME_INSTALL_ROOTS
    )


def _tracked_names(parent: str, cache: dict) -> frozenset:
    """The names git tracks *directly* in `parent` — not recursively.

    Asking git itself is what makes the rule hold: an ancestor `.git` is not
    enough, because installed software routinely lives untracked and ignored
    inside a checkout (`~/.claude/plugins/cache/…`, `.venv/…/site-packages/…`),
    and a `.git` at a broad scan root would otherwise bless everything beneath
    it. `:(glob)*` is a pathspec whose `*` does not cross a directory boundary,
    so the listing stays bounded to `parent` however large the repository is.

    Anything git cannot answer for — no repository, no git binary, a malformed
    or dangling marker, a hang — comes back empty, which is a decline.
    """
    key = os.path.realpath(parent)
    if key in cache:
        return cache[key]
    names: frozenset = frozenset()
    remaining = GIT_SCAN_BUDGET_SECONDS - cache.get(_SPENT_KEY, 0.0)
    if remaining <= 0:
        cache[_DEGRADED_KEY] = cache.get(_DEGRADED_KEY, 0) + 1
        cache[key] = names
        return names
    env = {k: v for k, v in os.environ.items() if k not in _GIT_ENV_STRIP}
    # git's diagnostics are translated; the non-repository answer is matched on
    # its text below, so pin the locale rather than the reader's language.
    env.update(LC_ALL="C", LANG="C", LANGUAGE="")
    started = time.monotonic()
    try:
        r = subprocess.run(
            ["git", "-C", key, "ls-files", "-z", "--", ":(glob)*"],
            capture_output=True, env=env, check=False,
            # the remaining budget, so the ceiling is a ceiling
            timeout=min(GIT_TIMEOUT_SECONDS, remaining),
        )
        if r.returncode == 0:
            names = frozenset(
                n.decode("utf-8", "replace")
                for n in r.stdout.split(b"\0") if n
            )
        elif b"not a git repository" not in r.stderr:
            # THAT is an ordinary answer for most of the filesystem. Anything
            # else — dubious ownership, a corrupt index, a permission problem —
            # means the question went unanswered, which is not the same as "no".
            cache[_DEGRADED_KEY] = cache.get(_DEGRADED_KEY, 0) + 1
    except (OSError, ValueError, subprocess.SubprocessError):
        cache[_DEGRADED_KEY] = cache.get(_DEGRADED_KEY, 0) + 1
    finally:
        cache[_SPENT_KEY] = cache.get(_SPENT_KEY, 0.0) + (time.monotonic() - started)
    # An index entry is not a file: a tracked path deleted from the working tree,
    # replaced by a directory, or left out by a sparse checkout, still appears
    # in `ls-files`.
    cache[key] = frozenset(n for n in names if os.path.isfile(os.path.join(key, n)))
    return cache[key]


# Only a RECOGNISED interpreter tag is stripped. Splitting on the first dot
# would map `pkg.mod.cpython-312.pyc` to `pkg.py`, letting a tracked `pkg.py`
# authorise deletion of bytecode belonging to a `pkg.mod.py` that no longer
# exists — the exact source-stripped case this rule is for.
_CACHE_TAG = re.compile(
    r"\.(?:cpython|pypy|jython|ironpython|graalpy)-[^.]+(?:\.opt-\d+)?$",
    re.IGNORECASE,
)


def _source_of(pyc_name: str) -> str:
    """`mod.cpython-312.pyc`, `pkg.mod.cpython-312.opt-1.pyc`, `mod.pyc`."""
    return _CACHE_TAG.sub("", pyc_name[: -len(".pyc")]) + ".py"


def _bytecode_is_regenerable(name: str, parent: str, tracked: frozenset) -> bool:
    """Every .pyc must map to tracked source that is still on disk.

    A frozen application ships bytecode with the source stripped; deleting one
    of those is permanent. An unrelated tracked `mod.py` in the same directory
    says nothing about `stale.pyc` sitting beside it.
    """
    if name.endswith(".pyc"):
        return _source_of(name) in tracked
    try:
        entries = os.listdir(os.path.join(parent, name))
    except OSError:
        return False
    pycs = [e for e in entries if e.endswith(".pyc")]
    return bool(pycs) and all(_source_of(e) in tracked for e in pycs)


def _is_project_junk(name: str, parent: str, cache: dict) -> bool:
    """Fail closed: offer an artefact only when it is provably project junk.

    Deleting a dependency produces no error anywhere — the cleaner reports
    success and so does the broken caller — so an undecidable path is declined.
    """
    if _is_installed_software_path(parent):
        return False
    tracked = _tracked_names(parent, cache)
    if name == "node_modules":
        # The manifest itself must supply the git evidence: a tracked README
        # beside an installed, untracked package.json is not a project.
        return "package.json" in tracked
    if name == "__pycache__" or name.endswith(".pyc"):
        return _bytecode_is_regenerable(name, parent, tracked)
    # .mypy_cache / .pytest_cache are tool caches, not compiled artefacts:
    # tracked Python source or a tracked project file is the right evidence.
    return bool(tracked & PY_PROJECT_FILES) or any(n.endswith(".py") for n in tracked)


def _scan_path(base: str, items: list, cache: dict | None = None) -> None:
    if not os.path.isdir(base) or is_in_trash(base):
        return
    git_cache: dict = _new_cache() if cache is None else cache
    for dirpath, dirnames, filenames in os.walk(base, topdown=True):
        # Never descend into a trash folder — its contents are already deleted.
        for d in list(dirnames):
            if d in TRASH_DIR_NAMES:
                dirnames.remove(d)
        for d in list(dirnames):
            if d in TARGET_DIRS:
                full = os.path.join(dirpath, d)
                dirnames.remove(d)  # don't recurse into it
                if not is_removable(full):
                    continue
                if not _is_project_junk(d, dirpath, git_cache):
                    continue
                size = _dir_size(full)
                items.append(make_item(full, size, f"{d} ({os.path.basename(dirpath)})"))
        for f in filenames:
            if os.path.splitext(f)[1] in TARGET_EXTS:
                fp = os.path.join(dirpath, f)
                if not is_removable(fp):
                    continue
                if not _is_project_junk(f, dirpath, git_cache):
                    continue
                try:
                    items.append(make_item(fp, os.path.getsize(fp), f))
                except OSError:
                    pass


def scan() -> dict:
    items = []
    git_cache = _new_cache()  # one budget for the whole scan, not one per root
    for path in DEV_SCAN_PATHS:
        _scan_path(path, items, git_cache)
    for static_path in [XCODE_DERIVED, PIP_CACHE, NPM_CACHE]:
        if os.path.isdir(static_path):
            size = _dir_size(static_path)
            if size > 0:
                items.append(make_item(static_path, size, os.path.basename(static_path)))
    total = sum(i["size_bytes"] for i in items)
    size_gb = total / (1024 ** 3)
    suggestion = f"Remove {len(items)} dev artefacts ({size_gb:.1f} GB)"
    degraded = git_cache.get(_DEGRADED_KEY, 0)
    if degraded:
        # Fail-closed selection is silent by design; say so, or an incomplete
        # scan is indistinguishable from a clean machine.
        suggestion += (
            f" — incomplete: git could not be consulted for {degraded}"
            " directories, so some project junk was not offered"
        )
    return make_result(
        "Dev Junk",
        "safe",
        action="trash",
        suggestion=suggestion,
        items=items,
    )
