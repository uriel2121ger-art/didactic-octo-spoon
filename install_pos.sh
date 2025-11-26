#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_CMD=""

function have_cmd() {
    command -v "$1" >/dev/null 2>&1
}

function ensure_python() {
    if have_cmd python3; then
        PYTHON_CMD="python3"
        return
    fi
    if have_cmd python; then
        PYTHON_CMD="python"
        return
    fi

    if have_cmd apt-get; then
        echo "Python no está instalado. Se intentará instalar python3 y pip usando apt-get."
        if [[ $EUID -ne 0 ]]; then
            echo "Se requieren privilegios de superusuario. Es posible que se te solicite la contraseña de sudo."
        fi
        local APT_CMD=(apt-get)
        if [[ $EUID -ne 0 ]]; then
            APT_CMD=(sudo apt-get)
        fi
        "${APT_CMD[@]}" update
        "${APT_CMD[@]}" install -y python3 python3-pip python3-venv
        PYTHON_CMD="python3"
        return
    fi

    echo "❌ No se encontró Python ni un gestor de paquetes compatible para instalarlo automáticamente." >&2
    echo "Instala Python 3.10 o superior manualmente y vuelve a ejecutar este script." >&2
    exit 1
}

ensure_python

if [[ -z "$PYTHON_CMD" ]]; then
    echo "❌ No se pudo determinar el intérprete de Python a utilizar." >&2
    exit 1
fi

"$PYTHON_CMD" "$SCRIPT_DIR/run_pos.py" "$@"
