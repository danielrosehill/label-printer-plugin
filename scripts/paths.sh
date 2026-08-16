#!/bin/sh
# Resolve where this plugin keeps its two kinds of state, and say which rule fired.
#
#   machine config  -> ~/.claude-plugins/label-printer/     never committed; holds
#                      printers.json, which is true on this box and this LAN only
#   user content    -> <user-data-root>/label-printer/      worth mirroring; holds
#                      templates/, which are portable between machines
#
# Never hard-code either path in a skill or a command. Ask this script.
#
# Usage:  sh paths.sh            KEY=VALUE lines
#         sh paths.sh --json     one JSON object
set -eu

# Nothing this plugin owns may live under ~/.claude — that is Claude Code's own
# state directory, it is replaced on update, and the whole point of a user-data
# root is that it outlives the tool. Hard error, no override.
guard() {
  case "$1" in
    "$HOME/.claude"|"$HOME/.claude"/*)
      echo "label-printer: refusing path inside ~/.claude: $1" >&2
      exit 2
      ;;
  esac
}

PLUGIN=label-printer

# --- machine config -------------------------------------------------------
if [ -n "${LABEL_PRINTER_CONFIG_DIR:-}" ]; then
  CONFIG_DIR="$LABEL_PRINTER_CONFIG_DIR"; CONFIG_SOURCE=env-override
else
  CONFIG_DIR="$HOME/.claude-plugins/$PLUGIN"; CONFIG_SOURCE=default
fi
CONFIG_FILE="$CONFIG_DIR/printers.json"

# --- user content ---------------------------------------------------------
# explicit override -> $CLAUDE_USER_DATA -> adopt whichever root already exists
# -> default. Adopting matters: defaulting blindly to ~/.claude-user-data on a
# box that already uses ~/.local/share/claude-plugins creates a second root and
# splits the user's content across both.
XDG_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/claude-plugins"
if [ -n "${LABEL_PRINTER_DATA:-}" ]; then
  DATA_ROOT="$LABEL_PRINTER_DATA"; DATA_SOURCE=env-override
elif [ -n "${CLAUDE_USER_DATA:-}" ]; then
  DATA_ROOT="$CLAUDE_USER_DATA"; DATA_SOURCE=claude-user-data
elif [ -d "$HOME/.claude-user-data" ]; then
  DATA_ROOT="$HOME/.claude-user-data"; DATA_SOURCE=adopted-existing
elif [ -d "$XDG_ROOT" ]; then
  DATA_ROOT="$XDG_ROOT"; DATA_SOURCE=adopted-existing
else
  DATA_ROOT="$HOME/.claude-user-data"; DATA_SOURCE=default
fi
DATA_DIR="$DATA_ROOT/$PLUGIN"
TEMPLATES="$DATA_DIR/templates"

guard "$CONFIG_DIR"
guard "$DATA_DIR"

if [ "${1:-}" = "--json" ]; then
  printf '{\n'
  printf '  "config_dir": "%s",\n'    "$CONFIG_DIR"
  printf '  "config_file": "%s",\n'   "$CONFIG_FILE"
  printf '  "config_source": "%s",\n' "$CONFIG_SOURCE"
  printf '  "data_root": "%s",\n'     "$DATA_ROOT"
  printf '  "data_dir": "%s",\n'      "$DATA_DIR"
  printf '  "templates": "%s",\n'     "$TEMPLATES"
  printf '  "data_source": "%s"\n'    "$DATA_SOURCE"
  printf '}\n'
else
  echo "CONFIG_DIR=$CONFIG_DIR"
  echo "CONFIG_FILE=$CONFIG_FILE"
  echo "CONFIG_SOURCE=$CONFIG_SOURCE"
  echo "DATA_ROOT=$DATA_ROOT"
  echo "DATA_DIR=$DATA_DIR"
  echo "TEMPLATES=$TEMPLATES"
  echo "DATA_SOURCE=$DATA_SOURCE"
fi
