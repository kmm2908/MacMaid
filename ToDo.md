<!-- GENERATED FROM TRELLO — do not edit. Board 6a8724fa3e644cd94e6f0a61 · fetched 2026-08-21T15:35Z
     Cards: 7 · renderer v1 · Regenerate: trello sync MacMaid -->

# MacMaid — backlog

The board is authoritative: https://trello.com/b/aFzZdqPQ/macmaid

Edits here are discarded on the next `trello sync`. To change something, move the
card, or run `trello work` / `trello done`.

## Backlog

- [ ] Consider packaging for pip / Homebrew. <!-- card:iR9xDyTm -->
- [ ] Test the Duplicates tab end-to-end in the browser UI: filter, sort, select, <!-- card:js35p4gA -->
      Move to Trash. UI confirmed loading (31,441 items) but the deletion flow has not
      been manually exercised.
- [ ] Full browser UI — move the entire scan/report/clean flow into the browser (replace <!-- card:lniVMHcS -->
      the Rich terminal output), surfacing all modules, not just Large & Old Files.
- [ ] Merge the `CleanUp` project — absorb `CC Dev/CleanUp/cleanup.py` (Downloads <!-- card:3yHbtDtc -->
      auto-cleaner with Finder-tag protection, 24h guard, notifications) as a new MacMaid
      module, then retire the standalone CleanUp project.
- [ ] Add a `config` subcommand or interactive config editor. <!-- card:EyNoGPT2 -->
- [ ] Extend `--review` + the email review link to other `risk=review` modules beyond <!-- card:N1G8HJ0O -->
      Large & Old Files and Duplicates, if any are added.
- [ ] Run `python main.py` interactively end-to-end — needs a manual terminal <!-- card:4J1ymHNX -->
      (questionary uses the TTY directly, can't be driven headless).
