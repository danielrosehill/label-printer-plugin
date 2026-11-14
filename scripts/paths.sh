#!/bin/sh
# Where label-printer keeps its state, and which rule fired. Delegates to labelctl.py so
# there is one implementation.
#
#   machine registry -> ~/.claude-plugins/label-printer/printers.json  (never committed)
#   user data dir    -> <user-data-root>/label-printer/                (config.json: label_templates_repo)
#   Label-Templates  -> the user's repo: printers.json/.md, styles.json, templates/
#
# Usage:  sh paths.sh            KEY=VALUE lines
#         sh paths.sh --json     one JSON object
set -eu
here=$(cd "$(dirname "$0")" && pwd)
if [ "${1:-}" = "--json" ]; then
  exec python3 "$here/labelctl.py" paths
fi
python3 "$here/labelctl.py" paths | python3 -c "import json,sys; [print(k.upper() + '=' + ('' if v is None else str(v))) for k, v in json.load(sys.stdin).items()]"
