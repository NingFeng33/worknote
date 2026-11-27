# Changelog

## 1.1.1 — 2026-11-27

- Clearer `note -h`: shows the note format at the top, a new "Other notebooks" section
  (`-n NAME` with `-T`, `-l`, `-e`), and `-T` described as the tag tree with entry counts.

## 1.1.0 — 2026-11-26

- Linked files: `note --link FILE.md` adds any Markdown file to `note -S` searches without
  moving or changing it. Matches show the file name and the headings above the line.
  `note --links` lists linked files, `note --unlink NAME` removes one. Links are per machine.

## 1.0.1 — 2026-11-26

- Long notes now wrap to the terminal width in `-l`, `-t`, `-s`, `-S`, `--rm` and `--mod` output.
  Wrapped lines line up under the description (the text after `—`), or under the note text
  when there is no description or the window is narrow. Chinese and other wide characters are
  measured correctly. The notebook file itself is unchanged: one note per line.
- Multi-line blocks, tables, and output piped to another program are not wrapped.

## 1.0.0 — 2026-11-25

First release.

- Add notes by tag: `note tag/sub: text -- description`, paste mode for multi-line blocks, prompt mode.
- Tables (`note table`), pictures (`note pic`, `--clip`), bulk import (`--import`).
- View and search: `-l`, `-t`, `-T`, `-s`, `-S`, `-N`.
- Change notes: `--mod`, `--rm`, `--undo`, `-e`, `--organize`, `--merge`.
- Notebooks per folder, or one default notebook (`--default`), or by name (`-n`).
- Git sync: `--init`, `--sync`, `--autosync`, with union merge for conflict-free adds.
- PowerShell and zsh integration that keeps `#`, `>`, `|`, `"` intact; zsh Tab completion of tags.
