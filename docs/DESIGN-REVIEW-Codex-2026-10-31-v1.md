# Starlight Clipboard design review, Codex, 2026-10-31, v1

Author and inline reviewer: Codex. Contributors: none. Review state: local beta; independent provider and native acceptance remain pending. Source: issue #4, README.md, Frank's liquid-glass direction and the exact interface SHA below.

Interface SHA256: `e347716d20d7137eb274ac5524b8d61e1ee67f05cf4b15dfdbec9240c7f2539b`. This identifies the rendered source independently of the later documentation commit.

## Decision and alternative

Extend the installed Windows collector and its authenticated local web palette. Preserve the dependency-free capture path and storage/recovery work. The useful outcome is finding, reading, reusing and filing an original quickly without losing an interrupted idea.

The conservative direction was a flat Windows utility; the selected direction adds Starlight glass chrome around a quiet reader. A Rust/Tauri application is the materially different alternative: it could improve packaging and native window integration, but introduces another runtime/build and migration surface. No measured speed, cost or competitive advantage is claimed. This slice implements and inspects the selected direction before considering a packaging rewrite.

| Before | After | Why |
| --- | --- | --- |
| Utility-style palette with compact controls | Material hierarchy, warm selection, readable original, 12px minimum metadata | Repeated retrieval needs clear focus and comfortable reading. |
| Flat capture browsing | Date groups, factual view counts, app/date filters and full reading pane | Reduce scanning and retain source context. |
| Idea save could finish while a newer draft was being edited | Newer edits remain open; interrupted composer retains its draft | A successful earlier save must not discard later thought. |
| A failed search could leave a previous selection actionable | Disable actions until current results are ready, offer Retry | Prevent applying the wrong capture after interruption. |
| Mobile rail enlarged the grid despite a passing document-overflow check | Zero-width minimum on rail, containment checks on actual workspace and buttons | Visual inspection exposed a false positive; the regression now measures the affected elements. |

## Applied guides and evidence

Emil design engineering and Impeccable were selected, read and applied. The Starlight materials tokens were read and applied to palette/material. This is an inline maker review because local swarm admission was HOLD. No independent design acceptance is claimed.

The installed Impeccable detector ran on `board.html`. Initial tiny-text warnings led to increasing 10px/11px metadata to 12px; the final detector returned `[]`. Local Windows checks: 44 unit tests and the built-in isolated self-test pass. JavaScript syntax is checked separately.

Cloudflare Chromium rendered the actual source using synthetic local API fixtures at 1440×900 and 390×844. Final interaction driver: 30 desktop, 31 mobile library and 32 mobile detail assertions passed. Key events were dispatched programmatically; touch was emulated; reduced-motion declarations were forced for computed-style verification. This does not establish physical keyboard/touch, Windows font rendering, real native focus or reboot behavior.

The final `Clipboard-*-Codex-2026-10-31-verified-v3.jpg` captures were visually inspected. Earlier captures with damaged Unicode or mobile overflow were rejected and retained privately. The source fixture is `tests/ui_fixture.py`; fixtures never load the real archive or capability token. Private capture receipts bind source, fixture and image hashes. Captures use Linux font fallback; no generated artwork is involved.

Sources for the bounded renderer: [Cloudflare Browser Run](https://developers.cloudflare.com/browser-run/) and [included browser usage](https://developers.cloudflare.com/changelog/post/2025-07-28-br-pricing/). Included allowance was checked before rendering; there is no metered model enrichment in the clipboard workflow.

## Remaining acceptance

Keep PR #5 draft. Exact-revision independent provider review, physical/native keyboard and touch acceptance, reboot startup and shortcut recovery, off-device encrypted recovery and key custody remain open in issue #4. The prior slice verified canonical memory filing and shared recall, plus encrypted local restoration; neither establishes off-device recovery. Unsaved composer text is kept in-window, not crash-recoverable storage. Native installation/open evidence belongs in the private runtime receipt and hub handover.
