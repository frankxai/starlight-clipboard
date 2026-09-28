# Starlight Clipboard

A Windows clipboard history for people who keep prompts. It listens beside the Windows clipboard. It does not replace Win+V.

What you copy stays on the Windows clipboard. This tool stores a local searchable copy, marks instructions as prompts, and can file a keeper into a private prompt book on the same machine.

## Two machines

Clone this repo on each machine and run `clip.py watch`. Each machine keeps its own database under `%USERPROFILE%\.starlight\clipboard-index`. That database is not in git. Do not commit it.

To move a non-secret copy to the other machine, copy a file from `devices\out` on the first machine into `devices\peers` on the second. The collector imports those files. Secrets are not written to `devices\out`.

The public prompt book is [frankxai/prompt-library](https://github.com/frankxai/prompt-library). Saving a prompt here does not push it there. A private entry stays in `%USERPROFILE%\.starlight\prompt-fabric` until you choose to publish a reviewed pattern.

## Commands

Open the palette with Ctrl+Alt+V after the collector is running.

Type `>` for commands: saved prompts, pinned copies, and save to the Starlight prompt book.

| Command | What it does |
|---|---|
| `clips` | Newest copies |
| `clips search words` | Full-text search |
| `clips prompts` | Copies marked as prompts |
| `clips promote 12 --scope starlight` | File one copy in the local prompt book |
| `clips watch` | Run the collector in this window |

A prompt is text that tells an agent what to do: a role, instructions, or a long ask. Ordinary sentences stay text. Keys are logged as events with the value removed.

## What this is not

Arcanea canon, the second-brain vault, and the public prompt library are separate. This tool can hand one saved prompt onward later. It does not bulk-import your clipboard into memory, and it does not publish your copies.
