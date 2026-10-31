---
name: Starlight Clipboard
description: A calm private workspace for copies, prompts and ideas.
colors:
  ink: "#070a10"
  paper: "#fbf6eb"
  muted: "#b9bdc8"
  quiet: "#8e97a8"
  gold: "#f0c87e"
  signal: "#82d8e6"
  reading: "#111620"
  selected: "rgba(201,161,92,.13)"
typography:
  title:
    fontFamily: '"Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif'
    fontSize: "25px"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "-.035em"
  body:
    fontFamily: '"Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif'
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.85
  metadata:
    fontSize: "12px"
rounded:
  control: "10px"
  surface: "20px"
spacing:
  small: "8px"
  medium: "16px"
  large: "24px"
components:
  button-primary:
    backgroundColor: "{colors.gold}"
    textColor: "#17130b"
    rounded: "{rounded.control}"
    padding: "9px 12px"
    height: "44px"
---

# Design system: Starlight Clipboard

Author: Codex. Created: 2026-10-31. Revision: v1. Review state: locally reviewed beta; independent acceptance pending.

## Overview

Frank's direction is Starlight liquid glass, combining a calm desktop workspace with a bold creative studio. Amber marks the action or capture in focus; restrained cyan light sits behind the workspace. Originals have a quiet reading surface. The interface serves repeated retrieval throughout the day.

Sources: Frank's direction, `board.html`, README.md and the inspected Starlight materials tokens in `starlight-design-intelligence/packages/materials/src/tokens/tokens.css`. Source code remains authoritative for behavior and computed values.

## Colors

Use ink behind the shell, warm paper for text, gold for primary actions and selection, and cyan for capture health. Muted and quiet support metadata. Excluded payloads and connection failures use explicit text in addition to color.

## Typography

Use the installed Windows Segoe stack with a system fallback. The main title is 25px at desktop size. The reading title is 23px, with 14px long-form text at 1.85 line height. Metadata is at least 12px. Code uses Cascadia Code or Consolas. No remote fonts are required.

## Layout

The desktop has a 192px navigation rail, a capture list and a flexible reader. Below 820px the rail becomes a horizontally scrollable navigation strip. Below 600px the list and reader occupy separate views with a visible Library return button. The navigation strip must scroll within its own rail. Grid children use a zero minimum width so they cannot enlarge the workspace.

Keep search near the top. Group captures by last-seen date; show original capture time in the reader. Keep frequent actions reachable without scrolling the original text.

## Elevation & Depth

Use translucent chrome, a thin warm border and subtle inset light. The rail uses 24px backdrop blur; the health panel uses 28px blur. The reader is nearly opaque. Provide solid surfaces when backdrop filtering is unsupported or stronger contrast is requested. Avoid animated ambient light.

## Shapes

Controls use 10px corners, capture rows 11px, the desktop shell 20px and the health panel 16px. Coarse pointers receive at least 44px high controls. Selection includes a visible border.

## Components

Primary buttons are warm gold with dark text. Secondary actions use a restrained translucent surface. Search uses a two-pixel focus ring around the group. Preserve visible keyboard focus for every actionable control.

The reader separates Paste and Copy from Save prompt, File in memory and Archive. An excluded payload disables the actions that could expose or file it. The shield panel reports actual capture and integration state. Suno remains a candidate classification until a separate submission receipt exists.

Frequent keyboard navigation has no animation. Fine-pointer hover changes color over 140ms with `cubic-bezier(.23,1,.32,1)`. Reduced motion removes transitions and animation. Touch does not use double-click to paste.

## Do's and Don'ts

- Do keep long originals readable and retain the source when filing or archiving.
- Do distinguish local snapshots, encrypted local backups and off-device recovery.
- Do show synthetic preview state explicitly in demonstrations.
- Don't infer submission, successful memory recall or backup coverage from appearance.
- Don't add remote dependencies to the capture path for decorative effects.
