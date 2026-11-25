# WorkNote - zsh integration.  install.sh adds this to ~/.zshrc:
#   source "$HOME/.local/share/worknote/note.zsh"

typeset -g WORKNOTE_PY="${0:A:h}/note.py"

note() { python3 "$WORKNOTE_PY" "$@" }

# zsh would treat  # > | ; &  * ?  specially and cut your note. This Enter hook
# sends everything typed after "note " to the tool untouched (base64-encoded),
# and keeps the line exactly as typed in history.
_worknote_accept_line() {
  emulate -L zsh
  setopt extendedglob
  local rest
  if [[ $BUFFER == [[:space:]]#note[[:space:]]##(#b)(*) ]]; then
    rest=$match[1]
    if [[ -n ${rest//[[:space:]]/} ]] &&
       [[ $rest != -* || $rest == (-p|-n)[[:space:]]* ]] &&
       [[ $rest != (table|pic)(|[[:space:]]*) ]]; then
      print -s -- "$BUFFER"
      BUFFER="note --b64 $(print -rn -- "$rest" | base64 | tr -d '\n')"
    fi
  fi
  zle .accept-line
}
zle -N accept-line _worknote_accept_line

_worknote_skip_history() { [[ $1 != 'note --b64 '* ]] }
autoload -Uz add-zsh-hook && add-zsh-hook zshaddhistory _worknote_skip_history

# Tab after "note " completes the tags you have already used
_worknote_complete() {
  (( CURRENT == 2 )) || return 1
  local -a tags
  tags=(${(f)"$(python3 "$WORKNOTE_PY" --tags-plain 2>/dev/null)"})
  compadd -S ': ' -- $tags
}
(( $+functions[compdef] )) && compdef _worknote_complete note
