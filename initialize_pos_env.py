#!/usr/bin/env python3
"""Bootstrap script for the POS environment.

Creates the data directory, initializes the SQLite database, and seeds minimal
configuration so the main application can decide whether to show the welcome
wizard.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from pos_core import POSCore, CONFIG_FILE, DATA_DIR


def ensure_directories() -> None:
    for path in (DATA_DIR, Path("tickets"), Path("reports"), Path("backups")):
        path.mkdir(parents=True, exist_ok=True)


def initialize_database() -> None:
    core = POSCore()
    core.ensure_schema()
    seed_config(core)


def seed_config(core: POSCore, *, force: bool = False) -> None:
    cfg = core.read_config()
    if cfg and not force:
        return
    cfg.setdefault("setup_completed", False)
    cfg.setdefault("theme", "kde-light")
    cfg.setdefault("mode", "server")
    cfg.setdefault("server_url", "http://127.0.0.1:8000")
    core.write_config(cfg)


def main() -> None:
    parser = argparse.ArgumentParser(description="Inicializa el entorno del POS")
    parser.add_argument("--force", action="store_true", help="Sobrescribe la configuración inicial si ya existe")
    args = parser.parse_args()

    ensure_directories()
    core = POSCore()
    core.ensure_schema()
    seed_config(core, force=args.force)
    print(f"Base de datos creada en {core.db_path}")
    print(f"Archivo de configuración: {CONFIG_FILE}")


if __name__ == "__main__":
    main()
