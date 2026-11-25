# note — tag-organized work notes from your terminal

`note` is a small command-line notebook. You type a note in the terminal, and it lands in a
plain Markdown file, filed under a tag and kept sorted. You can search it, view it by tag,
and sync it between machines with git.

```powershell
note sel/access: ACC -- go to access level 1
note vim/copy: "+y -- copy selection to system clipboard
note -t vim            # show everything tagged vim
note -S clipboard      # search all notebooks
```

- **One Python file, standard library only.** It runs anywhere Python 3.8+ runs: Windows, Linux, macOS.
- **Plain Markdown.** Notebooks are readable in any editor, renderable on GitHub, and easy for `grep` or an AI assistant to work with.
- **Organized by tag, not by date.** `## tag` / `### tag/sub` sections are created and kept in alphabetical order.
- **Type anything.** PowerShell and zsh integration keep characters like `#`, `>`, `|` and `"` from being eaten by the shell.
- **Sync through git.** Use any git remote, such as a home server over SSH. Notes added on two machines merge without conflicts.

## Install

You need **Python 3** and **git** (git is only needed for syncing).

### Windows (PowerShell)

Download and unzip the release, open PowerShell in that folder, and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
.\install.ps1
```

This copies the tool to `%USERPROFILE%\bin\worknote`, loads it from your PowerShell profile, and
allows that profile to load (sets the CurrentUser execution policy to RemoteSigned if it is Restricted).

### Linux / macOS (zsh)

```bash
sh install.sh && source ~/.zshrc
```

This installs to `~/.local/share/worknote` and adds one `source` line to `~/.zshrc`. It also
enables Tab completion of your existing tags.

## Usage

### Add notes

| Command | What it does |
|---|---|
| `note tag/sub: text -- description` | One-line note. Text after a standalone `--` (or after ` #`) becomes the description. |
| `note tag/sub:` | Paste mode for multi-line blocks. Finish with two empty lines or a line with just `.` |
| `note -p tag/sub: Title` | Paste mode with a title |
| `note` | Prompt mode: type a line with no shell interference |
| `note table tag: Server list` | Build a table: columns first, then one row per line (comma or tab separated) |
| `note pic path/to/img.png tag: caption` | Copy a picture into `worknotes/assets` and link it |
| `note pic --clip tag: caption` | Use the picture on the clipboard |
| `note --import [FILE]` | Add many `tag: text -- desc` lines at once (from the clipboard if no file) |

Notes without a tag go into an `inbox` section. Tags are case-insensitive.

### Read and search

| Command | What it does |
|---|---|
| `note -l` | Show the current notebook |
| `note -t TAG` | Show a tag and its sub-tags (`-g` = all notebooks) |
| `note -T` | List tags with counts (`-g` = all notebooks) |
| `note -s WORDS` | Search the current notebook (all words must match) |
| `note -S WORDS` | Search all notebooks |
| `note -N` | List notebooks |

### Change notes

| Command | What it does |
|---|---|
| `note --mod WORDS` | Find a note, pick it, type the new version (a new `tag:` moves it) |
| `note --rm WORDS` | Find notes, pick them by number, delete them |
| `note --undo` | Remove the last note added on this computer (repeatable) |
| `note -e` | Open the notebook in your editor (`$EDITOR`, or Notepad on Windows); re-sorted on close |
| `note --organize` | Re-sort all notebooks after hand edits |
| `note --merge FROM [INTO]` | Move every note of one notebook into another |

### Notebooks

Notebooks live in one folder: `~/worknotes` (or `%USERPROFILE%\worknotes`). Set `WORKNOTES_DIR` to use another folder.

- By default, each folder you run `note` from gets its own notebook, `<folder>_WorkNote.md`. Your home folder uses `general`.
- `note --default general` sends every note to one notebook instead. `note --default off` switches back.
- `note -n NAME ...` uses `NAME_WorkNote.md` for a single command.

### Sync between machines

```bash
# once, on the server
git init --bare ~/worknotes.git

# once, on each machine
note --init USER@SERVER:worknotes.git

# then
note --sync              # pull + push
note --autosync on       # push after every change
```

The notes repository uses git's `union` merge for Markdown files, so notes added on two machines
are both kept. The tool re-sorts the notebooks after each pull.

## File format

```markdown
# general — Work Notes

## vim

### vim/copy

- `yy` — copy (yank) current line
- `"+y` — copy selection to system clipboard

### vim/search

- `:%s/old/new/g` — replace all in file
```

See [`examples/example_WorkNote.md`](examples/example_WorkNote.md) for a fuller example. Hand
edits are fine; keep one note per `- ` line under the right heading, then run `note --organize`.

## Configuration

| Where | What |
|---|---|
| `~/.worknote.json` | Per-machine settings: `default` notebook, `autosync`, `dir` |
| `~/.worknote_state.json` | Undo history (last 30 notes added on this machine) |
| `WORKNOTES_DIR` | Environment variable that overrides the notes folder |
| `NO_COLOR` | Environment variable that turns off colored output |

## Uninstall

- **Windows:** delete `%USERPROFILE%\bin\worknote` and remove the `worknote\note.ps1` line from `$PROFILE`.
- **zsh:** delete `~/.local/share/worknote` and remove the `worknote/note.zsh` line from `~/.zshrc`.

Your notes folder is never touched by uninstalling.

## License

[MIT](LICENSE)
