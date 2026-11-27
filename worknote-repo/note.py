#!/usr/bin/env python3
"""note - tag-organized work notes in Markdown, synced with git.

Format:  note tag/sub: command or text -- description
         (colon right after the tag, no spaces in tags, spaces around --)

Add notes
  note sel/access: ACC -- access level 0 to 1     one-line note under a tag
  note sel/settings:                              paste mode (multi-line block)
  note -p sel/settings: Set a spare output        paste mode with a title
  note just some text                             untagged -> goes to "inbox"
  note                                            prompt mode: type anything safely
  note table sel/info: Server list                build a table row by row
  note pic C:\\path\\diagram.png sel: Wiring        copy a picture in and link it
  note pic --clip sel: Wiring                     picture from the clipboard
  note --import [FILE]    add many "tag: text -- desc" lines at once (default: clipboard)

Read / search
  note -l                 show the whole notebook
  note -T                 show the tag tree with entry counts   add -g for all notebooks
  note -t sel             show one tag and its sub-tags         add -g for all notebooks
  note -s word [word..]   search the notebook
  note -S word [word..]   search ALL notebooks and linked files
  note -N                 list notebooks

Other notebooks  (put -n NAME first; works with every command)
  note -n NAME tag: text  add to NAME_WorkNote.md (created on first use)
  note -n NAME -T         tag tree of NAME
  note -n NAME -l         show NAME            note -n NAME -e   edit NAME
  note --default NAME     send every note to NAME unless -n is given  (off = per folder)

Change notes
  note --mod WORDS [-g]   find a note, pick it, type the new text (or a new tag:)
  note --rm WORDS [-g]    find notes, pick by number, delete them
  note --undo             remove the last note you added (repeat to go further back)
  note -e                 open the notebook in your editor
  note --organize         re-sort every notebook by tag
  note --merge FROM [INTO]  move all entries of notebook FROM into INTO, delete FROM

Sync and setup
  note --sync             pull + push with the remote
  note --autosync on|off  sync automatically after every note
  note --init USER@HOST:worknotes.git    connect the notes folder to a git remote
  note --link FILE.md     also search this Markdown file with -S (it is never changed)
  note --unlink NAME      stop searching a linked file      note --links   list them
  note --where            show where the notes are stored
  note --version          show the version
"""
import base64
import csv
import getpass
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import unicodedata
from pathlib import Path

VERSION = "1.1.1"
SUFFIX = "_WorkNote.md"
INBOX = "inbox"
CONFIG_PATH = Path.home() / ".worknote.json"
STATE_PATH = Path.home() / ".worknote_state.json"   # undo history, per machine

# ----------------------------------------------------------------- console --

USE_COLOR = False


def setup_console():
    global USE_COLOR
    if os.name == "nt":
        os.system("")  # turns on ANSI colour handling in Windows consoles
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    USE_COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def col(code, text):
    return f"\033[{code}m{text}\033[0m" if USE_COLOR else text


def ok(msg):
    print(col("32", "✓ ") + msg)


def warn(msg):
    print(col("33", "! ") + msg, file=sys.stderr)


def die(msg, code=1):
    print(col("31", "✗ ") + msg, file=sys.stderr)
    sys.exit(code)


# ------------------------------------------------------------------ config --

def load_config():
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(cfg):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def notes_dir():
    d = os.environ.get("WORKNOTES_DIR") or load_config().get("dir")
    return Path(d).expanduser() if d else Path.home() / "worknotes"


# --------------------------------------------------------------- notebooks --

def default_notebook_name():
    fixed = load_config().get("default")
    if fixed:
        return fixed
    cwd = Path.cwd().resolve()
    try:
        home = Path.home().resolve()
    except Exception:
        home = None
    if cwd == home or not cwd.name:
        return "general"
    return re.sub(r"\s+", "-", cwd.name.strip())


def notebook_path(name):
    d = notes_dir()
    target = (name + SUFFIX).lower()
    if d.is_dir():
        for p in d.iterdir():
            if p.name.lower() == target:
                return p
    return d / (name + SUFFIX)


def all_notebook_paths():
    d = notes_dir()
    if not d.is_dir():
        return []
    return sorted((p for p in d.iterdir() if p.name.lower().endswith(SUFFIX.lower())),
                  key=lambda p: p.name.lower())


def norm_tag(tag):
    tag = tag.strip().strip(":").lower()
    tag = re.sub(r"\s+", "-", tag)
    tag = re.sub(r"/+", "/", tag).strip("/")
    return tag or INBOX


FENCE_OPEN = re.compile(r"^\s*(?:[-*]\s+)?(`{3,}|~{3,})")


def _closes_fence(line, mark):
    s = line.strip()
    return s.startswith(mark) and set(s) == {mark[0]}


def _norm_entry(entry):
    return "\n".join(l.rstrip() for l in entry).strip().lower()


