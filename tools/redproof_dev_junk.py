#!/usr/bin/env python3
"""Prove the dev_junk safety tests can FAIL, by breaking the rule on purpose.

A passing suite says the code does what the tests describe. It does not say the
tests would notice if the code stopped doing it — and this module has now
selected the wrong set twice (2026-08-30 installed software, 2026-09-08 live
projects), each time silently, because deleting a dependency tree raises no
error anywhere.

So: mutate one rule at a time, run the suite, and require the named tests to go
red. A mutant nothing catches is a rule nothing guards.

    python3 tools/redproof_dev_junk.py        # exit 0 = every mutant caught

**Mutations are applied to a COPY**, never to the working tree: the sources are
copied to a temporary directory and pytest runs there, so an interrupted run or
a concurrent edit cannot lose work. The checkout is never written to.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYTEST = os.environ.get("REDPROOF_PYTEST", "/Users/fred/Library/Python/3.12/bin/pytest")
_IGNORE = shutil.ignore_patterns(".git", "node_modules", "__pycache__", ".venv",
                                 "venv", ".pytest_cache", ".mypy_cache")
_TALLY = re.compile(r"(\d+) (passed|failed|error|errors|skipped)")


# (label, file, exact text to replace, replacement, tests that MUST go red)
# The list is a floor, not an exact set: breaking one safety rule legitimately
# trips other tests, and demanding an exact match would make the harness brittle
# without making it stricter. A mutant is caught when every named test is red.
MUTANTS = [
    ("no dormancy gate — the 2026-09-01 rule that trashed live projects",
     "modules/dev_junk.py",
     "        window = _dormant_days()\n"
     "        age = _head_age_days(parent, cache)\n"
     "        if age is None or age < window:\n"
     "            return False\n"
     "        return not _worked_on_recently(parent, window, cache)",
     "        return True",
     ["test_live_project_node_modules_is_not_offered",
      "test_only_the_dormant_one_comes_back_from_a_single_scan",
      "test_a_project_one_day_short_of_the_window_is_spared",
      "test_a_fresh_clone_of_an_old_project_is_spared",
      "test_an_old_checkout_with_work_in_flight_is_spared",
      "test_a_manifest_edited_today_spares_the_project",
      "test_the_window_comes_from_config",
      "test_a_window_that_would_switch_the_guard_off_falls_back_to_the_default",
      "test_repository_with_no_commits_yet_is_declined_not_counted_as_degraded",
      "test_exhausted_git_budget_declines_and_is_counted",
      "test_an_unanswerable_status_counts_as_activity",
      "test_a_newer_commit_on_another_branch_spares_the_project"]),

    ("gate inverted — dormant projects spared, live ones taken",
     "modules/dev_junk.py",
     "        if age is None or age < window:",
     "        if age is None or age >= window:",
     # The live-project tests are NOT here: the activity vetoes catch those on
     # their own, which is the defence-in-depth working rather than a gap.
     ["test_dormant_project_node_modules_is_still_offered",
      "test_only_the_dormant_one_comes_back_from_a_single_scan",
      "test_the_window_comes_from_config",
      "test_finds_node_modules",
      "test_installed_extension_inside_a_repo_not_offered",
      "test_installed_software_that_is_itself_a_checkout_not_offered",
      "test_marker_excludes_a_fully_tracked_installed_checkout",
      "test_home_install_root_excludes_a_tracked_checkout",
      "test_node_modules_outside_any_repo_not_offered",
      "test_empty_git_marker_is_not_a_repository",
      "test_dangling_gitdir_file_is_not_a_repository",
      "test_loose_pyc_outside_any_repo_not_offered",
      "test_project_node_modules_still_offered",
      "test_linked_git_worktree_is_recognised",
      "test_application_bundle_is_installed_software_anywhere",
      "test_tracked_but_deleted_manifest_is_not_evidence",
      "test_git_is_queried_once_per_directory_across_scan_roots",
      "test_literal_pathspecs_cannot_silently_empty_the_evidence",
      "test_scan_says_nothing_about_completeness_when_git_works",
      "test_scan_path_skips_home_trash"]),

    ("local activity ignored — an old commit date taken as proof nobody is here",
     "modules/dev_junk.py",
     "        return not _worked_on_recently(parent, window, cache)",
     "        return True",
     ["test_a_fresh_clone_of_an_old_project_is_spared",
      "test_an_old_checkout_with_work_in_flight_is_spared",
      "test_a_manifest_edited_today_spares_the_project",
      "test_an_unanswerable_status_counts_as_activity"]),

    ("an unanswerable git status treated as clean",
     "modules/dev_junk.py",
     "    return _has_uncommitted_changes(parent, cache) is not False",
     "    return _has_uncommitted_changes(parent, cache) is True",
     ["test_an_unanswerable_status_counts_as_activity"]),

    ("only HEAD read, not every ref — a stale branch reads as abandoned",
     "modules/dev_junk.py",
     '["log", "--all", "-1", "--format=%ct"]',
     '["log", "-1", "--format=%ct"]',
     ["test_a_newer_commit_on_another_branch_spares_the_project"]),

    ("an unanswerable git treated as dormant",
     "modules/dev_junk.py",
     "        if age is None or age < window:\n            return False",
     "        if age is not None and age < window:\n            return False",
     # Not the unborn-HEAD test: a repository with no commits and a tracked
     # manifest is necessarily one with staged work, so the dirty-tree veto
     # answers for it first. The budget case is the one that isolates this.
     ["test_exhausted_git_budget_declines_and_is_counted"]),

    ("config taken at face value — 0 or a bool switches the guard off",
     "modules/dev_junk.py",
     "    v = cfg.get(\"dev_junk_dormant_days\")\n"
     "    if isinstance(v, bool) or not isinstance(v, (int, float)):\n"
     "        return float(DORMANT_DAYS_DEFAULT)\n"
     "    if not math.isfinite(v) or v < 1:\n"
     "        return float(DORMANT_DAYS_DEFAULT)\n"
     "    return float(v)",
     "    v = cfg.get(\"dev_junk_dormant_days\")\n"
     "    return float(DORMANT_DAYS_DEFAULT if v is None else v)",
     ["test_a_window_that_would_switch_the_guard_off_falls_back_to_the_default"]),

    ("dormancy wrongly applied to bytecode too",
     "modules/dev_junk.py",
     '    if name == "__pycache__" or name.endswith(".pyc"):\n'
     "        return _bytecode_is_regenerable(name, parent, tracked)",
     '    if name == "__pycache__" or name.endswith(".pyc"):\n'
     "        age = _head_age_days(parent, cache)\n"
     "        return (age is not None and age >= _dormant_days()) and \\\n"
     "            _bytecode_is_regenerable(name, parent, tracked)",
     ["test_bytecode_in_a_live_project_is_still_offered"]),

    ("the scan stops recording what the directory looked like",
     "modules/dev_junk.py",
     '                meta = {"mtime": seen_at} if d == "node_modules" else None',
     "                meta = None",
     ["test_the_offered_directory_records_what_it_looked_like"]),

    ("the cleaner stops re-checking before it deletes",
     "cleaner.py",
     "            if not _unchanged_since_scan(item):\n"
     "                result.skipped += 1\n"
     "                result.changed_paths.append(path)\n"
     "                continue\n",
     "",
     ["test_a_directory_written_to_since_the_scan_is_not_cleaned"]),
    ("the baseline read AFTER the size walk, so an install during it closes the race",
     "modules/dev_junk.py",
     "                try:\n"
     "                    seen_at = os.path.getmtime(full)\n"
     "                except OSError:\n"
     "                    continue\n"
     "                if not _is_project_junk(d, dirpath, git_cache):\n"
     "                    continue\n"
     "                size = _dir_size(full)",
     "                if not _is_project_junk(d, dirpath, git_cache):\n"
     "                    continue\n"
     "                size = _dir_size(full)\n"
     "                try:\n"
     "                    seen_at = os.path.getmtime(full)\n"
     "                except OSError:\n"
     "                    continue",
     ["test_the_recorded_state_predates_the_size_walk"]),

    ("untracked and gitignored work beside the dependencies ignored",
     "modules/dev_junk.py",
     "        paths = [parent] + [e.path for e in os.scandir(parent)\n"
     "                            if os.path.basename(e.path) != \".git\"]",
     "        paths = [parent, os.path.join(parent, \"node_modules\"),\n"
     "                 os.path.join(parent, \"package.json\")]",
     ["test_untracked_work_beside_the_dependencies_spares_the_project"]),

    ("`.git` counted as activity, so this module's own queries look like work",
     "modules/dev_junk.py",
     "                            if os.path.basename(e.path) != \".git\"]",
     "                            ]",
     ["test_this_modules_own_git_queries_do_not_look_like_activity"]),

    ("a path left alone because it changed reported as an ordinary duplicate",
     "reporter.py",
     "    if result.changed_paths:\n"
     "        lines.append(f\"Left alone: {len(result.changed_paths)} path(s) changed between \"\n"
     "                     f\"the scan and the clean\")\n"
     "    covered = result.skipped - len(result.changed_paths)\n"
     "    if covered > 0:",
     "    covered = result.skipped\n"
     "    if covered > 0:",
     ["test_summary_separates_a_changed_path_from_a_duplicate"]),
]


def _run_suite(where: str) -> tuple:
    """(red test names, total tests accounted for, skipped, exit code).

    The total is what catches an abnormal run: a mutant that breaks an import
    collects nothing, exits non-zero and reports no FAILED lines at all, which
    would otherwise read exactly like 'nothing caught it'. Skips are counted
    separately because pytest renders one as `s` and still exits 0 — a baseline
    with a skip in it is a guard that quietly did not run.
    """
    r = subprocess.run(
        # -rfEs, not "-rf -rs": a second -r REPLACES the first, and the run then
        # prints no FAILED lines at all — which reads exactly like a mutant
        # nothing caught.
        [PYTEST, "tests/", "--tb=no", "-q", "-rfEs", "-p", "no:cacheprovider"],
        cwd=where, capture_output=True, text=True,
    )
    red = {line.split("::")[-1].split(" ")[0] for line in r.stdout.splitlines()
           if line.startswith(("FAILED", "ERROR"))}
    tally = _TALLY.findall(r.stdout)
    total = sum(int(n) for n, _ in tally)
    skipped = sum(int(n) for n, kind in tally if kind == "skipped")
    return red, total, skipped, r.returncode


def _copy() -> str:
    dst = os.path.join(tempfile.mkdtemp(prefix="redproof-"), "repo")
    shutil.copytree(ROOT, dst, ignore=_IGNORE, symlinks=True)
    return dst


def main() -> int:
    work = _copy()
    ok = True
    try:
        red, baseline, skipped, rc = _run_suite(work)
        if red or rc != 0 or baseline == 0 or skipped:
            print(f"BAD  the suite is not green to begin with "
                  f"(exit {rc}, {baseline} tests, {skipped} skipped, "
                  f"red: {sorted(red) or 'none'})")
            return 1
        print(f"baseline: {baseline} tests green, none skipped, "
              f"in the copy at {work}\n")
        for label, rel, old, new, expected in MUTANTS:
            src = os.path.join(work, rel)
            pristine = open(os.path.join(ROOT, rel), encoding="utf-8").read()
            if old not in pristine:
                print(f"BAD  anchor moved, mutant never applied: {label}")
                ok = False
                continue
            with open(src, "w", encoding="utf-8") as fh:
                fh.write(pristine.replace(old, new, 1))
            red, total, skipped, rc = _run_suite(work)
            with open(src, "w", encoding="utf-8") as fh:
                fh.write(pristine)
            missing = set(expected) - red
            abnormal = total != baseline or skipped
            good = not missing and not abnormal and rc != 0
            ok = ok and good
            print(f"{'OK ' if good else 'BAD'} {label}   ({len(red)} red)")
            if abnormal:
                print(f"       ABNORMAL RUN: {total} tests accounted for "
                      f"({skipped} skipped), expected {baseline} and no skips "
                      f"— the suite did not run properly")
            if rc == 0 and not missing:
                print("       NOT CAUGHT: the suite stayed green")
            if missing:
                print(f"       NOT CAUGHT: {sorted(missing)}")
    finally:
        shutil.rmtree(os.path.dirname(work), ignore_errors=True)
    print("\nredproof " + ("PASSED — every mutant was caught"
                           if ok else "FAILED — see the lines above"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
