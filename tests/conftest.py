import os

import pytest

from modules.dev_junk import _GIT_ENV_STRIP


@pytest.fixture(autouse=True)
def isolate_git_env(request, monkeypatch):
    """Make the dev_junk tests independent of the invoking shell.

    Two groups, for two reasons:
      * `_GIT_ENV_STRIP` — variables that REDIRECT git or change what a
        pathspec means. Imported from production rather than copied, so the
        two cannot drift; production strips exactly these.
      * config and `GIT_CEILING_DIRECTORIES` — production deliberately honours
        both, so a value inherited from the developer's shell would decide the
        outcome of the positive tests. The tests that are *about* those inputs
        set them themselves, after this fixture has run.

    Scoped by module so a future test of git/environment behaviour elsewhere is
    not silently run under altered conditions.
    """
    if "dev_junk" not in request.module.__name__:
        return
    for var in (*_GIT_ENV_STRIP, "GIT_CEILING_DIRECTORIES"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