class Notebook:
    """A <name>_WorkNote.md file: header, then '## top' / '### top/sub' sections of '- ' entries."""

    def __init__(self, path):
        self.path = Path(path)
        self.name = self.path.name[: -len(SUFFIX)]
        self.header = []
        self.sections = {}  # tag -> [entry, ...]; entry = [line, ...]
        if self.path.exists():
            self._parse(self.path.read_text(encoding="utf-8"))
        if not any(l.strip() for l in self.header):
            self.header = [
                f"# {self.name} — Work Notes",
                "",
                "<!-- Managed by the `note` tool. Entries sit under `## tag` / `### tag/sub` "
                "headings, sorted by tag. Hand edits are fine; run `note --organize` afterwards. -->",
            ]

    def _parse(self, text):
        lines = text.replace("\r\n", "\n").split("\n")
        top = tag = entry = fence = None

        def close():
            nonlocal entry
            if entry is not None and tag is not None:
                while entry and not entry[-1].strip():
                    entry.pop()
                if entry:
                    self.sections.setdefault(tag, []).append(entry)
            entry = None

        for line in lines:
            if fence:
                if entry is None:
                    entry = []
                entry.append(line)
                if _closes_fence(line, fence):
                    fence = None
                continue
            m = re.match(r"^(#{2,3})\s+(.+?)\s*$", line)
            if m:
                close()
                title = norm_tag(m.group(2))
                if len(m.group(1)) == 3 and "/" not in title and top:
                    title = f"{top}/{title}"
                tag = title
                top = tag.split("/")[0]
                self.sections.setdefault(tag, [])
                continue
            if tag is None:
                self.header.append(line)
                continue
            if line.startswith(("- ", "* ")) or line.rstrip() in ("-", "*"):
                close()
                entry = [line]
            elif entry is None:
                if not line.strip():
                    continue
                entry = [line]
            else:
                entry.append(line)
            fm = FENCE_OPEN.match(line)
            if fm:
                fence = fm.group(1)
        close()
        while self.header and not self.header[-1].strip():
            self.header.pop()

    def ordered(self):
        """(tag, entries) in file order: inbox first, then tags alphabetically, top before subs."""
        tags = [t for t, e in self.sections.items() if e]

        def key(t):
            parts = t.split("/")
            return (parts[0] != INBOX, parts[0], len(parts) > 1, t)

        return [(t, self.sections[t]) for t in sorted(tags, key=key)]

    def render(self):
        out = list(self.header) + [""]
        last_top = None
        for tag, entries in self.ordered():
            top = tag.split("/")[0]
            if top != last_top:
                out += [f"## {top}", ""]
                last_top = top
            if tag != top:
                out += [f"### {tag}", ""]
            out += _entries_lines(entries) + [""]
        return "\n".join(out).rstrip() + "\n"

    def add(self, tag, entry):
        entries = self.sections.setdefault(tag, [])
        key = _norm_entry(entry)
        if any(_norm_entry(e) == key for e in entries):
            return False
        entries.append(entry)
        return True

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(self.render())
        os.replace(tmp, self.path)


def _entries_lines(entries):
    res = []
    for e in entries:
        multi = len(e) > 1
        if multi and res and res[-1] != "":
            res.append("")
        res += e
        if multi:
            res.append("")
    while res and res[-1] == "":
        res.pop()
    return res


# --------------------------------------------------------- entry building --

TAG_RE = re.compile(r"^\s*([A-Za-z0-9_][\w.\-]*(?:/[\w.\-]+)*):(?:\s+(.*\S)|\s*)$", re.S)
DESC_SEP = re.compile(r"\s+(?:--(?=\s|$)|#)\s*")   # "--" only as a separate word, so "--rm" stays


def strip_quotes(text):
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        return text[1:-1].strip()
    return text


def split_tag(text):
    """'sel/access: ACC' -> ('sel/access', 'ACC'); untagged text -> ('inbox', text)."""
    m = TAG_RE.match(text)
    if m:
        return norm_tag(m.group(1)), (m.group(2) or "").strip()
    return INBOX, text.strip()


def format_line(text):
    text = text.strip()
    m = DESC_SEP.search(text)
    if m and m.start() > 0:
        cmd, desc = text[: m.start()].strip(), text[m.end():].strip()
        if desc:
            code = f"`{cmd}`" if "`" not in cmd else cmd
            return [f"- {code} — {desc}"]
        text = cmd
    return [f"- {text}"]


def format_block(lines, title=None):
    fence = "~~~" if any("```" in l for l in lines) else "```"
    out = [f"- {title}", f"  {fence}"] if title else [f"- {fence}"]
    out += [("  " + l) if l.strip() else "" for l in lines]
    out.append(f"  {fence}")
    return out


def format_table(title, header, rows):
    def cell(s):
        return s.strip().replace("|", "\\|")

    n = len(header)
    out = [f"- **{title}**" if title else "- **Table**", ""]
    out.append("  | " + " | ".join(cell(h) for h in header) + " |")
    out.append("  | " + " | ".join("---" for _ in header) + " |")
    for r in rows:
        if len(r) > n:
            r = r[: n - 1] + [", ".join(r[n - 1:])]
        r = r + [""] * (n - len(r))
        out.append("  | " + " | ".join(cell(x) for x in r) + " |")
    return out


def split_cells(line):
    if "\t" in line:
        return [c.strip() for c in line.split("\t")]
    return [c.strip() for c in next(csv.reader([line], skipinitialspace=True), [])]


def looks_like_tab_table(lines):
    rows = [l for l in lines if l.strip()]
    if len(rows) < 2 or not all("\t" in r for r in rows):
        return False
    return len({len(r.split("\t")) for r in rows}) == 1


def ask(prompt):
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        print()
        return None


def read_block():
    print(col("2", "Paste or type lines. Finish with two empty lines, or a line with just '.'"))
    lines, blanks = [], 0
    while True:
        line = ask(col("2", "paste> "))
        if line is None:
            break
        if line.strip() == ".":
            break
        if not line.strip():
            blanks += 1
            if blanks >= 2:
                break
            lines.append("")
            continue
        blanks = 0
        lines.append(line.rstrip())
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


# ------------------------------------------------------------------ output --

INLINE_CODE = re.compile(r"`([^`]+)`")
BOLD = re.compile(r"\*\*([^*]+)\*\*")
IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


