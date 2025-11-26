from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import boto3
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from pos_core import POSCore, DB_PATH, DATA_DIR

logger = logging.getLogger(__name__)


class BackupEngine:
    """High-level backup coordinator for database snapshots."""

    def __init__(self, core: POSCore, base_dir: Path | str | None = None, cfg: Optional[dict] = None):
        self.core = core
        self.base_dir = Path(base_dir) if base_dir else DATA_DIR / "backups"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.cfg = cfg or self.core.get_app_config()

    # ------------------------------------------------------------------
    # Core operations
    def create_local_backup(self) -> Path:
        """Create a compressed backup of the SQLite database and log it."""

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        raw_copy = self.base_dir / f"db_{timestamp}.db"
        shutil.copy2(DB_PATH, raw_copy)
        archive_path = shutil.make_archive(str(raw_copy), "zip", root_dir=raw_copy.parent, base_dir=raw_copy.name)
        archive_path = Path(archive_path)
        raw_copy.unlink(missing_ok=True)
        sha256 = self._hash_file(archive_path)
        size_bytes = archive_path.stat().st_size
        self.core.register_backup(
            filename=archive_path.name,
            sha256=sha256,
            size_bytes=size_bytes,
            storage_local=True,
            storage_nas=False,
            storage_cloud=False,
            notes="backup local",
        )
        return archive_path

    def encrypt_backup(self, filepath: Path, key: str) -> Path:
        data = filepath.read_bytes()
        aes_key = hashlib.sha256(key.encode("utf-8")).digest()
        aesgcm = AESGCM(aes_key)
        nonce = os.urandom(12)
        encrypted = aesgcm.encrypt(nonce, data, None)
        target = filepath.with_suffix(filepath.suffix + ".enc")
        target.write_bytes(nonce + encrypted)
        logger.info("Backup encriptado: %s", target)
        return target

    def decrypt_backup(self, filepath: Path, key: str) -> Path:
        data = filepath.read_bytes()
        aes_key = hashlib.sha256(key.encode("utf-8")).digest()
        aesgcm = AESGCM(aes_key)
        nonce, cipher = data[:12], data[12:]
        decrypted = aesgcm.decrypt(nonce, cipher, None)
        target = filepath.with_suffix("")
        target.write_bytes(decrypted)
        return target

    def upload_to_nas(self, filepath: Path, nas_path: str) -> bool:
        try:
            target_dir = Path(nas_path)
            target_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(filepath, target_dir / filepath.name)
            logger.info("Backup copiado a NAS: %s", target_dir)
            return True
        except Exception:  # noqa: BLE001
            logger.exception("No se pudo copiar backup a NAS")
            return False

    def upload_to_s3(self, filepath: Path, *, endpoint_url: str, access_key: str, secret_key: str, bucket: str, prefix: str = "") -> bool:
        try:
            session = boto3.session.Session()
            client = session.client(
                "s3",
                endpoint_url=endpoint_url or None,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
            )
            key = f"{prefix.rstrip('/')}/{filepath.name}" if prefix else filepath.name
            client.upload_file(str(filepath), bucket, key)
            logger.info("Backup subido a S3: s3://%s/%s", bucket, key)
            return True
        except Exception:  # noqa: BLE001
            logger.exception("No se pudo subir backup a S3 compatible")
            return False

    def retention_cleanup(self, days: int) -> None:
        cutoff = datetime.now() - timedelta(days=days)
        for file in self.base_dir.glob("db_*.zip"):
            mtime = datetime.fromtimestamp(file.stat().st_mtime)
            if mtime < cutoff:
                try:
                    file.unlink()
                    logger.info("Backup removido por retención: %s", file.name)
                except Exception:  # noqa: BLE001
                    logger.exception("No se pudo eliminar backup viejo")

    def restore_backup(self, filepath: Path, decrypt_key: str | None = None) -> None:
        target = filepath
        if decrypt_key and filepath.suffix == ".enc":
            target = self.decrypt_backup(filepath, decrypt_key)
        if target.suffix == ".zip":
            with tempfile.TemporaryDirectory() as tmpdir:
                shutil.unpack_archive(str(target), tmpdir)
                db_candidates = list(Path(tmpdir).glob("*.db"))
                if not db_candidates:
                    raise FileNotFoundError("Backup sin base de datos")
                shutil.copy2(db_candidates[0], DB_PATH)
        else:
            shutil.copy2(target, DB_PATH)
        cfg = self.core.read_config()
        cfg["setup_completed"] = True
        self.core.write_config(cfg)
        logger.info("Base restaurada desde %s", filepath)

    # ------------------------------------------------------------------
    def _hash_file(self, path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    # ------------------------------------------------------------------
    def auto_backup_flow(self) -> None:
        cfg = self.core.get_app_config()
        local_enabled = bool(cfg.get("backup_auto_on_close", False))
        if not local_enabled:
            return
        backup = self.create_local_backup()
        encrypted_path = backup
        if cfg.get("backup_encrypt"):
            key = cfg.get("backup_encrypt_key", "")
            if not key:
                logger.warning("Cifrado habilitado sin clave; omitiendo encriptado")
            else:
                encrypted_path = self.encrypt_backup(backup, key)
        if cfg.get("backup_nas_enabled"):
            self.upload_to_nas(encrypted_path, cfg.get("backup_nas_path", ""))
        if cfg.get("backup_cloud_enabled"):
            self.upload_to_s3(
                encrypted_path,
                endpoint_url=cfg.get("backup_s3_endpoint", ""),
                access_key=cfg.get("backup_s3_access_key", ""),
                secret_key=cfg.get("backup_s3_secret_key", ""),
                bucket=cfg.get("backup_s3_bucket", ""),
                prefix=cfg.get("backup_s3_prefix", ""),
            )
        if cfg.get("backup_retention_enabled"):
            days = int(cfg.get("backup_retention_days", 30))
            self.retention_cleanup(days)


def test_nas_access(path: str) -> tuple[bool, str]:
    try:
        target = Path(path)
        target.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target, delete=True) as tmp:
            tmp.write(b"test")
        return True, "OK"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def test_s3_access(endpoint_url: str, access_key: str, secret_key: str, bucket: str) -> tuple[bool, str]:
    try:
        session = boto3.session.Session()
        client = session.client(
            "s3",
            endpoint_url=endpoint_url or None,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
        client.list_objects_v2(Bucket=bucket, MaxKeys=1)
        return True, "OK"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
