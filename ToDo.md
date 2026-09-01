<!-- GENERATED FROM TRELLO — do not edit. Board 6a8724fa3e644cd94e6f0a61 · fetched 2026-09-01T17:28Z
     Cards: 8 · renderer v1 · Regenerate: trello sync MacMaid -->

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
## Review

- [ ] dev_junk trashes node_modules inside installed software (broke 6 VS Code extensions) <!-- card:mEU9eLek -->
      Root cause verified 2026-09-01. modules/dev_junk.py walks dev_scan_paths (~/ and /Volumes/Ext Data) and trashes EVERY node_modules it finds, with no exclusion for installed software. On 2026-08-30 16:14 it stripped node_modules from 5 VS Code extensions in ~/.vscode/extensions, which is why Code Spell Checker threw 'Configuration Loader Error: Failed to resolve @cspell/dict-en-gb/cspell-ext.json'. Also truncated: esbenp.prettier-vscode, peakchen90.open-html-in-browser, yzane.markdown-pdf, streetsidesoftware.code-spell-checker. All 5 restored by hand from marketplace VSIXs; they will break again on the next run. Today's scan ALSO lists 10 node_modules under hidden ~ dirs including ~/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules and ~/.codex/plugins/... - i.e. it can break the Codex CLI runtime that gates every commit on this machine. Fix: add an exclusion list to dev_junk (skip any node_modules whose path contains an installed-software root: ~/.vscode, ~/.vscode-insiders, ~/.cursor, ~/.codex, ~/.cache, ~/.npm/_npx, ~/Library/Application Support, /Applications), or better, only offer a node_modules whose parent dir contains a package.json AND sits under a git working tree. Regression test: assert a node_modules planted under ~/.vscode/extensions/<x>/ is NOT returned by dev_junk.scan().
      UPDATE 2026-09-01: a SIXTH extension was also stripped and was nearly missed. The first audit used `du`, which counts disk blocks, and scored ms-python.python at 97%; measured as the sum of file sizes it is 76%, with 7.4 MB of node_modules gone from out/client/node_modules — nested, so a top-level check misses it too. All six restored; see CC Dev/General/vscode-extensions-stripped-by-macmaid.md.