def paint(line, terms=None):
    m = re.match(r"^(\s*)[-*] (.*)$", line)
    indent, body = (m.group(1), m.group(2)) if m else ("", line)
    bullet = col("2", "• ") if m else ""

    def img(mm):
        p = mm.group(2)
        full = p if re.match(r"^[a-z]+://", p) else str((notes_dir() / p).resolve())
        return col("36", f"[pic] {mm.group(1)}") + col("2", f"  {full}")

    if terms:
        body = IMAGE.sub(lambda mm: f"[pic] {mm.group(1)}  {(notes_dir() / mm.group(2)).resolve()}", body)
        pat = re.compile("|".join(re.escape(t) for t in terms), re.I)
        body = pat.sub(lambda mm: col("1;33", mm.group(0)), body)
    else:
        body = IMAGE.sub(img, body)
        body = INLINE_CODE.sub(lambda mm: col("32", mm.group(1)), body)
        body = BOLD.sub(lambda mm: col("1", mm.group(1)), body)
        if body.lstrip().startswith("|"):
            body = col("2", body) if re.match(r"^\s*\|[\s|:-]+\|\s*$", body) else body
    return "  " + indent + bullet + body


ANSI = re.compile(r"\x1b\[[0-9;]*m")


def char_width(ch):
    if unicodedata.combining(ch):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def text_width(s):
    return sum(char_width(c) for c in ANSI.sub("", s))


def wrap_display(s):
    """Wrap a painted line to the terminal width. Continuation lines line up under the
    description (the text after ' — '), or under the text after the bullet."""
    if not sys.stdout.isatty():
        return s
    width = shutil.get_terminal_size((100, 24)).columns - 1
    plain = ANSI.sub("", s)
    if text_width(plain) <= width or plain.lstrip().startswith("|"):
        return s
    bullet = plain.find("• ")
    hang = text_width(plain[: bullet + 2]) if bullet != -1 else len(plain) - len(plain.lstrip())
    dash = plain.find(" — ")
    if dash != -1:
        desc_col = text_width(plain[: dash + 3])
        if desc_col <= width * 0.6:
            hang = desc_col
    if hang > width // 2:
        hang = 4

    # split into tokens: ANSI codes (zero width), runs of spaces, and words
    tokens = re.findall(r"\x1b\[[0-9;]*m|[ ]+|[^ \x1b]+", s)
    lines, cur, cur_w = [], "", 0
    pending_space = ""
    for tok in tokens:
        if tok.startswith("\x1b"):
            cur += tok
            continue
        if tok.startswith(" "):
            if not lines and not ANSI.sub("", cur):  # leading indent of the first line
                cur += tok
                cur_w += len(tok)
            else:
                pending_space = tok if cur_w > hang or not lines else ""
            continue
        w = text_width(tok)
        fits_on_fresh_line = w <= width - hang
        if cur_w and cur_w + len(pending_space) + w > width and fits_on_fresh_line:
            lines.append(cur)
            cur, cur_w = " " * hang, hang
            pending_space = ""
        cur += pending_space
        cur_w += len(pending_space)
        pending_space = ""
        while cur_w + w > width and w > 1:  # a single word longer than the line
            room = width - cur_w
            take, tw = "", 0
            for ch in tok:
                if tw + char_width(ch) > room:
                    break
                take += ch
                tw += char_width(ch)
            if not take:
                break
            lines.append(cur + take)
            tok = tok[len(take):]
            w = text_width(tok)
            cur, cur_w = " " * hang, hang
        cur += tok
        cur_w += w
    lines.append(cur)
    return "\n".join(lines)


def print_entry(entry, terms=None):
    fence = None
    for line in entry:
        if fence:
            if _closes_fence(line, fence):
                fence = None
                continue
            text = line[2:] if line.startswith("  ") else line
            if terms:
                pat = re.compile("|".join(re.escape(t) for t in terms), re.I)
                text = pat.sub(lambda mm: col("1;33", mm.group(0)), text)
            print("    " + col("2", "│ ") + text)
            continue
        fm = FENCE_OPEN.match(line)
        if fm:
            fence = fm.group(1)
            title = line.strip()[1:].strip() if line.lstrip().startswith(("-", "*")) else ""
            if title and not title.startswith(fence):
                print(wrap_display(paint(line, terms)))
            elif line.lstrip().startswith(("-", "*")):
                print("  " + col("2", "• ") + col("2", "(block)"))
            continue
        if not line.strip():
            continue
        print(wrap_display(paint(line, terms)))


def print_tag_heading(tag, notebook=None):
    top, _, sub = tag.partition("/")
    label = col("1;35", top) + (col("1;36", "/" + sub) if sub else "")
    prefix = col("2", f"{notebook} › ") if notebook else ""
    print(prefix + label)


def show_sections(nb, sections, show_nb=False):
    for tag, entries in sections:
        print_tag_heading(tag, nb.name if show_nb else None)
        for e in entries:
            print_entry(e)
        print()


# ---------------------------------------------------------------------- git --

def has_git():
    return shutil.which("git") is not None and (notes_dir() / ".git").exists()


def git(*args, capture=True, timeout=None, env=None):
    return subprocess.run(
        ["git", "-C", str(notes_dir()), *args],
        capture_output=capture, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, env=env,
    )


def git_commit(msg):
    if not has_git():
        return
    git("add", "-A")
    if git("diff", "--cached", "--quiet").returncode != 0:
        r = git("commit", "-q", "-m", msg)
        if r.returncode != 0:
            warn("git commit failed: " + (r.stderr or r.stdout).strip())


def has_remote():
    return has_git() and "origin" in git("remote").stdout.split()


def current_branch():
    return git("symbolic-ref", "--short", "HEAD").stdout.strip() or "main"


