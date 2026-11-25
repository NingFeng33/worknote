#!/bin/sh
# WorkNote installer for Ubuntu (zsh).  Run:  sh install.sh
set -e
src=$(cd "$(dirname "$0")" && pwd)
dest="$HOME/.local/share/worknote"
mkdir -p "$dest"
cp "$src/note.py" "$src/note.zsh" "$dest/"
line='source "$HOME/.local/share/worknote/note.zsh"'
touch "$HOME/.zshrc"
grep -q 'worknote/note.zsh' "$HOME/.zshrc" || printf '\n%s\n' "$line" >> "$HOME/.zshrc"
echo "Installed to $dest and added to ~/.zshrc"
echo "Open a new terminal (or: source ~/.zshrc), then:  note --init USER@SERVER:worknotes.git"
