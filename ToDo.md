# MacMaid — ToDo

macOS cleanup + system-health tool: 14 scan modules (caches, logs, trash, large files,
duplicates, dev junk, browsers, mail, login items, disk/memory/thermal, iOS backups,
Xcode sims), send2trash cleaner, Rich terminal UI, browser review UI (Flask +
`macmaid://` URL scheme), email report with review link, scheduler, history.
97 tests passing. See [STATUS.md](STATUS.md).

## Open items

### Manual testing gaps (from STATUS.md "Needs Testing")
- [ ] Run `python main.py` interactively end-to-end — needs a manual terminal
      (questionary uses the TTY directly, can't be driven headless).
- [ ] Test the Duplicates tab end-to-end in the browser UI: filter, sort, select,
      Move to Trash. UI confirmed loading (31,441 items) but the deletion flow has not
      been manually exercised.

### Deferred / future features
- [ ] Full browser UI — move the entire scan/report/clean flow into the browser (replace
      the Rich terminal output), surfacing all modules, not just Large & Old Files.
- [ ] Merge the `CleanUp` project — absorb `CC Dev/CleanUp/cleanup.py` (Downloads
      auto-cleaner with Finder-tag protection, 24h guard, notifications) as a new MacMaid
      module, then retire the standalone CleanUp project.
- [ ] Add a `config` subcommand or interactive config editor.
- [ ] Consider packaging for pip / Homebrew.
- [ ] Extend `--review` + the email review link to other `risk=review` modules beyond
      Large & Old Files and Duplicates, if any are added.

_Core is shipped and tested (97/97). The gaps above are TTY-only manual checks and
opt-in feature expansions, not blocking defects._