def ensure_repo_settings():
    d = notes_dir()
    if not git("config", "user.email").stdout.strip():
        user = getpass.getuser()
        git("config", "user.name", user)
        git("config", "user.email", f"{user}@{socket.gethostname()}")
    git("config", "pull.rebase", "false")
    git("config", "core.autocrlf", "false")
    ga = d / ".gitattributes"
    if not ga.exists():
        # union merge: notes added on two machines are both kept instead of conflicting
        ga.write_text("*.md text eol=lf merge=union\n", encoding="utf-8", newline="\n")
    gi = d / ".gitignore"
    if not gi.exists():
        gi.write_text("*.tmp\n", encoding="utf-8", newline="\n")


def organize_all(quiet=True):
    n = 0
    for p in all_notebook_paths():
        before = p.read_text(encoding="utf-8")
        nb = Notebook(p)
        if nb.render() != before:
            nb.save()
            n += 1
    if not quiet:
        ok(f"Organized {n} notebook(s)" if n else "Everything already organized")
    return n


def cmd_init(remote):
    if not shutil.which("git"):
        die("git is not installed or not on PATH.")
    d = notes_dir()
    d.mkdir(parents=True, exist_ok=True)
    print(f"Notes folder: {d}")
    if not (d / ".git").exists():
        git("init", "-q")
    if "origin" in git("remote").stdout.split():
        git("remote", "set-url", "origin", remote)
    else:
        git("remote", "add", "origin", remote)
    ensure_repo_settings()

    print(f"Contacting {remote} ...")
    ls = git("ls-remote", "--symref", "origin")
    if ls.returncode != 0:
        die("Could not reach the remote:\n" + ls.stderr.strip() +
            "\nCheck the address (user@host:path), and that `ssh user@host` works without a password.")
    heads, head_target = set(), None
    for line in ls.stdout.splitlines():
        if line.startswith("ref: refs/heads/") and line.endswith("HEAD"):
            head_target = line[len("ref: refs/heads/"):].split()[0]
        elif "\trefs/heads/" in line:
            heads.add(line.split("\trefs/heads/")[1])
    if heads:
        branch = head_target if head_target in heads else (
            "main" if "main" in heads else "master" if "master" in heads else sorted(heads)[0])
    else:
        branch = "main"

    has_commits = git("rev-parse", "--verify", "-q", "HEAD").returncode == 0
    if has_commits:
        if current_branch() != branch:
            git("branch", "-M", branch)
    else:
        git("symbolic-ref", "HEAD", f"refs/heads/{branch}")
    organize_all()
    git_commit("worknote: local notes")

    if branch in heads:
        r = git("fetch", "-q", "origin", branch, capture=False)
        if r.returncode != 0:
            die("Fetching from the remote failed.")
        r = git("merge", "--no-edit", "-q", "--allow-unrelated-histories", f"origin/{branch}")
        if r.returncode != 0:
            die("Merging remote notes failed:\n" + (r.stdout + r.stderr).strip())
        if organize_all():
            git_commit("worknote: organize")
    r = git("push", "-q", "-u", "origin", branch, capture=False)
    if r.returncode != 0:
        die("Push failed (see message above).")
    ok(f"Connected to {remote} (branch {branch}). Use `note --sync` to sync.")


def cmd_sync(quiet=False, timeout=None):
    if not has_remote():
        if quiet:
            return False
        die("Not connected yet. Run:  note --init USER@HOST:worknotes.git")
    env = None
    if quiet:
        env = dict(os.environ)
        env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes -o ConnectTimeout=5")
    git_commit("worknote: local changes")
    try:
        r = git("pull", "-q", "--no-edit", "origin", current_branch(), timeout=timeout, env=env)
        if r.returncode != 0:
            if quiet:
                return False
            die("Pull failed:\n" + (r.stdout + r.stderr).strip())
        if organize_all():
            git_commit("worknote: organize")
        r = git("push", "-q", "-u", "origin", current_branch(), timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return False
    if r.returncode != 0:
        if quiet:
            return False
        die("Push failed:\n" + (r.stdout + r.stderr).strip())
    if not quiet:
        ok("Synced.")
    return True


def after_change(msg):
    git_commit(msg)
    if load_config().get("autosync") and has_remote():
        if cmd_sync(quiet=True, timeout=20):
            print(col("2", "  synced"))
        else:
            print(col("2", "  (not synced: offline? run `note --sync` later)"))


# ----------------------------------------------------------------- actions --

def save_entry(nbname, tag, entry):
    nb = Notebook(notebook_path(nbname))
    if not nb.add(tag, entry):
        warn(f"Already in {nb.name} › {tag}; nothing added.")
        return
    nb.save()
    push_undo(nb.name, tag, entry)
    ok(f"Added to {col('1', nb.name)} › {col('1;36', tag)}")
    print_entry(entry)
    after_change(f"note: {nb.name} / {tag}")


# ------------------------------------------------------ undo / rm / modify --

def load_state():
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def push_undo(nbname, tag, entry):
    st = load_state()
    st["added"] = (st.get("added", []) + [{"nb": nbname, "tag": tag, "entry": entry}])[-30:]
    try:
        STATE_PATH.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def remove_entry(nb, tag, entry):
    key = _norm_entry(entry)
    entries = nb.sections.get(tag, [])
    for i, e in enumerate(entries):
        if _norm_entry(e) == key:
            del entries[i]
            return True
    return False


def cmd_undo():
    st = load_state()
    stack = st.get("added", [])
    while stack:
        last = stack.pop()
        p = notebook_path(last["nb"])
        nb = Notebook(p) if p.exists() else None
        STATE_PATH.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
        if nb and remove_entry(nb, last["tag"], last["entry"]):
            nb.save()
            ok(f"Removed from {nb.name} › {last['tag']}:")
            print_entry(last["entry"])
            after_change(f"undo: {nb.name} / {last['tag']}")
            return
    warn("Nothing to undo (only notes added on this computer can be undone).")


def find_matches(terms, nbname, everywhere):
    terms = [t.lower() for t in terms if t.strip()]
    paths = all_notebook_paths() if everywhere else [notebook_path(nbname)]
    found = []
    for p in paths:
        if not p.exists():
            continue
        nb = Notebook(p)
        for tag, entries in nb.ordered():
            for e in entries:
                hay = (tag + "\n" + "\n".join(e)).lower()
                if all(t in hay for t in terms):
                    found.append((nb.name, tag, e))
    return terms, found


def pick(terms, nbname, everywhere, verb, many):
    if not [t for t in terms if t.strip()]:
        die(f"Usage: note --{verb} WORDS [-g]")
    terms, found = find_matches(terms, nbname, everywhere)
    if not found:
        die("No matching notes" + ("." if everywhere else " here (add -g to look in all notebooks)."))
    if len(found) > 40:
        die(f"{len(found)} matches; add more words to narrow it down.")
    for i, (nb, tag, e) in enumerate(found, 1):
        print(col("1", f"[{i}] ") + col("2", f"{nb} › ") + col("36", tag))
        print_entry(e, terms)
    if len(found) == 1:
        a = ask(f"{verb.capitalize()} this one? [y/N] ")
        return found if a and a.strip().lower() in ("y", "yes") else []
    a = ask(f"Number{'s (e.g. 1 3)' if many else ''} to {verb}, Enter to cancel: ")
    if not a or not a.strip():
        return []
    try:
        nums = sorted({int(x) for x in re.split(r"[\s,]+", a.strip()) if x})
    except ValueError:
        die("Please type numbers only.")
    if any(n < 1 or n > len(found) for n in nums):
        die("Number out of range.")
    if not many and len(nums) > 1:
        die("Pick one note at a time.")
    return [found[n - 1] for n in nums]


def read_clipboard_text():
    if os.name == "nt":
        ps = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-Clipboard"
        r = subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps], capture_output=True)
        return r.stdout.decode("utf-8", errors="replace") if r.returncode == 0 else ""
    for cmd in (["wl-paste", "--no-newline"], ["xclip", "-selection", "clipboard", "-o"]):
        if shutil.which(cmd[0]):
            r = subprocess.run(cmd, capture_output=True)
            if r.returncode == 0:
                return r.stdout.decode("utf-8", errors="replace")
    return ""


