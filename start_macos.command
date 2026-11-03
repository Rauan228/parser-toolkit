#!/bin/bash
cd -- "$(dirname -- "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
    python3 -m venv .venv || { echo 'Установите Python с python.org. См. README.ru.md'; read -r; exit 1; }
fi
.venv/bin/python -m pip install -e '.[contacts]' || { read -r; exit 1; }
.venv/bin/python -m parser_toolkit gui || { read -r; exit 1; }
