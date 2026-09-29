# Starlight Clipboard

A Windows clipboard history for people who keep prompts. It listens beside the Windows clipboard. It does not replace Win+V.

What you copy stays on the Windows clipboard. This tool stores a local searchable copy, keeps pictures, marks instructions as prompts, and can file one keeper into a private prompt book or one note in a markdown vault on the same machine.

## Two machines

Clone this repo on each machine and run `clip.py watch`. Each machine keeps its own database under `%USERPROFILE%\.starlight\clipboard-index`. That database is not in git. Do not commit it.

To move a non-secret copy to the other machine, copy a file from `devices\out` on the first machine into `devices\peers` on the second. The collector imports those files. Secrets are not written to `devices\out`.

The public prompt book is [frankxai/prompt-library](https://github.com/frankxai/prompt-library). Saving a prompt here does not push it there. A private entry stays in `%USERPROFILE%\.starlight\prompt-fabric` until you choose to publish a reviewed pattern.

## Commands

Open the palette with Ctrl+Alt+V after the collector is running.

Type `>` for commands: saved prompts, pinned copies, save to the Starlight prompt book, and file one copy in the second brain.

Pictures are kept when the copy includes a PNG or a bitmap. Paste puts the picture back. If an older picture says it was not kept, copy it again.

The collector waits before it reads, and it waits longer while the Windows key is down or the Windows clipboard window is open. It does not register Win+V.

| Command | What it does |
|---|---|
| `clips` | Newest copies |
| `clips search words` | Full-text search |
| `clips prompts` | Copies marked as prompts |
| `clips promote 12 --scope starlight` | File one copy in the local prompt book |
| `clips remember 12` | File that one copy as a private note |
| `clips watch` | Run the collector in this window |

A prompt is text that tells an agent what to do: a role, instructions, or a long ask. The palette shows that reason on its own line. Ordinary sentences stay text. Keys are logged as events with the value removed. `clips remember` refuses a secret and a picture with no text. Set `STARLIGHT_VAULT` to a markdown vault if the note should land in `atoms` there.

## What this is not

Arcanea canon and the public prompt library are separate. The second brain receives one note when you use `clips remember` or the palette command. Nothing else is imported, and nothing is published.