def cmd_import(args, nbname):
    if args:
        src = Path(strip_quotes(" ".join(args))).expanduser()
        if not src.is_file():
            die(f"File not found: {src}")
        text = src.read_text(encoding="utf-8-sig")
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        text = read_clipboard_text()
    lines = [l.strip() for l in text.replace("\r\n", "\n").split("\n") if l.strip()]
    if not lines:
        die("Nothing to import (copy the lines first, or give a file: note --import FILE).")
    nb = Notebook(notebook_path(nbname))
    added = dup = 0
    for line in lines:
        line = re.sub(r"^note\s+", "", line)
        tag, body = split_tag(strip_quotes(line))
        if not body:
            continue
        if nb.add(tag, format_line(body)):
            added += 1
        else:
            dup += 1
    nb.save()
    ok(f"Imported {added} note(s) into {nb.name}" + (f" ({dup} already there)" if dup else ""))
    after_change(f"import: {added} note(s) into {nb.name}")


def cmd_rm(terms, nbname, everywhere):
    chosen = pick(terms, nbname, everywhere, "delete", many=True)
    if not chosen:
        print("Cancelled.")
        return
    if len(chosen) > 1:
        a = ask(f"Delete {len(chosen)} notes? [y/N] ")
        if not a or a.strip().lower() not in ("y", "yes"):
            print("Cancelled.")
            return
    books = {}
    for nbn, tag, e in chosen:
        nb = books.setdefault(nbn, Notebook(notebook_path(nbn)))
        remove_entry(nb, tag, e)
    for nb in books.values():
        nb.save()
    ok(f"Deleted {len(chosen)} note(s).")
    after_change(f"rm: {len(chosen)} note(s)")


def entry_to_text(entry):
    line = entry[0]
    line = line[2:] if line.startswith(("- ", "* ")) else line
    m = re.match(r"^`([^`]+)` — (.*)$", line)
    return f"{m.group(1)} -- {m.group(2)}" if m else line


def cmd_mod(terms, nbname, everywhere):
    chosen = pick(terms, nbname, everywhere, "modify", many=False)
    if not chosen:
        print("Cancelled.")
        return
    nbn, tag, e = chosen[0]
    nb = Notebook(notebook_path(nbn))
    if len(e) > 1:
        old_title = e[0][2:].strip() if e[0].startswith("- ") else ""
        if not old_title or old_title.startswith(("```", "~~~", "**")):
            die("This is a multi-line block or table; change it with  note -e")
        print(col("2", "This is a multi-line block; you can change its title or tag here (use note -e for the content)."))
    current = f"{tag}: {entry_to_text(e)}"
    print(col("2", "Current: ") + current)
    print(col("2", "Type the new version (you may change the tag too). Enter alone keeps it."))
    new = ask(col("1", "new> "))
    if not new or not new.strip():
        print("Unchanged.")
        return
    new = strip_quotes(new)
    if TAG_RE.match(new):
        new_tag, body = split_tag(new)
    else:
        new_tag, body = tag, new.strip()
    if not body:
        die("Empty text; nothing changed.")
    if len(e) > 1:
        new_entry = [f"- {body}"] + e[1:]
    else:
        new_entry = format_line(body)
    remove_entry(nb, tag, e)
    nb.add(new_tag, new_entry)
    nb.save()
    ok(f"Updated in {nb.name} › {col('1;36', new_tag)}")
    print_entry(new_entry)
    after_change(f"mod: {nb.name} / {new_tag}")


