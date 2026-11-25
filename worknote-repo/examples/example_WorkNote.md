# example — Work Notes

<!-- Managed by the `note` tool. Entries sit under `## tag` / `### tag/sub` headings, sorted by tag. Hand edits are fine; run `note --organize` afterwards. -->

## inbox

- remember to renew the lab certificate

## git

### git/branch

- `git switch -c NAME` — create and switch to a new branch

### git/undo

- `git restore FILE` — discard changes to a file

## lab

### lab/hosts

- **Lab hosts**

  | host | ip | role |
  | --- | --- | --- |
  | web01 | 10.0.0.5 | frontend |
  | db01 | 10.0.0.9 | database |

## linux

### linux/disk

- `df -h` — free space per filesystem
- `du -sh * | sort -h` — size of each item in this folder

### linux/systemd

- Minimal service unit
  ```
  [Unit]
  Description=My service

  [Service]
  ExecStart=/usr/local/bin/myapp
  Restart=on-failure
  ```

## ssh

### ssh/keys

- `ssh-keygen -t ed25519` — create a key pair

## vim

### vim/copy

- `yy` — copy (yank) current line
- `"+y` — copy selection to system clipboard
- `p / P` — paste after / before cursor

### vim/search

- `/text` — search forward
- `:%s/old/new/g` — replace all in file
