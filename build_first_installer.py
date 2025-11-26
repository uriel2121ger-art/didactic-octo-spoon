#!/usr/bin/env python3
"""Genera un instalador autoextraíble para distribuir la primera versión del POS."""
from __future__ import annotations

import argparse
import os
import tarfile
import tempfile
from pathlib import Path
from typing import Iterable, Sequence

BASE_DIR = Path(__file__).resolve().parent
DIST_DIR = BASE_DIR / "dist"
DEFAULT_NAME = "pos_v1_installer.run"

# Archivos esenciales que se incluirán en el paquete inicial.
PAYLOAD_FILES: Sequence[Path] = [
    Path("LICENSE"),
    Path("README.md"),
    Path("requirements.txt"),
    Path("MAD_POS_v1.3.md"),
    Path("pos_core.py"),
    Path("pos_app.py"),
    Path("initialize_pos_env.py"),
    Path("run_pos.py"),
    Path("install_pos.sh"),
]

STUB_TEMPLATE = """#!/usr/bin/env bash
set -euo pipefail

ARCHIVE_MARK="__ARCHIVE_BELOW__"
TMPDIR=$(mktemp -d)
cleanup() {
    rm -rf "${TMPDIR}"
}
trap cleanup EXIT

ARCHIVE_LINE=$(awk -v mark="${ARCHIVE_MARK}" '$0 == mark {print NR + 1; exit 0;}' "$0")
if [[ -z "${ARCHIVE_LINE}" ]]; then
    echo "No se pudo localizar el archivo comprimido embebido." >&2
    exit 1
fi

tail -n +"${ARCHIVE_LINE}" "$0" | tar -xz -C "${TMPDIR}"
chmod +x "${TMPDIR}/install_pos.sh"
cd "${TMPDIR}"
./install_pos.sh "$@"
exit $?
${ARCHIVE_MARK}
"""


def ensure_files(paths: Iterable[Path]) -> None:
    missing = [str(path) for path in paths if not (BASE_DIR / path).exists()]
    if missing:
        raise FileNotFoundError(
            "No se encontraron los archivos necesarios para construir el instalador: "
            + ", ".join(missing)
        )


def build_tarball(target: Path, files: Sequence[Path]) -> None:
    with tarfile.open(target, "w:gz") as tar:
        for rel_path in files:
            abs_path = BASE_DIR / rel_path
            tar.add(abs_path, arcname=str(rel_path))


def assemble_installer(output_path: Path, tarball: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as installer, open(tarball, "rb") as payload:
        installer.write(STUB_TEMPLATE.encode("utf-8"))
        installer.write(payload.read())
    os.chmod(output_path, 0o755)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Genera un instalador autoextraíble del POS para pruebas de la versión inicial.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DIST_DIR / DEFAULT_NAME,
        help="Ruta donde se escribirá el instalador (por defecto: dist/pos_v1_installer.run)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_files(PAYLOAD_FILES)

    with tempfile.TemporaryDirectory() as tmp:
        tarball_path = Path(tmp) / "payload.tar.gz"
        build_tarball(tarball_path, PAYLOAD_FILES)
        assemble_installer(args.output, tarball_path)

    print(f"Instalador generado correctamente en: {args.output}")
    print("\nEjemplo de uso:")
    print(f"  chmod +x {args.output}")
    print(f"  ./{args.output.name}")


if __name__ == "__main__":
    main()