def add_note(text, nbname, force_paste=False):
    text = strip_quotes(text)
    if force_paste and text.startswith("-p"):
        text = text[2:].strip()
    elif text.startswith("-p ") or text == "-p":
        force_paste, text = True, text[2:].strip()
    tag, body = split_tag(text)
    if not text and not force_paste:
        return
    if force_paste or not body:
        title = body if force_paste and body else None
        lines = read_block()
        if not lines:
            warn("Nothing entered; cancelled.")
            return
        if looks_like_tab_table(lines):
            a = ask("Looks like a table (copied from a spreadsheet?). Save as a table? [Y/n] ")
            if a is not None and a.strip().lower() in ("", "y", "yes"):
                rows = [split_cells(l) for l in lines if l.strip()]
                save_entry(nbname, tag, format_table(title, rows[0], rows[1:]))
                return
        if len(lines) == 1 and not title:
            entry = format_line(lines[0])
        else:
            entry = format_block(lines, title)
    else:
        entry = format_line(body)
    save_entry(nbname, tag, entry)


def prompt_mode(nbname):
    print(col("2", f"Notebook: {nbname}.  Type  tag: text   (or just  tag:  for a multi-line block)."))
    line = ask(col("1", "note> "))
    if line and line.strip():
        add_note(line, nbname)


def cmd_table(args, nbname):
    tag, title = split_tag(" ".join(args))
    if not sys.stdin.isatty():
        data = [l for l in sys.stdin.read().splitlines() if l.strip()]
        rows = [split_cells(l) for l in data]
        if len(rows) < 1:
            die("No table data on input.")
    else:
        print(col("2", "Separate cells with commas (or tabs). Empty line or 'end' finishes."))
        head = ask(col("1", "columns> "))
        if not head or not head.strip():
            warn("No columns; cancelled.")
            return
        rows = [split_cells(head)]
        while True:
            line = ask(col("1", f"row {len(rows)}> "))
            if line is None or not line.strip() or line.strip().lower() in ("end", "end table", "."):
                break
            rows.append(split_cells(line))
    save_entry(nbname, tag, format_table(title, rows[0], rows[1:]))
    print(col("2", f"  ({len(rows) - 1} rows)"))


def slug(text):
    s = re.sub(r"[^\w.-]+", "-", text.strip()).strip("-.").lower()
    return s[:60] or "pic"


def grab_clipboard_image(dest):
    if os.name == "nt":
        ps = ("Add-Type -AssemblyName System.Windows.Forms,System.Drawing; "
              "$i=[System.Windows.Forms.Clipboard]::GetImage(); if(-not $i){exit 3}; "
              "$i.Save($env:WORKNOTE_OUT,[System.Drawing.Imaging.ImageFormat]::Png)")
        env = dict(os.environ, WORKNOTE_OUT=str(dest))
        r = subprocess.run(["powershell.exe", "-NoProfile", "-STA", "-Command", ps], env=env)
        return r.returncode == 0 and dest.exists()
    for cmd in (["wl-paste", "--type", "image/png"], ["xclip", "-selection", "clipboard", "-t", "image/png", "-o"]):
        if shutil.which(cmd[0]):
            r = subprocess.run(cmd, capture_output=True)
            if r.returncode == 0 and r.stdout:
                dest.write_bytes(r.stdout)
                return True
    return False


def cmd_pic(args, nbname):
    clip = "--clip" in args
    args = [a for a in args if a != "--clip"]
    src = None
    if not clip:
        if not args:
            die("Usage: note pic PATH [tag:] [caption]     or   note pic --clip [tag:] [caption]")
        src = Path(strip_quotes(args[0])).expanduser()
        args = args[1:]
        if not src.is_file():
            die(f"File not found: {src}")
    tag, caption = split_tag(" ".join(args))
    assets = notes_dir() / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    stem = slug(caption) if clip else slug(src.stem)
    ext = ".png" if clip else src.suffix.lower()
    base = f"{slug(nbname)}-{stem}"
    dest, n = assets / f"{base}{ext}", 2
    while dest.exists():
        dest, n = assets / f"{base}-{n}{ext}", n + 1
    if clip:
        if not grab_clipboard_image(dest):
            die("No image found on the clipboard.")
    else:
        shutil.copy2(src, dest)
    caption = caption or (src.stem if src else "screenshot")
    save_entry(nbname, tag, [f"- ![{caption}](assets/{dest.name})"])


def matches_tag(tag, want):
    return tag == want or tag.startswith(want + "/")


def cmd_show_tag(want, nbname, everywhere):
    want = norm_tag(want)
    paths = all_notebook_paths() if everywhere else [notebook_path(nbname)]
    found = 0
    for p in paths:
        if not p.exists():
            continue
        nb = Notebook(p)
        secs = [(t, e) for t, e in nb.ordered() if matches_tag(t, want)]
        if not secs:  # fall back to partial match, e.g. "access" -> sel/access
            secs = [(t, e) for t, e in nb.ordered() if want in t]
        if secs:
            found += sum(len(e) for _, e in secs)
            show_sections(nb, secs, show_nb=everywhere or nb.name != nbname)
    if not found:
        warn(f"No entries tagged '{want}'" + ("" if everywhere else " here (try adding -g)."))


def cmd_tags(nbname, everywhere):
    paths = all_notebook_paths() if everywhere else [notebook_path(nbname)]
    any_shown = False
    for p in paths:
        if not p.exists():
            continue
        nb = Notebook(p)
        if everywhere:
            print(col("1", nb.name))
        tops = {}
        for t, e in nb.ordered():
            tops.setdefault(t.split("/")[0], []).append((t, len(e)))
        for top, items in tops.items():
            total = sum(n for _, n in items)
            print("  " + col("1;35", top) + col("2", f"  {total}"))
            for t, n in items:
                if t != top:
                    print("    " + col("36", t) + col("2", f"  {n}"))
        any_shown = True
    if not any_shown:
        warn("No notes yet.")


