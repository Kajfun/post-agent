#!/usr/bin/env bash
set -u
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1

PY=""
for kandydat in python3 python; do
  if command -v "$kandydat" >/dev/null 2>&1; then PY="$kandydat"; break; fi
done

if [ -z "$PY" ]; then
  echo
  echo "Nie znalazlem Pythona."
  echo "macOS:  brew install python3"
  echo "Linux:  sudo apt install python3 python3-venv"
  echo
  read -r -p "Enter zamyka to okno. " _
  exit 1
fi

"$PY" narzedzia/uruchom.py "$@"
kod=$?

echo
echo "Gotowe. Mozesz zamknac to okno."
read -r -p "Enter zamyka. " _
exit $kod
