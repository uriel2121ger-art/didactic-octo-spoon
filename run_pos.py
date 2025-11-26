#!/usr/bin/env python3
"""Entry point that decides whether to show the welcome wizard or launch the app."""
from __future__ import annotations

import argparse
import sys

from pos_app import main as run_gui
from initialize_pos_env import main as init_env


def main() -> None:
    parser = argparse.ArgumentParser(description="Ejecuta el POS o inicializa el entorno")
    parser.add_argument("--init-only", action="store_true", help="Solo inicializa la base de datos y sale")
    args = parser.parse_args()

    init_env()
    if args.init_only:
        print("Inicialización completada. Ejecuta sin --init-only para abrir la app.")
        return

    run_gui()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
