#!/bin/sh
# Mac launcher for JARVIS.
#   sh jarvis.sh            start the server and open the browser
#   sh jarvis.sh eval       run the golden set against the real brain
#   sh jarvis.sh backup     back up logs, photos, debriefs, reference, evals, settings
cd "$(dirname "$0")" || exit 1
case "$1" in
  eval)   shift; exec python3 jarvis/eval.py "$@" ;;
  backup) shift; exec python3 jarvis/backup.py "$@" ;;
  *)      exec python3 jarvis/server.py --open "$@" ;;
esac
