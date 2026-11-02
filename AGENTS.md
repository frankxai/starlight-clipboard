# Starlight Clipboard repository guide

Maintainer: Starlight. Author: Codex. Created: 2026-10-31. Revision: v1.
Review state: local beta. Source: README.md and issue #4.

This repository contains the Windows clipboard collector, local library window,
installer and isolated tests. Read README.md before changing behavior.

Keep clipboard bodies, databases, backups, local capability tokens, browser
profiles and machine receipts outside Git. The default private runtime is
`~/.starlight/clipboard-index`. Use synthetic content in tests and public reports.

Preserve committed source captures when changing retention, export or migration.
Derived Markdown and image files are rebuildable caches. Use SQLite's online
backup API for a running database. Restore into a new destination and verify it
before changing the active runtime.

Run `py -3 -m unittest discover -s tests -v` and `py -3 clip.py self-test` for
persistence, privacy, migration or API changes. Parse install.ps1 with PowerShell
7 before installer changes. Use `-WhatIf` to inspect installation intent.

The collector owns the Windows clipboard lane. Inspect the install receipt and
process command before stopping an installed instance. Use `clips stop` for a
graceful stop. Never run a second collector against the real clipboard for QA;
the fixture server and temporary data roots support isolated testing.

Keep the local API authenticated and restricted to loopback. Honor protected
clipboard formats and excluded applications before reading payloads. Treat
classification as a suggestion; a copied prompt is not proof of submission.

Review changed interface files with the installed design checks and rendered
interaction checks when admitted. Independent review, reboot acceptance,
off-device recovery and shared-memory retrieval remain open in issue #4.
Keep changes in a draft PR until the applicable release checks pass.
