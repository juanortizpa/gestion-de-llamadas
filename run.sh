#!/usr/bin/env sh
# macOS y Linux: ./run.sh  (o: sh run.sh). Solo busca Python 3.12+ y delega todo en iniciar.py.
cd "$(dirname "$0")" || exit 1

for py in python3.14 python3.13 python3.12 python3 python; do
  if command -v "$py" >/dev/null 2>&1; then
    exec "$py" iniciar.py "$@"
  fi
done

echo "Python 3.12 o superior no esta instalado."
echo "  macOS:          brew install python@3.12"
echo "  Ubuntu/Debian:  sudo apt install python3.12 python3.12-venv"
echo "  Otros:          https://www.python.org/downloads/"
exit 1