def cmd_search(terms, nbname, everywhere):
    terms = [t.lower() for t in terms if t.strip()]
    if not terms:
        die("Usage: note -s WORDS   (this notebook)   |   note -S WORDS   (all notebooks)")
    paths = all_notebook_paths() if everywhere else [notebook_path(nbname)]
    if not everywhere and not paths[0].exists():
        die(f"No notebook for this folder ({nbname}). Use  note -S {' '.join(terms)}  to search all.")
    hits = 0
    for p in paths:
        if not p.exists():
            continue
        nb = Notebook(p)
        for tag, entries in nb.ordered():
            shown_heading = False
            for e in entries:
                hay = (tag + "\n" + "\n".join(e)).lower()
                if all(t in hay for t in terms):
                    if not shown_heading:
                        print_tag_heading(tag, nb.name if everywhere else None)
                        shown_heading = True
                    print_entry(e, terms)
                    hits += 1
    if everywhere:
        hits += search_linked(terms)
    print(col("2", f"{hits} match(es)") if hits else col("33", "No matches."))


# ------------------------------------------------------------ linked files --

def linked_files():
    return [Path(x) for x in load_config().get("links", [])]


def search_linked(terms):
    """Search other Markdown files line by line; a line matches when all words appear
    in it or in the headings above it."""
    hits = 0
    for path in linked_files():
        if not path.is_file():
            warn(f"Linked file not found: {path}  (note --unlink {path.stem})")
            continue
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError as e:
            warn(f"Cannot read {path}: {e}")
            continue
        heads, fence, shown = [], None, None
        for line in text.replace("\r\n", "\n").split("\n"):
            if fence:
                if _closes_fence(line, fence):
                    fence = None
                    continue
            else:
                fm = re.match(r"^\s*(`{3,}|~{3,})", line)
                if fm:
                    fence = fm.group(1)
                    continue
                hm = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
                if hm:
                    level = len(hm.group(1))
                    heads = [h for h in heads if h[0] < level] + [(level, hm.group(2))]
                    continue
            if not line.strip() or re.match(r"^\s*\|[\s|:-]+\|\s*$", line):
                continue
            path_txt = " > ".join(h for _, h in heads)
            hay = (path_txt + "\n" + line).lower()
            if all(t in hay for t in terms):
                key = (str(path), path_txt)
                if shown != key:
                    print(col("2", f"{path.stem} › ") + col("1;36", path_txt or "(top)"))
                    shown = key
                print(wrap_display(paint(line.rstrip(), terms)))
                hits += 1
    return hits


def cmd_link(arg):
    if not arg:
        die("Usage: note --link PATH\\TO\\FILE.md")
    path = Path(strip_quotes(arg)).expanduser().resolve()
    if not path.is_file():
        die(f"File not found: {path}")
    cfg = load_config()
    links = cfg.get("links", [])
    if str(path) in links:
        warn(f"Already linked: {path}")
        return
    cfg["links"] = links + [str(path)]
    save_config(cfg)
    ok(f"Linked {path}. It is now included in  note -S  (read-only).")


def cmd_unlink(arg):
    cfg = load_config()
    links = cfg.get("links", [])
    keep = [x for x in links if not (Path(x).stem.lower() == strip_quotes(arg).lower()
                                     or x.lower() == str(Path(strip_quotes(arg)).expanduser().resolve()).lower())]
    if len(keep) == len(links):
        die(f"No linked file matches '{arg}'. See  note --links")
    cfg["links"] = keep
    save_config(cfg)
    ok(f"Unlinked {len(links) - len(keep)} file(s). The file itself was not touched.")


def cmd_links():
    links = linked_files()
    if not links:
        print("  (no linked files)  add one with  note --link PATH")
    for p in links:
        print("  " + col("1", p.stem) + col("2", f"  {p}") + ("" if p.is_file() else col("33", "  (missing)")))


def cmd_list(nbname):
    p = notebook_path(nbname)
    if not p.exists():
        warn(f"No notebook for '{nbname}' yet. Existing notebooks:")
        cmd_notebooks()
        return
    nb = Notebook(p)
    print(col("1", f"── {nb.name} ──") + col("2", f"  {p}"))
    print()
    show_sections(nb, nb.ordered())


def cmd_notebooks():
    paths = all_notebook_paths()
    if not paths:
        print("  (none yet)")
    for p in paths:
        nb = Notebook(p)
        n = sum(len(e) for _, e in nb.ordered())
        print("  " + col("1", nb.name) + col("2", f"  {n} entries"))


def cmd_edit(nbname):
    p = notebook_path(nbname)
    nb = Notebook(p)
    if not p.exists():
        nb.save()
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if editor:
        cmd = shlex.split(editor, posix=(os.name != "nt")) + [str(p)]
    elif os.name == "nt":
        cmd = ["notepad.exe", str(p)]
    else:
        cmd = [shutil.which("nano") or "vi", str(p)]
    subprocess.call(cmd)
    Notebook(p).save()
    after_change(f"edit: {nb.name}")
    ok(f"Saved and re-organized {nb.name}")


def cmd_default(value):
    cfg = load_config()
    if not value:
        cur = cfg.get("default")
        print(f"default notebook: {cur}" if cur else "default notebook: off (each folder has its own)")
        return
    if value.lower() in ("off", "none", "folder"):
        cfg.pop("default", None)
        save_config(cfg)
        ok("Notes go to the current folder's notebook again.")
        return
    cfg["default"] = value
    save_config(cfg)
    ok(f"All notes now go to {value}{SUFFIX} unless you use -n NAME.")


def cmd_merge(src_name, dest_name):
    src = notebook_path(src_name)
    if not src.exists():
        die(f"No notebook named '{src_name}'. See  note -N")
    dest = notebook_path(dest_name)
    if src.resolve() == dest.resolve():
        die("Source and destination are the same notebook.")
    a, b = Notebook(src), Notebook(dest)
    moved = skipped = 0
    for tag, entries in a.ordered():
        for e in entries:
            if b.add(tag, e):
                moved += 1
            else:
                skipped += 1
    b.save()
    src.unlink()
    after_change(f"merge: {a.name} -> {b.name}")
    ok(f"Moved {moved} entries from {a.name} into {b.name}"
       + (f" ({skipped} duplicates skipped)" if skipped else "") + f"; {src.name} removed.")


def cmd_autosync(value):
    cfg = load_config()
    if value not in ("on", "off"):
        print(f"autosync is {'on' if cfg.get('autosync') else 'off'}")
        return
    cfg["autosync"] = value == "on"
    save_config(cfg)
    ok(f"autosync {value}")


def print_tags_plain():
    tags = set()
    for p in all_notebook_paths():
        tags.update(t for t, _ in Notebook(p).ordered())
    print("\n".join(sorted(tags)))


# -------------------------------------------------------------------- main --

def main(argv):
    setup_console()
    nbname = None

    # raw text from the shell integration (keeps #, >, |, ; etc. untouched)
    raw = os.environ.pop("WORKNOTE_RAW", None)
    if argv[:1] == ["--b64"]:
        raw = base64.b64decode(argv[1] if len(argv) > 1 else "").decode("utf-8") if len(argv) > 1 else ""
        argv = []
    elif argv[:1] == ["--raw"]:
        raw = " ".join(argv[1:])
        argv = []
    if raw is not None:
        m = re.match(r"^\s*(?:-n|--notebook)\s+(\S+)\s*(.*)$", raw, re.S)
        if m:
            nbname, raw = m.group(1), m.group(2)
        else:
            nbname = default_notebook_name()
        if raw.strip():
            add_note(raw, nbname)
        else:
            prompt_mode(nbname)
        return

    if len(argv) >= 2 and argv[0] in ("-n", "--notebook"):
        nbname, argv = argv[1], argv[2:]
    nbname = nbname or default_notebook_name()

    if not argv:
        prompt_mode(nbname)
        return
    a, rest = argv[0], argv[1:]
    everywhere = any(x in ("-g", "-a", "--all") for x in rest)
    rest_clean = [x for x in rest if x not in ("-g", "-a", "--all")]

    if a in ("-h", "--help", "help"):
        print(__doc__)
    elif a in ("-V", "--version"):
        print(f"note {VERSION}")
    elif a in ("-l", "--list"):
        if everywhere:
            for p in all_notebook_paths():
                cmd_list(Notebook(p).name)
        else:
            cmd_list(rest_clean[0] if rest_clean else nbname)
    elif a in ("-s", "--search"):
        cmd_search(rest_clean, nbname, everywhere)
    elif a in ("-S", "-g", "-a", "--search-all"):
        cmd_search(rest_clean, nbname, True)
    elif a in ("-t", "--tag"):
        if not rest_clean:
            die("Usage: note -t TAG [-g]")
        cmd_show_tag(rest_clean[0], nbname, everywhere)
    elif a in ("-T", "--tags"):
        cmd_tags(nbname, everywhere)
    elif a in ("-N", "--notebooks"):
        cmd_notebooks()
    elif a in ("-e", "--edit"):
        cmd_edit(nbname)
    elif a in ("-p", "--paste"):
        add_note(" ".join(rest), nbname, force_paste=True)
    elif a == "table":
        cmd_table(rest, nbname)
    elif a == "pic":
        cmd_pic(rest, nbname)
    elif a == "--organize":
        organize_all(quiet=False)
        after_change("worknote: organize")
    elif a == "--init":
        if not rest_clean:
            die("Usage: note --init USER@HOST:worknotes.git")
        cmd_init(rest_clean[0])
    elif a == "--sync":
        cmd_sync()
    elif a == "--link":
        cmd_link(" ".join(rest))
    elif a == "--unlink":
        cmd_unlink(" ".join(rest))
    elif a == "--links":
        cmd_links()
    elif a == "--import":
        cmd_import(rest, nbname)
    elif a == "--undo":
        cmd_undo()
    elif a == "--rm":
        cmd_rm(rest_clean, nbname, everywhere)
    elif a in ("--mod", "--modify"):
        cmd_mod(rest_clean, nbname, everywhere)
    elif a == "--default":
        cmd_default(rest_clean[0] if rest_clean else "")
    elif a == "--merge":
        if not rest_clean:
            die("Usage: note --merge FROM [INTO]   (INTO defaults to your default/current notebook)")
        cmd_merge(rest_clean[0], rest_clean[1] if len(rest_clean) > 1 else nbname)
    elif a == "--autosync":
        cmd_autosync(rest_clean[0] if rest_clean else "")
    elif a == "--where":
        print(notes_dir())
        print(col("2", f"notes go to: {notebook_path(nbname).name}"))
    elif a == "--tags-plain":
        print_tags_plain()
    elif a.startswith("-") and len(a) > 1 and not TAG_RE.match(" ".join(argv)):
        die(f"Unknown option {a}. See  note -h")
    else:
        add_note(" ".join(argv), nbname)


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except KeyboardInterrupt:
        print()
        sys.exit(130)
    except BrokenPipeError:
        sys.stderr.close()
