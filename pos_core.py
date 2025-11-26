#!/usr/bin/env python3
"""Core data and persistence layer for POS Novedades Lupita Ultra Pro Max 2025.

This module centralizes database access, schema creation, and business helpers
for sales, inventory, layaways, and reporting. It stays GUI-free so it can be
reused by CLI tools, the Qt application, and the API server.
"""
from __future__ import annotations

import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
import sqlite3
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Sequence

# Imports CFDI/PAC opcionales (stubs por ahora)
try:
    from fiscal.cfdi_builder import build_cfdi_ingreso_xml, build_cfdi_pago_xml
except ModuleNotFoundError:
    build_cfdi_ingreso_xml = None
    build_cfdi_pago_xml = None

try:
    from fiscal.cfdi_pac_client import PACClient
except ModuleNotFoundError:
    PACClient = None


APP_NAME = "POS Ultra Pro Max"
DATA_DIR = Path("data")
DB_PATH = DATA_DIR / "pos.db"
CONFIG_FILE = DATA_DIR / "pos_config.json"

LOG_PATH = DATA_DIR / "pos.log"
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_SCHEMA = r"""
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT,
    role TEXT NOT NULL DEFAULT 'admin',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS branches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    currency TEXT NOT NULL DEFAULT 'MXN',
    timezone TEXT NOT NULL DEFAULT 'America/Merida',
    is_default INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS app_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT NOT NULL,
    last_name TEXT,
    phone TEXT,
    email TEXT,
    email_fiscal TEXT,
    notes TEXT,
    vip INTEGER NOT NULL DEFAULT 0,
    credit_limit REAL NOT NULL DEFAULT 0,
    credit_balance REAL NOT NULL DEFAULT 0,
    credit_authorized INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_active INTEGER NOT NULL DEFAULT 1,
    -- Campos fiscales
    rfc TEXT,
    razon_social TEXT,
    domicilio1 TEXT,
    domicilio2 TEXT,
    colonia TEXT,
    municipio TEXT,
    estado TEXT,
    pais TEXT,
    codigo_postal TEXT,
    regimen_fiscal TEXT
);

CREATE TABLE IF NOT EXISTS previous_credit_balances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    balance REAL NOT NULL,
    description TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(customer_id) REFERENCES customers(id)
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT UNIQUE NOT NULL,
    barcode TEXT UNIQUE,
    name TEXT NOT NULL,
    description TEXT,
    price REAL NOT NULL DEFAULT 0.0,
    price_wholesale REAL NOT NULL DEFAULT 0.0,
    cost REAL NOT NULL DEFAULT 0.0,
    unit TEXT NOT NULL DEFAULT 'Unidad',
    allow_decimal INTEGER NOT NULL DEFAULT 0,
    is_kit INTEGER NOT NULL DEFAULT 0,
    department TEXT,
    provider TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    is_favorite INTEGER NOT NULL DEFAULT 0,
    sale_type TEXT NOT NULL DEFAULT 'unit',
    kit_items TEXT NOT NULL DEFAULT '[]',
    uses_inventory INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS product_stocks (
    product_id INTEGER NOT NULL,
    branch_id INTEGER NOT NULL,
    stock REAL NOT NULL DEFAULT 0,
    reserved REAL NOT NULL DEFAULT 0,
    min_stock REAL NOT NULL DEFAULT 0,
    max_stock REAL NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (product_id, branch_id),
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    FOREIGN KEY (branch_id) REFERENCES branches(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    branch_id INTEGER NOT NULL,
    user_id INTEGER,
    customer_id INTEGER,
    ts TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    subtotal REAL NOT NULL DEFAULT 0,
    discount REAL NOT NULL DEFAULT 0,
    total REAL NOT NULL DEFAULT 0,
    payment_method TEXT NOT NULL DEFAULT 'cash',
    payment_breakdown TEXT NOT NULL DEFAULT '{}',
    reference TEXT,
    card_fee REAL,
    usd_amount REAL,
    usd_exchange REAL,
    voucher_amount REAL,
    check_number TEXT,
    FOREIGN KEY (branch_id) REFERENCES branches(id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE TABLE IF NOT EXISTS sale_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id INTEGER NOT NULL,
    product_id INTEGER,
    qty REAL NOT NULL,
    price REAL NOT NULL,
    discount REAL NOT NULL DEFAULT 0,
    total REAL NOT NULL DEFAULT 0,
    price_includes_tax INTEGER NOT NULL DEFAULT 0,
    metadata TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (sale_id) REFERENCES sales(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS sale_returns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    qty REAL NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (sale_id) REFERENCES sales(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS layaways (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    branch_id INTEGER NOT NULL,
    customer_id INTEGER,
    total REAL NOT NULL,
    deposit REAL NOT NULL DEFAULT 0,
    balance REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pendiente',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    due_date TEXT,
    notes TEXT,
    FOREIGN KEY (branch_id) REFERENCES branches(id),
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE TABLE IF NOT EXISTS layaway_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    layaway_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    qty REAL NOT NULL,
    price REAL NOT NULL,
    discount REAL NOT NULL DEFAULT 0,
    total REAL NOT NULL DEFAULT 0,
    FOREIGN KEY (layaway_id) REFERENCES layaways(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS layaway_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    layaway_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    timestamp TEXT NOT NULL,
    notes TEXT,
    user_id INTEGER,
    FOREIGN KEY(layaway_id) REFERENCES layaways(id),
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS credit_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    timestamp TEXT NOT NULL,
    notes TEXT,
    user_id INTEGER,
    sale_ids TEXT,
    FOREIGN KEY(customer_id) REFERENCES customers(id),
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action TEXT NOT NULL,
    payload TEXT,
    timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS fiscal_config (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    rfc_emisor TEXT NOT NULL DEFAULT '',
    razon_social_emisor TEXT NOT NULL DEFAULT '',
    regimen_fiscal TEXT NOT NULL DEFAULT '601',
    lugar_expedicion TEXT NOT NULL DEFAULT '00000',
    csd_cert_path TEXT,
    csd_key_path TEXT,
    csd_key_password TEXT,
    pac_base_url TEXT,
    pac_user TEXT,
    pac_password TEXT,
    serie_factura TEXT NOT NULL DEFAULT 'F',
    folio_actual INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS cfdi_issued (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id INTEGER,
    customer_id INTEGER,
    uuid TEXT,
    serie TEXT,
    folio TEXT,
    fecha TEXT,
    total REAL,
    xml_path TEXT,
    pdf_path TEXT,
    status TEXT NOT NULL DEFAULT 'vigente',
    tipo_comprobante TEXT NOT NULL DEFAULT 'I',
    uso_cfdi TEXT,
    forma_pago TEXT,
    metodo_pago TEXT,
    moneda TEXT,
    FOREIGN KEY(sale_id) REFERENCES sales(id),
    FOREIGN KEY(customer_id) REFERENCES customers(id)
);

CREATE TABLE IF NOT EXISTS cfdi_cancelled (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cfdi_id INTEGER NOT NULL,
    fecha TEXT NOT NULL,
    motivo TEXT,
    uuid_relacionado TEXT,
    FOREIGN KEY(cfdi_id) REFERENCES cfdi_issued(id)
);

CREATE TABLE IF NOT EXISTS backup_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sha256 TEXT,
    size_bytes INTEGER,
    storage_local INTEGER NOT NULL DEFAULT 1,
    storage_nas INTEGER NOT NULL DEFAULT 0,
    storage_cloud INTEGER NOT NULL DEFAULT 0,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS api_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token TEXT NOT NULL,
    role TEXT NOT NULL,
    description TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_active INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS cash_movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    branch_id INTEGER NOT NULL,
    user_id INTEGER,
    movement_type TEXT NOT NULL,
    amount REAL NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    turn_id INTEGER,
    type TEXT,
    FOREIGN KEY (branch_id) REFERENCES branches(id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (turn_id) REFERENCES turns(id)
);

CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    branch_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    opened_at TEXT NOT NULL,
    closed_at TEXT,
    opening_amount REAL NOT NULL DEFAULT 0.0,
    closing_amount REAL,
    expected_amount REAL,
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    FOREIGN KEY(branch_id) REFERENCES branches(id),
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS inventory_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    branch_id INTEGER NOT NULL,
    delta REAL NOT NULL,
    reason TEXT,
    ref_type TEXT,
    ref_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products(id),
    FOREIGN KEY (branch_id) REFERENCES branches(id)
);
"""


@dataclass
class AppState:
    """Mutable singleton-like state shared by GUI and server."""

    user_id: int = 0
    username: str = ""
    role: str = "admin"
    branch_id: int = 1
    branch_name: str = "Caja Principal"


class POSCore:
    """SQLite-backed convenience wrapper for POS operations."""

    def __init__(self, db_path: Path | str = DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, isolation_level="DEFERRED", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA temp_store=MEMORY;")
        conn.execute("PRAGMA cache_size=-2048;")
        return conn

    def ensure_schema(self) -> None:
        """Create core tables and seed defaults when needed."""
        with self.connect() as conn:
            conn.executescript(DEFAULT_SCHEMA)
            self._migrate_customers(conn)
            self._migrate_products(conn)
            self._migrate_sale_items(conn)
            self._ensure_sale_payment_fields(conn)
            self._ensure_credit_payments(conn)
            self._ensure_layaway_support(conn)
            self._ensure_turn_support(conn)
            self._ensure_audit_logs(conn)
            self._ensure_backup_logs(conn)
            self._ensure_api_tokens(conn)
            self._ensure_fiscal_config(conn)
            self._ensure_previous_credit_table(conn)
            self._ensure_indices(conn)
            self._ensure_default_branch(conn)
            self._ensure_default_user(conn)
            self._ensure_active_branch(conn)
        cfg = self.read_config()
        if "log_level" not in cfg:
            cfg["log_level"] = "INFO"
            self.write_config(cfg)
        self._configure_logging(cfg.get("log_level", "INFO"))
        if "setup_completed" not in cfg:
            cfg["setup_completed"] = False
            self.write_config(cfg)

    def _configure_logging(self, level_name: str) -> None:
        level = getattr(logging, str(level_name).upper(), logging.INFO)
        handlers = [RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=3)]
        if not logging.getLogger().handlers:
            logging.basicConfig(level=level, format="[%(levelname)s] %(name)s: %(message)s", handlers=handlers)
        else:
            logging.getLogger().setLevel(level)
            for h in logging.getLogger().handlers:
                h.setLevel(level)
            if all(not isinstance(h, RotatingFileHandler) for h in logging.getLogger().handlers):
                logging.getLogger().addHandler(handlers[0])

    def _ensure_indices(self, conn: sqlite3.Connection) -> None:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sales_ts_branch ON sales(ts, branch_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sale_items_sale ON sale_items(sale_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_products_sku_barcode ON products(sku, barcode)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_inventory_logs_prod_ts ON inventory_logs(product_id, created_at)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cfdi_sale ON cfdi_issued(sale_id)")

    # ------------------------------------------------------------------
    # Config helpers
    def read_config(self) -> dict[str, Any]:
        if CONFIG_FILE.exists():
            try:
                return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                logger.warning("Config file corrupted, resetting")
        return {}

    def write_config(self, data: dict[str, Any]) -> None:
        CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def get_app_config(self) -> dict[str, Any]:
        """Return a dict with config file plus DB-backed values."""
        cfg = self.read_config()
        with self.connect() as conn:
            active_branch_id = self._get_active_branch_id(conn)
        cfg.setdefault("active_branch_id", active_branch_id)
        cfg.setdefault("mode", "server")
        cfg.setdefault("server_ip", "127.0.0.1")
        cfg.setdefault("server_port", 8000)
        cfg.setdefault("client_id", self._ensure_client_id(cfg))
        cfg.setdefault("last_sync_timestamp", None)
        cfg.setdefault("sync_token", "dev-token")
        cfg.setdefault("sync_interval_seconds", 10)
        cfg.setdefault("multicaja_enabled", True)
        cfg.setdefault("theme", "Light")
        cfg.setdefault("api_external_enabled", False)
        cfg.setdefault("api_external_base_url", "")
        cfg.setdefault("api_dashboard_token", "")
        cfg.setdefault("allowed_origins", "*")
        cfg.setdefault("secret_key", self._ensure_secret_key(cfg))
        cfg.setdefault("backup_auto_on_close", False)
        cfg.setdefault("backup_dir", str(DATA_DIR / "backups"))
        cfg.setdefault("backup_encrypt", False)
        cfg.setdefault("backup_encrypt_key", "")
        cfg.setdefault("backup_nas_enabled", False)
        cfg.setdefault("backup_nas_path", "")
        cfg.setdefault("backup_cloud_enabled", False)
        cfg.setdefault("backup_s3_endpoint", "")
        cfg.setdefault("backup_s3_access_key", "")
        cfg.setdefault("backup_s3_secret_key", "")
        cfg.setdefault("backup_s3_bucket", "")
        cfg.setdefault("backup_s3_prefix", "")
        cfg.setdefault("backup_retention_enabled", False)
        cfg.setdefault("backup_retention_days", 30)
        cfg.setdefault("scanner_prefix", "")
        cfg.setdefault("scanner_suffix", "")
        cfg.setdefault("camera_scanner_enabled", False)
        cfg.setdefault("camera_scanner_index", 0)
        cfg.setdefault("printer_name", "")
        cfg.setdefault("ticket_paper_width", "80mm")
        cfg.setdefault("auto_print_tickets", False)
        cfg.setdefault("cash_drawer_enabled", False)
        cfg.setdefault("cash_drawer_pulse_bytes", "\\x1B\\x70\\x00\\x19\\xFA")
        return cfg

    def _ensure_client_id(self, cfg: dict[str, Any]) -> str:
        cid = cfg.get("client_id")
        if cid:
            return cid
        import uuid

        cid = uuid.uuid4().hex
        cfg["client_id"] = cid
        self.write_config(cfg)
        return cid

    def _ensure_secret_key(self, cfg: dict[str, Any]) -> str:
        key = cfg.get("secret_key")
        if key:
            return key
        import secrets

        key = secrets.token_hex(32)
        cfg["secret_key"] = key
        self.write_config(cfg)
        return key

    def get_active_branch(self) -> int:
        with self.connect() as conn:
            return self._get_active_branch_id(conn)

       # ------------------------------------------------------------------
    # Fiscal configuration
    def update_fiscal_config(self, config: dict) -> None:
        """
        Temporalmente desactivado para evitar errores de SQLite mientras
        completamos la definición de campos fiscales.
        """
        print("update_fiscal_config llamado (TEMP: no se escribe nada en la BD)")
        return

    def get_next_folio(self) -> str:
        with self.connect() as conn:
            cur = conn.execute(
                "SELECT serie_factura, folio_actual FROM fiscal_config WHERE id = 1"
            )
            row = cur.fetchone()
            if not row:
                raise ValueError("Config fiscal no encontrada")
            serie = row["serie_factura"] or "F"
            folio = int(row["folio_actual"] or 1)
            conn.execute(
                "UPDATE fiscal_config SET folio_actual = folio_actual + 1 WHERE id = 1"
            )
            return f"{serie}{folio}"

      # ------------------------------------------------------------------
    # Fiscal configuration
    def get_fiscal_config(self) -> dict:
        """
        Devuelve la configuración fiscal desde la base de datos.
        Si no existe la tabla o el registro, regresa un dict vacío.
        """
        try:
            with self.connect() as conn:
                cur = conn.execute("SELECT * FROM fiscal_config WHERE id = 1")
                row = cur.fetchone()
        except sqlite3.Error:
            # Si la tabla no existe o hay otro problema, regresamos config vacía
            return {}

        if not row:
            return {}

        # sqlite3.Row -> dict normal
        return dict(row)

    def update_fiscal_config(self, config: dict) -> None:
        """
        Temporalmente desactivado para evitar errores de SQLite mientras
        completamos la definición de campos fiscales.
        """
        print("update_fiscal_config llamado (TEMP: no se escribe nada en la BD)")
        return

    def get_next_folio(self) -> str:
        with self.connect() as conn:
            cur = conn.execute(
                "SELECT serie_factura, folio_actual FROM fiscal_config WHERE id = 1"
            )
            row = cur.fetchone()
            if not row:
                raise ValueError("Config fiscal no encontrada")
            serie = row["serie_factura"] or "F"
            folio = int(row["folio_actual"] or 1)
            conn.execute(
                "UPDATE fiscal_config SET folio_actual = folio_actual + 1 WHERE id = 1"
            )
            return f"{serie}{folio}"

    # ------------------------------------------------------------------
    # Internal helpers
    def _ensure_default_branch(self, conn: sqlite3.Connection) -> None:
        cur = conn.execute("SELECT id FROM branches ORDER BY id LIMIT 1")
        if cur.fetchone() is None:
            logger.info("Creating default branch: Caja Principal")
            conn.execute(
                "INSERT INTO branches (name, currency, timezone, is_default) VALUES (?, ?, ?, 1)",
                ("Caja Principal", "MXN", "America/Merida"),
            )

    def _ensure_default_user(self, conn: sqlite3.Connection) -> None:
        cur = conn.execute("SELECT id FROM users WHERE username = ?", ("admin",))
        if cur.fetchone() is None:
            logger.info("Creating default admin user with password 'admin'")
            conn.execute(
                "INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
                ("admin", self._hash_password("admin"), "Administrador", "admin"),
            )

    def _ensure_active_branch(self, conn: sqlite3.Connection) -> None:
        cur = conn.execute("SELECT value FROM app_config WHERE key = 'active_branch_id'")
        row = cur.fetchone()
        if row is None:
            cur_branch = conn.execute(
                "SELECT id, name FROM branches WHERE is_default = 1 ORDER BY id LIMIT 1"
            ).fetchone()
            branch_id = cur_branch["id"] if cur_branch else 1
            conn.execute(
                "INSERT OR REPLACE INTO app_config (key, value) VALUES ('active_branch_id', ?)",
                (str(branch_id),),
            )

    def _migrate_customers(self, conn: sqlite3.Connection) -> None:
        cur = conn.execute("PRAGMA table_info(customers)")
        columns = {row[1] for row in cur.fetchall()}
        migrations: list[tuple[str, str]] = [
            ("last_name", "ALTER TABLE customers ADD COLUMN last_name TEXT"),
            ("notes", "ALTER TABLE customers ADD COLUMN notes TEXT"),
            ("credit_limit", "ALTER TABLE customers ADD COLUMN credit_limit REAL NOT NULL DEFAULT 0"),
            ("credit_balance", "ALTER TABLE customers ADD COLUMN credit_balance REAL NOT NULL DEFAULT 0"),
            ("credit_authorized", "ALTER TABLE customers ADD COLUMN credit_authorized INTEGER NOT NULL DEFAULT 0"),
            ("is_active", "ALTER TABLE customers ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1"),
            ("first_name", "ALTER TABLE customers ADD COLUMN first_name TEXT"),
            ("created_at", "ALTER TABLE customers ADD COLUMN created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP"),
            ("vip", "ALTER TABLE customers ADD COLUMN vip INTEGER NOT NULL DEFAULT 0"),
            ("rfc", "ALTER TABLE customers ADD COLUMN rfc TEXT"),
            ("razon_social", "ALTER TABLE customers ADD COLUMN razon_social TEXT"),
            ("email_fiscal", "ALTER TABLE customers ADD COLUMN email_fiscal TEXT"),
            ("domicilio1", "ALTER TABLE customers ADD COLUMN domicilio1 TEXT"),
            ("domicilio2", "ALTER TABLE customers ADD COLUMN domicilio2 TEXT"),
            ("colonia", "ALTER TABLE customers ADD COLUMN colonia TEXT"),
            ("municipio", "ALTER TABLE customers ADD COLUMN municipio TEXT"),
            ("estado", "ALTER TABLE customers ADD COLUMN estado TEXT"),
            ("pais", "ALTER TABLE customers ADD COLUMN pais TEXT"),
            ("codigo_postal", "ALTER TABLE customers ADD COLUMN codigo_postal TEXT"),
            ("regimen_fiscal", "ALTER TABLE customers ADD COLUMN regimen_fiscal TEXT"),
        ]
        for column, statement in migrations:
            if column not in columns:
                try:
                    conn.execute(statement)
                except sqlite3.OperationalError:
                    pass
        if "first_name" in columns and "name" in columns:
            try:
                conn.execute("UPDATE customers SET first_name = first_name OR name WHERE (first_name IS NULL OR first_name = '') AND name IS NOT NULL")
            except sqlite3.OperationalError:
                pass
    def _migrate_sale_items(self, conn: sqlite3.Connection) -> None:
        try:
            conn.execute("ALTER TABLE sale_items ADD COLUMN price_includes_tax INTEGER NOT NULL DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE sale_items ADD COLUMN product_id INTEGER")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE sale_items ADD COLUMN metadata TEXT NOT NULL DEFAULT '{}' ")
        except sqlite3.OperationalError:
            pass

    def _ensure_sale_payment_fields(self, conn: sqlite3.Connection) -> None:
        cur = conn.execute("PRAGMA table_info(sales)")
        columns = {row[1] for row in cur.fetchall()}
        migrations = [
            ("payment_method", "ALTER TABLE sales ADD COLUMN payment_method TEXT NOT NULL DEFAULT 'cash'"),
            ("reference", "ALTER TABLE sales ADD COLUMN reference TEXT"),
            ("card_fee", "ALTER TABLE sales ADD COLUMN card_fee REAL"),
            ("usd_amount", "ALTER TABLE sales ADD COLUMN usd_amount REAL"),
            ("usd_exchange", "ALTER TABLE sales ADD COLUMN usd_exchange REAL"),
            ("voucher_amount", "ALTER TABLE sales ADD COLUMN voucher_amount REAL"),
            ("check_number", "ALTER TABLE sales ADD COLUMN check_number TEXT"),
        ]
        for column, statement in migrations:
            if column not in columns:
                try:
                    conn.execute(statement)
                except sqlite3.OperationalError:
                    pass

    def _migrate_products(self, conn: sqlite3.Connection) -> None:
        """Backfill recently added product columns without breaking older DBs."""

        migrations = [
            ("price_wholesale", "ALTER TABLE products ADD COLUMN price_wholesale REAL NOT NULL DEFAULT 0.0"),
            ("department", "ALTER TABLE products ADD COLUMN department TEXT"),
            ("provider", "ALTER TABLE products ADD COLUMN provider TEXT"),
            ("is_active", "ALTER TABLE products ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1"),
            ("is_favorite", "ALTER TABLE products ADD COLUMN is_favorite INTEGER NOT NULL DEFAULT 0"),
            ("sale_type", "ALTER TABLE products ADD COLUMN sale_type TEXT NOT NULL DEFAULT 'unit'"),
            ("kit_items", "ALTER TABLE products ADD COLUMN kit_items TEXT NOT NULL DEFAULT '[]'"),
            ("uses_inventory", "ALTER TABLE products ADD COLUMN uses_inventory INTEGER NOT NULL DEFAULT 1"),
        ]
        cur = conn.execute("PRAGMA table_info(products)")
        cols = {row[1] for row in cur.fetchall()}
        for column, statement in migrations:
            if column not in cols:
                try:
                    conn.execute(statement)
                except sqlite3.OperationalError:
                    pass

        # product_stocks: ensure max_stock column exists for inventory dashboards
        cur_stocks = conn.execute("PRAGMA table_info(product_stocks)")
        stock_cols = {row[1] for row in cur_stocks.fetchall()}
        if "max_stock" not in stock_cols:
            try:
                conn.execute("ALTER TABLE product_stocks ADD COLUMN max_stock REAL NOT NULL DEFAULT 0")
            except sqlite3.OperationalError:
                pass

    def _ensure_layaway_support(self, conn: sqlite3.Connection) -> None:
        """Ensure layaway-related columns and tables exist."""
        try:
            conn.execute("ALTER TABLE layaways ADD COLUMN due_date TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE layaways ADD COLUMN notes TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE layaways ADD COLUMN balance REAL NOT NULL DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS layaway_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                layaway_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                timestamp TEXT NOT NULL,
                notes TEXT,
                user_id INTEGER,
                FOREIGN KEY(layaway_id) REFERENCES layaways(id),
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            """
        )

    def _ensure_credit_payments(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS credit_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                timestamp TEXT NOT NULL,
                notes TEXT,
                user_id INTEGER,
                sale_ids TEXT,
                FOREIGN KEY(customer_id) REFERENCES customers(id),
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            """
        )

    def _ensure_audit_logs(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT NOT NULL,
                payload TEXT,
                timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            """
        )

    def _ensure_backup_logs(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS backup_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                sha256 TEXT,
                size_bytes INTEGER,
                storage_local INTEGER NOT NULL DEFAULT 1,
                storage_nas INTEGER NOT NULL DEFAULT 0,
                storage_cloud INTEGER NOT NULL DEFAULT 0,
                notes TEXT
            );
            """
        )

    def _ensure_api_tokens(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS api_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token TEXT NOT NULL,
                role TEXT NOT NULL,
                description TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            """
        )

    def _ensure_fiscal_config(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fiscal_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                rfc_emisor TEXT NOT NULL DEFAULT '',
                razon_social_emisor TEXT NOT NULL DEFAULT '',
                regimen_fiscal TEXT NOT NULL DEFAULT '601',
                lugar_expedicion TEXT NOT NULL DEFAULT '00000',
                csd_cert_path TEXT,
                csd_key_path TEXT,
                csd_key_password TEXT,
                pac_base_url TEXT,
                pac_user TEXT,
                pac_password TEXT,
                serie_factura TEXT NOT NULL DEFAULT 'F',
                folio_actual INTEGER NOT NULL DEFAULT 1
            );
            """
        )
        exists = conn.execute("SELECT COUNT(1) FROM fiscal_config").fetchone()[0]
        if not exists:
            conn.execute(
                """
                INSERT INTO fiscal_config (
                    id, rfc_emisor, razon_social_emisor, regimen_fiscal, lugar_expedicion, serie_factura, folio_actual
                ) VALUES (1, 'XAXX010101000', 'Emisor Demo', '601', '00000', 'F', 1)
                """,
            )

    def _ensure_turn_support(self, conn: sqlite3.Connection) -> None:
        try:
            conn.execute("ALTER TABLE cash_movements ADD COLUMN turn_id INTEGER")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE cash_movements ADD COLUMN type TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE sales ADD COLUMN turn_id INTEGER")
        except sqlite3.OperationalError:
            pass
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                branch_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                opened_at TEXT NOT NULL,
                closed_at TEXT,
                opening_amount REAL NOT NULL DEFAULT 0.0,
                closing_amount REAL,
                expected_amount REAL,
                notes TEXT,
                status TEXT NOT NULL DEFAULT 'open',
                FOREIGN KEY(branch_id) REFERENCES branches(id),
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            """
        )

    def _ensure_previous_credit_table(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS previous_credit_balances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                balance REAL NOT NULL,
                description TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(customer_id) REFERENCES customers(id)
            );
            """
        )


    @staticmethod
    def _hash_password(password: str) -> str:
        return hashlib.sha256(password.encode("utf-8")).hexdigest()

    def register_audit(self, *, user_id: int | None, action: str, payload: dict[str, Any] | None = None) -> None:
        """Persist a simple audit trail for critical actions."""
        try:
            with self.connect() as conn:
                conn.execute(
                    "INSERT INTO audit_logs (user_id, action, payload, timestamp) VALUES (?, ?, ?, ?)",
                    (
                        user_id,
                        action,
                        json.dumps(payload or {}),
                        datetime.utcnow().isoformat(),
                    ),
                )
        except Exception:  # noqa: BLE001
            logger.exception("Unable to write audit entry for %s", action)

    # ------------------------------------------------------------------
    # Backup logs
    def register_backup(
        self,
        *,
        filename: str,
        sha256: str,
        size_bytes: int,
        storage_local: bool = True,
        storage_nas: bool = False,
        storage_cloud: bool = False,
        notes: str | None = None,
    ) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO backup_logs (filename, sha256, size_bytes, storage_local, storage_nas, storage_cloud, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    filename,
                    sha256,
                    size_bytes,
                    int(storage_local),
                    int(storage_nas),
                    int(storage_cloud),
                    notes,
                ),
            )
            return cur.lastrowid

    def list_backups(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            cur = conn.execute("SELECT * FROM backup_logs ORDER BY created_at DESC")
            return cur.fetchall()

    def get_backup_info(self, backup_id: int) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            cur = conn.execute("SELECT * FROM backup_logs WHERE id = ?", (backup_id,))
            return cur.fetchone()

    def delete_backup(self, backup_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM backup_logs WHERE id = ?", (backup_id,))

    def _get_active_branch_id(self, conn: sqlite3.Connection) -> int:
        cur = conn.execute("SELECT value FROM app_config WHERE key = 'active_branch_id'")
        row = cur.fetchone()
        return int(row["value"]) if row else 1

    def _ensure_common_product(self, conn: sqlite3.Connection) -> int:
        cur = conn.execute("SELECT id FROM products WHERE sku = 'COMMON'")
        row = cur.fetchone()
        if row:
            return int(row["id"])
        conn.execute(
            "INSERT INTO products (sku, name, price, allow_decimal, unit) VALUES (?, ?, ?, 1, 'Servicio')",
            ("COMMON", "Producto Común", 0.0),
        )
        cur = conn.execute("SELECT id FROM products WHERE sku = 'COMMON'")
        row = cur.fetchone()
        return int(row["id"])

    def get_tax_rate(self, branch_id: Optional[int] = None) -> float:
        cfg = self.read_config()
        try:
            return float(cfg.get("tax_rate", 0.16))
        except (TypeError, ValueError):
            return 0.16

    # ------------------------------------------------------------------
    # Authentication
    def authenticate_user(self, username: str, password: str) -> Optional[sqlite3.Row]:
        """Validate credentials and return the user row when valid."""
        with self.connect() as conn:
            cur = conn.execute(
                "SELECT * FROM users WHERE username = ? AND is_active = 1", (username,)
            )
            row = cur.fetchone()
            if row and row["password_hash"] == self._hash_password(password):
                logger.info("User %s authenticated", username)
                self.register_audit(user_id=row["id"], action="login_success", payload={"username": username})
                return row
            logger.warning("Invalid login attempt for %s", username)
            self.register_audit(user_id=None, action="login_failed", payload={"username": username})
            return None

    def get_user(self, user_id: int) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            cur = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            return cur.fetchone()

    def get_user_by_username(self, username: str) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            cur = conn.execute("SELECT * FROM users WHERE username = ?", (username,))
            return cur.fetchone()

    def list_users(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            cur = conn.execute("SELECT * FROM users ORDER BY id")
            return cur.fetchall()

    def update_user_role(self, user_id: int, role: str) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
            logger.info("Updated role for user %s to %s", user_id, role)

    def set_user_active(self, user_id: int, active: bool) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE users SET is_active = ? WHERE id = ?", (int(active), user_id))
            logger.info("User %s active=%s", user_id, active)

    def get_user_roles(self, user_id: int) -> list[str]:
        user = self.get_user(user_id)
        if not user:
            return []
        return [str(user["role"])]

    def create_api_token(self, user_id: int, role: str, description: str | None = None) -> str:
        import secrets

        token = secrets.token_urlsafe(32)
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO api_tokens (user_id, token, role, description) VALUES (?, ?, ?, ?)",                (user_id, token, role, description),
            )
        logger.info("Created API token for user %s with role %s", user_id, role)
        return token

    # ------------------------------------------------------------------
    # Branch helpers
    def list_branches(self) -> List[sqlite3.Row]:
        with self.connect() as conn:
            cur = conn.execute("SELECT * FROM branches ORDER BY id")
            return cur.fetchall()

    def get_branch(self, branch_id: int) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            cur = conn.execute("SELECT * FROM branches WHERE id = ?", (branch_id,))
            return cur.fetchone()

    def set_active_branch(self, branch_id: int) -> None:
        with self.connect() as conn:
            exists = conn.execute("SELECT 1 FROM branches WHERE id = ?", (branch_id,)).fetchone()
            if not exists:
                raise ValueError(f"Branch {branch_id} does not exist")
            conn.execute(
                "INSERT OR REPLACE INTO app_config (key, value) VALUES ('active_branch_id', ?)",
                (str(branch_id),),
            )
            logger.info("Active branch set to %s", branch_id)

    # ------------------------------------------------------------------
    # Product helpers
    def upsert_product(
        self,
        *,
        sku: str,
        name: str,
        price: float,
        price_wholesale: float = 0.0,
        cost: float = 0.0,
        unit: str = "Unidad",
        allow_decimal: bool = False,
        barcode: Optional[str] = None,
        description: Optional[str] = None,
        is_kit: bool = False,
    ) -> int:
        """Insert or update a product by SKU and return its ID."""
        with self.connect() as conn:
            cur = conn.execute("SELECT id FROM products WHERE sku = ?", (sku,))
            row = cur.fetchone()
            if row:
                conn.execute(
                    """
                    UPDATE products
                    SET name = ?, price = ?, price_wholesale = ?, cost = ?, unit = ?, allow_decimal = ?, barcode = ?,
                        description = ?, is_kit = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE sku = ?
                    """,
                    (
                        name,
                        price,
                        price_wholesale,
                        cost,
                        unit,
                        int(allow_decimal),
                        barcode,
                        description,
                        int(is_kit),
                        sku,
                    ),
                )
                product_id = row["id"]
                logger.info("Updated product %s (%s)", sku, name)
            else:
                cur = conn.execute(
                    """
                    INSERT INTO products
                    (sku, barcode, name, description, price, price_wholesale, cost, unit, allow_decimal, is_kit)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sku,
                        barcode,
                        name,
                        description,
                        price,
                        price_wholesale,
                        cost,
                        unit,
                        int(allow_decimal),
                        int(is_kit),
                    ),
                )
                product_id = cur.lastrowid
                logger.info("Inserted product %s (%s)", sku, name)
            branch_id = self._get_active_branch_id(conn)
            conn.execute(
                "INSERT OR IGNORE INTO product_stocks (product_id, branch_id) VALUES (?, ?)",
                (product_id, branch_id),
            )
            return product_id

    def get_product_by_sku_or_barcode(self, identifier: str) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            cur = conn.execute(
                "SELECT * FROM products WHERE sku = ? OR barcode = ?",
                (identifier, identifier),
            )
            return cur.fetchone()

    def get_product_by_id(self, product_id: int) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            cur = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,))
            return cur.fetchone()

    def search_products(
        self,
        term: str,
        category: Optional[str] = None,
        *,
        limit: int = 20,
        branch_id: Optional[int] = None,
    ) -> List[sqlite3.Row]:
        pattern = f"%{term.strip()}%"
        with self.connect() as conn:
            branch = branch_id or self._get_active_branch_id(conn)
            sql = (
                """
                SELECT p.*, ps.stock, ps.reserved
                FROM products p
                LEFT JOIN product_stocks ps ON p.id = ps.product_id AND ps.branch_id = ?
                WHERE (p.name LIKE ? OR p.sku LIKE ? OR p.barcode LIKE ?)
                """
            )
            params: list[Any] = [branch, pattern, pattern, pattern]
            if category:
                sql += " AND p.category = ?"
                params.append(category)
            sql += " ORDER BY p.name ASC LIMIT ?"
            params.append(limit)
            cur = conn.execute(sql, params)
            return cur.fetchall()

    # ------------------------------------------------------------------
    # Product CRUD (PRO)
    def create_product(self, data: dict[str, Any]) -> int:
        sku = (data.get("sku") or "").strip()
        if not sku:
            raise ValueError("El SKU es obligatorio")
        name = (data.get("name") or data.get("description") or "").strip()
        if not name:
            raise ValueError("El nombre es obligatorio")

        sale_type = (data.get("sale_type") or "unit").lower()
        allow_decimal = bool(data.get("allow_decimal", sale_type == "weight"))
        is_kit = sale_type == "kit" or bool(data.get("is_kit"))
        uses_inventory = int(data.get("uses_inventory", 1))

        payload = (
            sku,
            (data.get("barcode") or "").strip() or None,
            name,
            (data.get("description") or "").strip() or None,
            float(data.get("price") or 0),
            float(data.get("price_wholesale") or 0),
            float(data.get("cost") or 0),
            (data.get("unit") or "Unidad"),
            int(allow_decimal),
            int(is_kit),
            (data.get("department") or "").strip() or None,
            (data.get("provider") or "").strip() or None,
            int(data.get("is_active", 1)),
            int(data.get("is_favorite", 0)),
            sale_type,
            json.dumps(data.get("kit_items") or []),
            uses_inventory,
        )

        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO products (
                    sku, barcode, name, description, price, price_wholesale, cost, unit, allow_decimal, is_kit,
                    department, provider, is_active, is_favorite, sale_type, kit_items, uses_inventory
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                payload,
            )
            product_id = cur.lastrowid
            branch_id = self._get_active_branch_id(conn)
            conn.execute(
                "INSERT OR IGNORE INTO product_stocks (product_id, branch_id, stock, min_stock, max_stock) VALUES (?, ?, ?, ?, ?)",
                (
                    product_id,
                    branch_id,
                    float(data.get("stock", 0) or 0),
                    float(data.get("min_stock", 0) or 0),
                    float(data.get("max_stock", 0) or 0),
                ),
            )
            self._notify_product_event("product_created", product_id)
            return product_id

    def update_product(self, product_id: int, data: dict[str, Any]) -> None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
            if not row:
                raise ValueError("Producto no encontrado")

            sale_type = (data.get("sale_type") or row["sale_type"] or "unit").lower()
            allow_decimal = bool(data.get("allow_decimal", sale_type == "weight" or row["allow_decimal"]))
            is_kit = sale_type == "kit" or bool(data.get("is_kit") or row["is_kit"])
            uses_inventory = int(data.get("uses_inventory", row["uses_inventory"]))

            fields = [
                ("sku", (data.get("sku") or row["sku"]).strip()),
                ("barcode", (data.get("barcode") or row["barcode"] or "").strip() or None),
                ("name", (data.get("name") or data.get("description") or row["name"]).strip()),
                ("description", (data.get("description") or row["description"] or "").strip() or None),
                ("price", float(data.get("price") if data.get("price") is not None else row["price"])),
                ("price_wholesale", float(data.get("price_wholesale") if data.get("price_wholesale") is not None else row["price_wholesale"])),
                ("cost", float(data.get("cost") if data.get("cost") is not None else row["cost"])),
                ("unit", (data.get("unit") or row["unit"])),
                ("allow_decimal", int(allow_decimal)),
                ("is_kit", int(is_kit)),
                ("department", (data.get("department") or row["department"] or "").strip() or None),
                ("provider", (data.get("provider") or row["provider"] or "").strip() or None),
                ("is_active", int(data.get("is_active", row["is_active"]))),
                ("is_favorite", int(data.get("is_favorite", row["is_favorite"]))),
                ("sale_type", sale_type),
                (
                    "kit_items",
                    json.dumps(
                        data.get("kit_items")
                        or json.loads(row["kit_items"] or "[]")
                        if isinstance(row["kit_items"], str)
                        else row["kit_items"]
                        or []
                    ),
                ),
                ("uses_inventory", uses_inventory),
            ]

            set_clause = ", ".join(f"{col} = ?" for col, _ in fields)
            values = [val for _, val in fields]
            values.append(product_id)
            conn.execute(f"UPDATE products SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?", values)

            branch_id = self._get_active_branch_id(conn)
            if uses_inventory:
                conn.execute(
                    "INSERT OR IGNORE INTO product_stocks (product_id, branch_id) VALUES (?, ?)",
                    (product_id, branch_id),
                )
                stock_fields = []
                stock_values: list[Any] = []
                for column, key in (("stock", "stock"), ("min_stock", "min_stock"), ("max_stock", "max_stock")):
                    if key in data:
                        stock_fields.append(f"{column} = ?")
                        stock_values.append(float(data.get(key) or 0))
                if stock_fields:
                    stock_values.extend([product_id, branch_id])
                    conn.execute(
                        f"UPDATE product_stocks SET {', '.join(stock_fields)}, updated_at = CURRENT_TIMESTAMP WHERE product_id = ? AND branch_id = ?",
                        stock_values,
                    )
            self._notify_product_event("product_updated", product_id)

    def delete_product(self, product_id: int) -> None:
        if self.get_product_sales_count(product_id) > 0:
            raise ValueError("El producto tiene ventas asociadas; desactívalo en lugar de borrarlo")
        with self.connect() as conn:
            conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
            self._notify_product_event("product_deleted", product_id)

    def deactivate_product(self, product_id: int) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE products SET is_active = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (product_id,),
            )
            self._notify_product_event("product_deleted", product_id)

    def toggle_favorite(self, product_id: int) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE products SET is_favorite = CASE WHEN is_favorite = 1 THEN 0 ELSE 1 END WHERE id = ?",
                (product_id,),
            )
            self._notify_product_event("favorite_changed", product_id)

    def get_product(self, product_id: int) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            cur = conn.execute(
                "SELECT p.*, ps.stock, ps.min_stock, ps.max_stock, ps.reserved FROM products p "
                "LEFT JOIN product_stocks ps ON p.id = ps.product_id AND ps.branch_id = ? WHERE p.id = ?",
                (self._get_active_branch_id(conn), product_id),
            )
            return cur.fetchone()

    def get_product_by_sku(self, sku: str) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            cur = conn.execute("SELECT * FROM products WHERE sku = ?", (sku.strip(),))
            return cur.fetchone()

    def get_kit_items(self, product_id: int) -> list[dict[str, Any]]:
        """Return parsed kit components for a product."""
        with self.connect() as conn:
            row = conn.execute("SELECT kit_items FROM products WHERE id = ?", (product_id,)).fetchone()
            if not row:
                return []
            raw = row["kit_items"] if isinstance(row, dict) else row[0]
            try:
                parsed = json.loads(raw) if isinstance(raw, str) else raw
            except Exception:
                return []
            if not isinstance(parsed, list):
                return []
            return [comp for comp in parsed if comp]

    def get_products_for_search(self, query: str, *, limit: int = 50, branch_id: Optional[int] = None) -> list[sqlite3.Row]:
        term = (query or "").strip()
        exact = term.startswith("@")
        active_branch: Optional[int] = None
        with self.connect() as conn:
            active_branch = branch_id or self._get_active_branch_id(conn)
            sql = [
                "SELECT p.*, ps.stock, ps.reserved FROM products p ",
                "LEFT JOIN product_stocks ps ON p.id = ps.product_id AND ps.branch_id = ? ",
                "WHERE p.is_active = 1 ",
            ]
            params: list[Any] = [active_branch]

            if exact:
                term = term[1:].strip()
                sql.append("AND (p.sku = ? OR p.name = ?)")
                params.extend([term, term])
            elif term.isdigit():
                sql.append("AND (p.sku = ? OR p.barcode = ? OR p.name LIKE ?)")
                like = f"%{term}%"
                params.extend([term, term, like])
            else:
                like = f"%{term}%"
                sql.append("AND (p.name LIKE ? OR p.sku LIKE ? OR p.barcode LIKE ?)")
                params.extend([like, like, like])

            sql.append(" ORDER BY p.is_favorite DESC, p.name COLLATE NOCASE ASC LIMIT ?")
            params.append(limit)
            cur = conn.execute("".join(sql), params)
            return cur.fetchall()

    def list_products_for_export(self, branch_id: Optional[int] = None) -> list[dict[str, Any]]:
        with self.connect() as conn:
            branch = branch_id or self._get_active_branch_id(conn)
            cur = conn.execute(
                """
                SELECT p.*, ps.stock, ps.min_stock, ps.max_stock, ps.reserved
                FROM products p
                LEFT JOIN product_stocks ps ON p.id = ps.product_id AND ps.branch_id = ?
                WHERE p.is_active = 1
                ORDER BY p.name COLLATE NOCASE ASC
                """,
                (branch,),
            )
            return [dict(row) for row in cur.fetchall()]

    def get_product_sales_count(self, product_id: int) -> int:
        with self.connect() as conn:
            cur = conn.execute("SELECT COUNT(1) FROM sale_items WHERE product_id = ?", (product_id,))
            return int(cur.fetchone()[0])

    def update_stock(self, product_id: int, delta: float, branch_id: Optional[int] = None) -> None:
        with self.connect() as conn:
            branch = branch_id or self._get_active_branch_id(conn)
            conn.execute(
                "INSERT OR IGNORE INTO product_stocks (product_id, branch_id) VALUES (?, ?)",
                (product_id, branch),
            )
            conn.execute(
                """
                UPDATE product_stocks
                SET stock = stock + ?, updated_at = CURRENT_TIMESTAMP
                WHERE product_id = ? AND branch_id = ?
                """,
                (delta, product_id, branch),
            )

    def set_stock(self, product_id: int, new_value: float, branch_id: Optional[int] = None) -> None:
        with self.connect() as conn:
            branch = branch_id or self._get_active_branch_id(conn)
            conn.execute(
                "INSERT OR IGNORE INTO product_stocks (product_id, branch_id) VALUES (?, ?)",
                (product_id, branch),
            )
            conn.execute(
                "UPDATE product_stocks SET stock = ?, updated_at = CURRENT_TIMESTAMP WHERE product_id = ? AND branch_id = ?",
                (float(new_value), product_id, branch),
            )

    def get_inventory_movements(
        self, product_id: int, *, date_from: Optional[str] = None, date_to: Optional[str] = None, branch_id: Optional[int] = None
    ) -> list[sqlite3.Row]:
        with self.connect() as conn:
            branch = branch_id or self._get_active_branch_id(conn)
            sql = ["SELECT * FROM inventory_logs WHERE product_id = ? AND branch_id = ?"]
            params: list[Any] = [product_id, branch]
            if date_from:
                sql.append(" AND created_at >= ?")
                params.append(date_from)
            if date_to:
                sql.append(" AND created_at <= ?")
                params.append(date_to)
            sql.append(" ORDER BY created_at DESC LIMIT 200")
            cur = conn.execute("".join(sql), params)
            return cur.fetchall()

    def _notify_product_event(self, event: str, product_id: int) -> None:
        """Best-effort hook for MultiCaja/websocket sync without hard dependency."""

        payload = {"event": event, "product_id": product_id}
        callback = getattr(self, "on_product_event", None)
        if callable(callback):
            try:
                callback(payload)
            except Exception:  # pragma: no cover - non-critical
                logger.exception("Error notifying product event")

    # ------------------------------------------------------------------
    # Customer helpers
    def create_customer(self, data: dict[str, Any]) -> int:
        first = (data.get("first_name") or "").strip()
        if not first:
            raise ValueError("El nombre es requerido")
        credit_limit_raw = data.get("credit_limit")
        credit_limit = float(credit_limit_raw) if credit_limit_raw not in (None, "") else 0.0
        credit_balance_raw = data.get("credit_balance")
        credit_balance = float(credit_balance_raw) if credit_balance_raw is not None else 0.0
        credit_authorized = bool(data.get("credit_authorized", credit_limit != 0))
        if not credit_authorized:
            credit_balance = 0.0
        payload = (
            first,
            (data.get("last_name") or "").strip(),
            (data.get("phone") or "").strip(),
            (data.get("email") or "").strip(),
            (data.get("email_fiscal") or "").strip(),
            credit_limit,
            credit_balance,
            int(credit_authorized),
            (data.get("notes") or "").strip() or None,
            int(data.get("is_active", 1)),
            int(data.get("vip", False)),
            datetime.utcnow().isoformat(),
            (data.get("rfc") or "").strip(),
            (data.get("razon_social") or "").strip(),
            (data.get("domicilio1") or "").strip(),
            (data.get("domicilio2") or "").strip(),
            (data.get("colonia") or "").strip(),
            (data.get("municipio") or "").strip(),
            (data.get("estado") or "").strip(),
            (data.get("pais") or "").strip(),
            (data.get("codigo_postal") or "").strip(),
            (data.get("regimen_fiscal") or "").strip(),
        )
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO customers (
                    first_name, last_name, phone, email, email_fiscal, credit_limit, credit_balance, credit_authorized,
                    notes, is_active, vip, created_at,
                    rfc, razon_social, domicilio1, domicilio2, colonia, municipio, estado, pais, codigo_postal, regimen_fiscal
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                payload,
            )
            logger.info("Created customer %s", first)
            return cur.lastrowid

    def update_customer(self, customer_id: int, data: dict[str, Any]) -> None:
        first = (data.get("first_name") or "").strip()
        if not first:
            raise ValueError("El nombre es requerido")
        with self.connect() as conn:
            current_row = conn.execute("SELECT credit_balance FROM customers WHERE id = ?", (customer_id,)).fetchone()
            current_balance = float(current_row["credit_balance"]) if current_row else 0.0
            credit_limit_raw = data.get("credit_limit")
            credit_limit = float(credit_limit_raw) if credit_limit_raw not in (None, "") else 0.0
            credit_authorized = bool(data.get("credit_authorized", credit_limit != 0))
            if not credit_authorized:
                current_balance = 0.0
            fields = [
                ("first_name", first),
                ("last_name", (data.get("last_name") or "").strip()),
                ("phone", (data.get("phone") or "").strip()),
                ("email", (data.get("email") or "").strip()),
                ("email_fiscal", (data.get("email_fiscal") or "").strip()),
                ("credit_limit", credit_limit),
                ("credit_balance", float(data.get("credit_balance") if data.get("credit_balance") is not None else current_balance)),
                ("credit_authorized", int(credit_authorized)),
                ("notes", (data.get("notes") or "").strip() or None),
                ("is_active", int(data.get("is_active", 1))),
                ("vip", int(data.get("vip", False))),
                ("rfc", (data.get("rfc") or "").strip()),
                ("razon_social", (data.get("razon_social") or "").strip()),
                ("domicilio1", (data.get("domicilio1") or "").strip()),
                ("domicilio2", (data.get("domicilio2") or "").strip()),
                ("colonia", (data.get("colonia") or "").strip()),
                ("municipio", (data.get("municipio") or "").strip()),
                ("estado", (data.get("estado") or "").strip()),
                ("pais", (data.get("pais") or "").strip()),
                ("codigo_postal", (data.get("codigo_postal") or "").strip()),
                ("regimen_fiscal", (data.get("regimen_fiscal") or "").strip()),
            ]
            set_clause = ", ".join(f"{col} = ?" for col, _ in fields)
            values = [val for _, val in fields]
            values.append(customer_id)
            conn.execute(f"UPDATE customers SET {set_clause} WHERE id = ?", values)
            logger.info("Updated customer %s", customer_id)

    def delete_customer(self, customer_id: int) -> None:
        with self.connect() as conn:
            row = conn.execute("SELECT credit_balance FROM customers WHERE id = ?", (customer_id,)).fetchone()
            if row and float(row["credit_balance"] or 0.0) > 0:
                raise ValueError("No se puede eliminar un cliente con saldo pendiente")
            conn.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
            logger.info("Deleted customer %s", customer_id)

    def get_customer(self, customer_id: int) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            cur = conn.execute(
                "SELECT *, TRIM(COALESCE(first_name,'') || ' ' || COALESCE(last_name,'')) AS full_name FROM customers WHERE id = ?",
                (customer_id,),
            )
            return cur.fetchone()

    def search_customers(self, query: str, limit: int = 50) -> List[sqlite3.Row]:
        term = f"%{query.strip()}%"
        with self.connect() as conn:
            cur = conn.execute(
                """
                SELECT *, TRIM(COALESCE(first_name,'') || ' ' || COALESCE(last_name,'')) AS full_name
                FROM customers
                WHERE first_name LIKE ? OR last_name LIKE ? OR phone LIKE ? OR email LIKE ? OR rfc LIKE ?
                ORDER BY full_name ASC
                LIMIT ?
                """,
                (term, term, term, term, term, limit),
            )
            return cur.fetchall()

    def list_customers(self, limit: int = 200) -> List[sqlite3.Row]:
        with self.connect() as conn:
            cur = conn.execute(
                "SELECT *, TRIM(COALESCE(first_name,'') || ' ' || COALESCE(last_name,'')) AS full_name FROM customers ORDER BY full_name ASC LIMIT ?",
                (limit,),
            )
            return cur.fetchall()

    def list_all_customers_with_credit_meta(self) -> list[dict[str, Any]]:
        """Return customers with fiscal and credit metadata for exports."""

        with self.connect() as conn:
            cur = conn.execute(
                """
                SELECT
                    c.*,
                    TRIM(COALESCE(c.first_name,'') || ' ' || COALESCE(c.last_name,'')) AS full_name,
                    (
                        SELECT MAX(timestamp) FROM credit_payments cp WHERE cp.customer_id = c.id
                    ) AS last_payment_ts,
                    (
                        SELECT amount FROM credit_payments cp WHERE cp.customer_id = c.id ORDER BY timestamp DESC LIMIT 1
                    ) AS last_payment_amount
                FROM customers c
                ORDER BY full_name COLLATE NOCASE ASC
                """
            )
            return [dict(row) for row in cur.fetchall()]

    def update_customer_credit(self, customer_id: int, new_balance: float) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE customers SET credit_balance = ? WHERE id = ?",
                (float(new_balance), customer_id),
            )
            logger.info("Updated credit balance for customer %s to %.2f", customer_id, new_balance)

    def modify_customer_credit(self, customer_id: int, *, limit_delta: float = 0.0, balance_delta: float = 0.0) -> None:
        """Adjust credit limit and/or balance by the provided deltas."""

        with self.connect() as conn:
            if limit_delta:
                conn.execute("UPDATE customers SET credit_limit = credit_limit + ? WHERE id = ?", (limit_delta, customer_id))
            if balance_delta:
                conn.execute(
                    "UPDATE customers SET credit_balance = MAX(credit_balance + ?, 0) WHERE id = ?",
                    (balance_delta, customer_id),
                )
            logger.info(
                "Modified credit for customer %s (limit Δ %.2f, balance Δ %.2f)",
                customer_id,
                limit_delta,
                balance_delta,
            )

    def reduce_credit_balance(self, customer_id: int, amount: float) -> None:
        if amount <= 0:
            return
        with self.connect() as conn:
            conn.execute(
                "UPDATE customers SET credit_balance = MAX(credit_balance - ?, 0) WHERE id = ?",
                (float(amount), customer_id),
            )
            logger.info("Reduced credit balance for customer %s by %.2f", customer_id, amount)

    def get_customer_sales_history(self, customer_id: int, limit: int = 100) -> list[sqlite3.Row]:
        with self.connect() as conn:
            cur = conn.execute(
                """
                SELECT id, ts, total, payment_method
                FROM sales
                WHERE customer_id = ?
                ORDER BY ts DESC
                LIMIT ?
                """,
                (customer_id, limit),
            )
            return cur.fetchall()

    def get_credit_balance(self, customer_id: int) -> float:
        with self.connect() as conn:
            row = conn.execute("SELECT credit_balance FROM customers WHERE id = ?", (customer_id,)).fetchone()
            return float(row["credit_balance"]) if row else 0.0

    def get_customer_credit_info(self, customer_id: int) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT credit_limit, credit_balance, credit_authorized FROM customers WHERE id = ?",
                (customer_id,),
            ).fetchone()
            if not row:
                return {"credit_limit": 0.0, "credit_balance": 0.0, "credit_authorized": False}
            return {
                "credit_limit": float(row["credit_limit"] or 0.0),
                "credit_balance": float(row["credit_balance"] or 0.0),
                "credit_authorized": bool(row["credit_authorized"]),
            }

    def record_credit_payment(
        self,
        customer_id: int,
        amount: float,
        notes: str | None = None,
        user_id: int | None = None,
        sale_ids: Sequence[int] | None = None,
    ) -> int:
        amount = float(amount)
        if amount <= 0:
            raise ValueError("El abono debe ser mayor a cero")
        sale_ids_text = json.dumps(list(sale_ids)) if sale_ids is not None else None
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO credit_payments (customer_id, amount, timestamp, notes, user_id, sale_ids)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    customer_id,
                    amount,
                    datetime.utcnow().isoformat(),
                    notes,
                    user_id,
                    sale_ids_text,
                ),
            )
            logger.info("Recorded credit payment for customer %s amount %.2f", customer_id, amount)
            self.register_audit(
                user_id=user_id,
                action="credit_payment",
                payload={"customer_id": customer_id, "amount": amount, "sale_ids": sale_ids},
            )
            return cur.lastrowid

    def get_credit_payments(self, customer_id: int) -> list[sqlite3.Row]:
        with self.connect() as conn:
            cur = conn.execute(
                "SELECT * FROM credit_payments WHERE customer_id = ? ORDER BY timestamp DESC",
                (customer_id,),
            )
            return cur.fetchall()

    def register_credit_payment(
        self,
        customer_id: int,
        amount: float,
        notes: str | None = None,
        user_id: int | None = None,
        sale_ids: Sequence[int] | None = None,
    ) -> int:
        """Register an abono and decrease the customer's credit balance."""

        payment_id = self.record_credit_payment(customer_id, amount, notes, user_id, sale_ids)
        self.reduce_credit_balance(customer_id, amount)
        return payment_id

    def get_previous_credit_balance(self, customer_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM previous_credit_balances WHERE customer_id = ? ORDER BY created_at DESC LIMIT 1",
                (customer_id,),
            ).fetchone()
            return dict(row) if row else None

    def set_previous_credit_balance(self, customer_id: int, balance: float, description: str = "") -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO previous_credit_balances (customer_id, balance, description, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (customer_id, float(balance), description, datetime.utcnow().isoformat()),
            )
            logger.info("Registered previous credit balance for customer %s", customer_id)
            return cur.lastrowid

    def get_customer_full_profile(self, customer_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT *, TRIM(COALESCE(first_name,'') || ' ' || COALESCE(last_name,'')) AS full_name
                FROM customers WHERE id = ?
                """,
                (customer_id,),
            ).fetchone()
            return dict(row) if row else None

    def get_customer_credit_movements(
        self,
        customer_id: int,
        *,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return chronological credit-impacting movements (ventas fiadas y abonos)."""

        movements: list[dict[str, Any]] = []
        with self.connect() as conn:
            params: list[Any] = [customer_id]
            date_clause = ""
            if date_from:
                date_clause += " AND ts >= ?"
                params.append(date_from)
            if date_to:
                date_clause += " AND ts <= ?"
                params.append(date_to)
            sales = conn.execute(
                f"SELECT id, ts, total, payment_method, payment_breakdown FROM sales WHERE customer_id = ?{date_clause}", params
            ).fetchall()
            for sale in sales:
                credit_amount = 0.0
                if sale["payment_method"] == "credit":
                    credit_amount = float(sale["total"] or 0.0)
                elif sale["payment_method"] == "mixed":
                    try:
                        breakdown = json.loads(sale["payment_breakdown"] or "{}")
                        credit_amount = float(breakdown.get("credit", 0.0) or 0.0)
                    except Exception:
                        credit_amount = 0.0
                if credit_amount > 0:
                    movements.append(
                        {
                            "date": sale["ts"],
                            "type": "sale",
                            "description": f"Venta #{sale['id']}",
                            "debit": credit_amount,
                            "credit": 0.0,
                            "sale_id": int(sale["id"]),
                            "payment_id": None,
                        }
                    )

            pay_params: list[Any] = [customer_id]
            pay_clause = ""
            if date_from:
                pay_clause += " AND timestamp >= ?"
                pay_params.append(date_from)
            if date_to:
                pay_clause += " AND timestamp <= ?"
                pay_params.append(date_to)
            payments = conn.execute(
                f"SELECT * FROM credit_payments WHERE customer_id = ?{pay_clause} ORDER BY timestamp ASC", pay_params
            ).fetchall()
            for pmt in payments:
                movements.append(
                    {
                        "date": pmt["timestamp"],
                        "type": "payment",
                        "description": pmt.get("notes") or "Abono",
                        "debit": 0.0,
                        "credit": float(pmt.get("amount", 0.0) or 0.0),
                        "sale_id": None,
                        "payment_id": int(pmt["id"]),
                    }
                )

        movements.sort(key=lambda m: m["date"])
        return movements

    def get_credit_statement(
        self,
        customer_id: int,
        *,
        date_from: str | None = None,
        date_to: str | None = None,
        include_previous: bool = True,
    ) -> dict[str, Any]:
        profile = self.get_customer_full_profile(customer_id)
        previous = self.get_previous_credit_balance(customer_id) if include_previous else None
        movements = self.get_customer_credit_movements(customer_id, date_from=date_from, date_to=date_to)
        running = float(previous.get("balance", 0.0) if previous else 0.0)
        enriched: list[dict[str, Any]] = []
        if previous:
            enriched.append(
                {
                    "date": previous.get("created_at"),
                    "type": "previous",
                    "description": previous.get("description") or "Saldo consolidado anterior",
                    "debit": running,
                    "credit": 0.0,
                    "balance_after": running,
                    "sale_id": None,
                    "payment_id": None,
                }
            )

        total_sales = 0.0
        total_payments = 0.0
        for mv in movements:
            running += float(mv.get("debit", 0.0)) - float(mv.get("credit", 0.0))
            mv["balance_after"] = running
            total_sales += float(mv.get("debit", 0.0))
            total_payments += float(mv.get("credit", 0.0))
            enriched.append(mv)

        return {
            "customer": profile,
            "previous_balance": float(previous.get("balance", 0.0) if previous else 0.0),
            "current_balance": self.get_credit_balance(customer_id),
            "movements": enriched,
            "total_sales": total_sales,
            "total_payments": total_payments,
        }

    def get_credit_summary(self, customer_id: int) -> dict[str, Any]:
        """Return credit overview including sales and payments."""

        credit_info = self.get_customer_credit_info(customer_id)
        balance = float(credit_info.get("credit_balance", 0.0))
        payments = [dict(row) for row in self.get_credit_payments(customer_id)]
        sales = [dict(row) for row in self.get_customer_sales_history(customer_id, limit=200)]
        total_payments = sum(float(p.get("amount", 0.0) or 0.0) for p in payments)
        return {
            "credit_limit": float(credit_info.get("credit_limit", 0.0) or 0.0),
            "credit_balance": balance,
            "payments": payments,
            "sales": sales,
            "total_payments": total_payments,
        }

    def list_credit_accounts(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            cur = conn.execute(
                """
                SELECT id, TRIM(COALESCE(first_name,'') || ' ' || COALESCE(last_name,'')) AS full_name,
                       credit_limit, credit_balance
                FROM customers
                WHERE credit_balance > 0
                ORDER BY full_name ASC
                """
            )
            return cur.fetchall()

    def list_all_credit_payments(self, limit: int = 200) -> list[sqlite3.Row]:
        """Return recent credit payments across customers for reporting."""

        with self.connect() as conn:
            cur = conn.execute(
                """
                SELECT cp.*, c.first_name, c.last_name
                FROM credit_payments cp
                LEFT JOIN customers c ON c.id = cp.customer_id
                ORDER BY cp.timestamp DESC
                LIMIT ?
                """,
                (limit,),
            )
            return cur.fetchall()

    # ------------------------------------------------------------------
    # Stock helpers
    def get_stock_info(self, product_id: int, branch_id: Optional[int] = None) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            branch = branch_id or self._get_active_branch_id(conn)
            cur = conn.execute(
                """
                SELECT ps.*, p.name, p.sku
                FROM product_stocks ps
                JOIN products p ON p.id = ps.product_id
                WHERE ps.product_id = ? AND ps.branch_id = ?
                """,
                (product_id, branch),
            )
            return cur.fetchone()

    def list_product_stocks(self, branch_id: Optional[int] = None) -> List[sqlite3.Row]:
        with self.connect() as conn:
            branch = branch_id or self._get_active_branch_id(conn)
            cur = conn.execute(
                """
                SELECT ps.product_id, ps.stock, p.sku, p.name, p.description as category
                FROM product_stocks ps
                JOIN products p ON p.id = ps.product_id
                WHERE ps.branch_id = ?
                ORDER BY p.name ASC
                """,
                (branch,),
            )
            return cur.fetchall()

    def add_stock(
        self,
        product_id: int,
        quantity: float,
        *,
        branch_id: Optional[int] = None,
        reason: str | None = None,
        ref_type: str | None = None,
        ref_id: int | None = None,
        ) -> None:
        """Adjust stock and log the movement."""
        with self.connect() as conn:
            branch = branch_id or self._get_active_branch_id(conn)
            conn.execute(
                "INSERT OR IGNORE INTO product_stocks (product_id, branch_id) VALUES (?, ?)",
                (product_id, branch),
            )
            conn.execute(
                "UPDATE product_stocks SET stock = stock + ?, updated_at = CURRENT_TIMESTAMP WHERE product_id = ? AND branch_id = ?",
                (quantity, product_id, branch),
            )
            self._log_inventory(conn, product_id, branch, quantity, reason, ref_type, ref_id)
            logger.info("Adjusted stock for product %s by %s in branch %s", product_id, quantity, branch)

    def reserve_stock(self, product_id: int, qty: float, branch_id: Optional[int] = None) -> None:
        with self.connect() as conn:
            branch = branch_id or self._get_active_branch_id(conn)
            conn.execute(
                "INSERT OR IGNORE INTO product_stocks (product_id, branch_id) VALUES (?, ?)",
                (product_id, branch),
            )
            conn.execute(
                "UPDATE product_stocks SET reserved = reserved + ?, updated_at = CURRENT_TIMESTAMP WHERE product_id = ? AND branch_id = ?",
                (qty, product_id, branch),
            )
            self._log_inventory(conn, product_id, branch, -qty, "layaway reserve", "layaway", None)

    def release_reserved_stock(self, product_id: int, qty: float, branch_id: Optional[int] = None) -> None:
        with self.connect() as conn:
            branch = branch_id or self._get_active_branch_id(conn)
            conn.execute(
                "UPDATE product_stocks SET reserved = MAX(reserved - ?, 0), updated_at = CURRENT_TIMESTAMP WHERE product_id = ? AND branch_id = ?",
                (qty, product_id, branch),
            )
            self._log_inventory(conn, product_id, branch, qty, "layaway release", "layaway", None)

    def consume_reserved_stock(self, product_id: int, qty: float, branch_id: Optional[int] = None) -> None:
        with self.connect() as conn:
            branch = branch_id or self._get_active_branch_id(conn)
            conn.execute(
                "UPDATE product_stocks SET reserved = MAX(reserved - ?, 0), stock = stock - ?, updated_at = CURRENT_TIMESTAMP WHERE product_id = ? AND branch_id = ?",
                (qty, qty, product_id, branch),
            )
            self._log_inventory(conn, product_id, branch, -qty, "layaway consume", "layaway", None)

    def _log_inventory(
        self,
        conn: sqlite3.Connection,
        product_id: int,
        branch_id: int,
        delta: float,
        reason: Optional[str],
        ref_type: Optional[str],
        ref_id: Optional[int],
    ) -> None:
        conn.execute(
            """
            INSERT INTO inventory_logs (product_id, branch_id, delta, reason, ref_type, ref_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (product_id, branch_id, delta, reason, ref_type, ref_id),
        )

    def list_inventory_logs(
        self, *, product_id: Optional[int] = None, branch_id: Optional[int] = None, limit: int = 100
    ) -> List[sqlite3.Row]:
        query = "SELECT * FROM inventory_logs WHERE 1=1"
        params: list[Any] = []
        if product_id:
            query += " AND product_id = ?"
            params.append(product_id)
        if branch_id:
            query += " AND branch_id = ?"
            params.append(branch_id)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self.connect() as conn:
            cur = conn.execute(query, params)
            return cur.fetchall()

    # ------------------------------------------------------------------
    # Cash movements and turns
    def get_current_turn(self, branch_id: int, user_id: int) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            cur = conn.execute(
                "SELECT * FROM turns WHERE branch_id = ? AND user_id = ? AND status = 'open' ORDER BY id DESC LIMIT 1",
                (branch_id, user_id),
            )
            return cur.fetchone()

    def get_active_turn(self, *, user_id: Optional[int] = None, branch_id: Optional[int] = None) -> Optional[sqlite3.Row]:
        """Return the active turn for the provided or current user/branch."""

        with self.connect() as conn:
            branch = branch_id or self._get_active_branch_id(conn)
            effective_user = user_id or STATE.user_id
            cur = conn.execute(
                "SELECT * FROM turns WHERE branch_id = ? AND user_id = ? AND status = 'open' ORDER BY id DESC LIMIT 1",
                (branch, effective_user),
            )
            return cur.fetchone()

    def open_turn(
        self, branch_id: int, user_id: int, opening_amount: float, notes: Optional[str] = None
    ) -> int:
        if opening_amount < 0:
            raise ValueError("El fondo inicial no puede ser negativo")
        with self.connect() as conn:
            existing = self.get_current_turn(branch_id, user_id)
            if existing:
                raise ValueError("Ya existe un turno abierto")
            cur = conn.execute(
                """
                INSERT INTO turns (branch_id, user_id, opened_at, opening_amount, status, notes)
                VALUES (?, ?, ?, ?, 'open', ?)
                """,
                (branch_id, user_id, datetime.utcnow().isoformat(), float(opening_amount), notes),
            )
            logger.info("Turn opened for user %s in branch %s", user_id, branch_id)
            self.register_audit(
                user_id=user_id,
                action="open_turn",
                payload={"turn_id": cur.lastrowid, "opening_amount": opening_amount, "branch_id": branch_id},
            )
            return cur.lastrowid

    def register_cash_movement(
        self,
        turn_id: Optional[int],
        movement_type: str,
        amount: float,
        *,
        reason: Optional[str] = None,
        branch_id: Optional[int] = None,
        user_id: Optional[int] = None,
    ) -> int:
        """Register a cash movement and tie it to the current turn."""

        if amount <= 0:
            raise ValueError("La cantidad debe ser mayor a cero")
        if movement_type not in {"in", "out"}:
            raise ValueError("Tipo de movimiento inválido")
        with self.connect() as conn:
            branch = branch_id or self._get_active_branch_id(conn)
            effective_user = user_id or STATE.user_id
            current_turn = turn_id
            if current_turn is None:
                turn_row = self.get_current_turn(branch, effective_user)
                if not turn_row:
                    raise ValueError("No hay turno abierto")
                current_turn = turn_row["id"]
            cur = conn.execute(
                """
                INSERT INTO cash_movements (branch_id, user_id, movement_type, type, amount, reason, turn_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (branch, effective_user, movement_type, movement_type, amount, reason, current_turn),
            )
            logger.info("Cash movement %s %.2f for turn %s", movement_type, amount, current_turn)
            self.register_audit(
                user_id=effective_user,
                action="cash_movement",
                payload={"turn_id": current_turn, "type": movement_type, "amount": amount, "reason": reason},
            )
            return cur.lastrowid

    def _cash_sales_for_turn(self, conn: sqlite3.Connection, turn_row: sqlite3.Row) -> float:
        start = turn_row["opened_at"]
        end = turn_row["closed_at"] or datetime.utcnow().isoformat()
        cur = conn.execute(
            "SELECT payment_breakdown FROM sales WHERE branch_id = ? AND user_id = ? AND ts BETWEEN ? AND ?",
            (turn_row["branch_id"], turn_row["user_id"], start, end),
        )
        cash_total = 0.0
        for row in cur.fetchall():
            try:
                bd = json.loads(row["payment_breakdown"] or "{}")
            except json.JSONDecodeError:
                continue
            flat = self._flatten_payment_amounts(bd)
            cash_total += float(flat.get("cash") or 0.0)
        return cash_total

    def _cash_movements_for_turn(self, conn: sqlite3.Connection, turn_id: int) -> float:
        cur = conn.execute(
            """
            SELECT
                SUM(CASE WHEN movement_type = 'in' THEN amount ELSE 0 END) AS ins,
                SUM(CASE WHEN movement_type = 'out' THEN amount ELSE 0 END) AS outs
            FROM cash_movements
            WHERE turn_id = ?
            """,
            (turn_id,),
        )
        row = cur.fetchone()
        return float(row["ins"] or 0.0) - float(row["outs"] or 0.0)

    def close_turn(self, turn_id: int, closing_amount: float, notes: Optional[str] = None) -> None:
        if closing_amount < 0:
            raise ValueError("El conteo no puede ser negativo")
        with self.connect() as conn:
            turn = conn.execute("SELECT * FROM turns WHERE id = ?", (turn_id,)).fetchone()
            if not turn or turn["status"] != "open":
                raise ValueError("Turno no encontrado o ya cerrado")
            summary = self.get_turn_summary(turn_id)
            expected = summary.get("expected_cash", 0.0)
            conn.execute(
                """
                UPDATE turns
                SET closed_at = ?, closing_amount = ?, expected_amount = ?, status = 'closed', notes = COALESCE(notes, '') || ?
                WHERE id = ?
                """,
                (datetime.utcnow().isoformat(), closing_amount, expected, f"\n{notes}" if notes else None, turn_id),
            )
            logger.info(
                "Closed turn %s with expected %.2f and counted %.2f (delta %.2f)",
                turn_id,
                expected,
                closing_amount,
                closing_amount - expected,
            )
            self.register_audit(
                user_id=turn["user_id"],
                action="close_turn",
                payload={
                    "turn_id": turn_id,
                    "expected": expected,
                    "counted": closing_amount,
                    "delta": closing_amount - expected,
                },
            )

    def list_turns(
        self,
        branch_id: int,
        status: Optional[str] = None,
        limit: int = 100,
        date_range: Optional[tuple[str, str]] = None,
    ) -> List[sqlite3.Row]:
        query = "SELECT * FROM turns WHERE branch_id = ?"
        params: list[Any] = [branch_id]
        if status and status != "all":
            query += " AND status = ?"
            params.append(status)
        if date_range:
            query += " AND date(opened_at) BETWEEN date(?) AND date(?)"
            params.extend([date_range[0], date_range[1]])
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self.connect() as conn:
            cur = conn.execute(query, params)
            return cur.fetchall()

    def add_cash_movement(
        self,
        movement_type: str,
        amount: float,
        *,
        reason: Optional[str] = None,
        branch_id: Optional[int] = None,
        user_id: Optional[int] = None,
        turn_id: Optional[int] = None,
    ) -> int:
        return self.register_cash_movement(turn_id, movement_type, amount, reason=reason, branch_id=branch_id, user_id=user_id)

    def list_cash_movements(self, turn_id: int) -> List[sqlite3.Row]:
        with self.connect() as conn:
            cur = conn.execute(
                "SELECT * FROM cash_movements WHERE turn_id = ? ORDER BY created_at DESC", (turn_id,)
            )
            return cur.fetchall()

    def delete_cash_movement(self, movement_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM cash_movements WHERE id = ?", (movement_id,))

    def _turn_time_bounds(self, turn_row: sqlite3.Row) -> tuple[str, str]:
        start = turn_row["opened_at"]
        end = turn_row["closed_at"] or datetime.utcnow().isoformat()
        return start, end

    def _turn_sales_breakdown(self, conn: sqlite3.Connection, turn_row: sqlite3.Row) -> dict[str, float]:
        start, end = self._turn_time_bounds(turn_row)
        cur = conn.execute(
            "SELECT payment_breakdown, payment_method, total FROM sales WHERE branch_id = ? AND user_id = ? AND ts BETWEEN ? AND ?",
            (turn_row["branch_id"], turn_row["user_id"], start, end),
        )
        totals: dict[str, float] = {}
        for row in cur.fetchall():
            bd = json.loads(row["payment_breakdown"] or "{}")
            flat = self._flatten_payment_amounts({"method": row["payment_method"], **bd})
            for key, val in flat.items():
                totals[key] = totals.get(key, 0.0) + float(val or 0.0)
        return totals

    def _turn_cash_movements(self, conn: sqlite3.Connection, turn_row: sqlite3.Row) -> tuple[float, float]:
        start, end = self._turn_time_bounds(turn_row)
        cur = conn.execute(
            "SELECT SUM(CASE WHEN movement_type='in' THEN amount ELSE 0 END) AS ins, SUM(CASE WHEN movement_type='out' THEN amount ELSE 0 END) AS outs FROM cash_movements WHERE turn_id = ? OR (branch_id = ? AND user_id = ? AND created_at BETWEEN ? AND ?)",
            (turn_row["id"], turn_row["branch_id"], turn_row["user_id"], start, end),
        )
        row = cur.fetchone()
        return float(row["ins"] or 0.0), float(row["outs"] or 0.0)

    def get_turn_summary(self, turn_id: int) -> dict[str, float]:
        with self.connect() as conn:
            turn = conn.execute("SELECT * FROM turns WHERE id = ?", (turn_id,)).fetchone()
            if not turn:
                raise ValueError("Turno no encontrado")
            sales = self._turn_sales_breakdown(conn, turn)
            cash_sales = sales.get("cash", 0.0)
            credit_sales = sales.get("credit", 0.0)
            layaway_payments = conn.execute(
                "SELECT COALESCE(SUM(lp.amount),0) AS total FROM layaway_payments lp JOIN layaways l ON l.id = lp.layaway_id WHERE l.branch_id = ? AND lp.timestamp BETWEEN ? AND ?",
                (turn["branch_id"], *self._turn_time_bounds(turn)),
            ).fetchone()["total"]
            credit_payments = conn.execute(
                "SELECT COALESCE(SUM(amount),0) AS total FROM credit_payments WHERE timestamp BETWEEN ? AND ?",
                self._turn_time_bounds(turn),
            ).fetchone()["total"]
            ins, outs = self._turn_cash_movements(conn, turn)
            opening = float(turn["opening_amount"] or 0.0)
            expected_cash = opening + cash_sales + float(layaway_payments or 0.0) + float(credit_payments or 0.0) + ins - outs
            return {
                "opening": opening,
                "cash_sales": cash_sales,
                "credit_sales": credit_sales,
                "layaway_payments": float(layaway_payments or 0.0),
                "credit_payments": float(credit_payments or 0.0),
                "ins": ins,
                "outs": outs,
                "expected_cash": expected_cash,
            }

    def get_turn_movements(self, turn_id: int) -> List[sqlite3.Row]:
        with self.connect() as conn:
            cur = conn.execute(
                "SELECT * FROM cash_movements WHERE turn_id = ? ORDER BY created_at DESC", (turn_id,),
            )
            return cur.fetchall()

    def turn_totals(self, turn_id: int) -> dict[str, float]:
        with self.connect() as conn:
            turn = conn.execute("SELECT * FROM turns WHERE id = ?", (turn_id,)).fetchone()
            if not turn:
                raise ValueError("Turno no encontrado")
            summary = self.get_turn_summary(turn_id)
            return {
                "cash_sales": summary.get("cash_sales", 0.0),
                "ins_outs": summary.get("ins", 0.0) - summary.get("outs", 0.0),
                "expected": summary.get("expected_cash", 0.0),
                "opening": summary.get("opening", 0.0),
            }

    # ------------------------------------------------------------------
    # Sales
    def _flatten_payment_amounts(self, breakdown: dict[str, Any]) -> dict[str, float]:
        """Return a flat mapping of method->amount for reporting."""

        method = breakdown.get("method")
        flat: dict[str, float] = {}
        if method == "mixed":
            nested = breakdown.get("breakdown", {}) or {}
            for key, value in nested.items():
                if isinstance(value, dict):
                    amount = float(value.get("amount") or 0.0)
                    if key == "card":
                        amount += float(value.get("card_fee") or 0.0)
                else:
                    amount = float(value or 0.0)
                flat[key] = flat.get(key, 0.0) + amount
            if "usd" in nested:
                usd_val = nested.get("usd") or {}
                usd_amount = float(usd_val.get("usd_amount") or usd_val.get("amount") or 0.0)
                usd_exchange = float(usd_val.get("usd_exchange") or 0.0)
                if usd_amount and usd_exchange:
                    flat["usd"] = usd_amount * usd_exchange
        else:
            # single method
            if method:
                amount = float(
                    breakdown.get("amount_mxn")
                    or breakdown.get("amount")
                    or breakdown.get("paid_amount")
                    or breakdown.get(method)
                    or 0.0
                )
                if method == "card":
                    amount += float(breakdown.get("card_fee") or 0.0)
                flat[method] = amount
            if method == "usd":
                usd_amount = float(breakdown.get("usd_amount") or 0.0)
                usd_exchange = float(breakdown.get("usd_exchange") or 0.0)
                if usd_amount and usd_exchange:
                    flat["usd"] = usd_amount * usd_exchange
        return flat

    def create_sale(
        self,
        items: Sequence[dict[str, Any]],
        payment_breakdown: dict[str, Any],
        *,
        discount: float = 0.0,
        customer_id: Optional[int] = None,
        user_id: Optional[int] = None,
        branch_id: Optional[int] = None,
    ) -> int:
        """Create a sale, deduct stock, and return the sale ID."""
        if not items:
            raise ValueError("Sale requires at least one item")
        with self.connect() as conn:
            branch = branch_id or self._get_active_branch_id(conn)
            effective_user = user_id or STATE.user_id
            tax_rate = self.get_tax_rate(branch)
            subtotal = 0.0
            tax_total = 0.0
            total = 0.0
            prepared_items: list[tuple[int, float, float, float, float, float, str]] = []
            for item in items:
                original_product_id = item.get("product_id")
                product_id = original_product_id if original_product_id is not None else self._ensure_common_product(conn)
                product_row = None
                if original_product_id is not None:
                    product_row = self.get_product(original_product_id)
                sale_type = (item.get("sale_type") or (product_row or {}).get("sale_type") or "unit").lower()
                qty = float(item.get("qty", 1))
                price = float(item.get("price", 0.0))
                is_wholesale = bool(item.get("is_wholesale", False))
                metadata: dict[str, Any] = {}
                if is_wholesale:
                    metadata["wholesale"] = True
                line_discount = 0.0 if is_wholesale else float(item.get("discount", 0.0))
                includes_tax = bool(item.get("price_includes_tax", False))
                if sale_type == "kit":
                    metadata["kit"] = True
                if sale_type == "weight":
                    metadata["weight"] = True
                line_base = price * qty
                if includes_tax:
                    gross = max(line_base - line_discount, 0)
                    base_without_tax = gross / (1 + tax_rate)
                    line_tax = gross - base_without_tax
                    line_total = gross
                else:
                    base_without_tax = max(line_base - line_discount, 0)
                    line_tax = base_without_tax * tax_rate
                    line_total = base_without_tax + line_tax
                subtotal += base_without_tax
                tax_total += line_tax
                total += line_total
                prepared_items.append(
                    (product_id, qty, price, line_discount, line_total, includes_tax, json.dumps(metadata))
                )
                if original_product_id is not None and (product_row or {}).get("uses_inventory", 1):
                    if sale_type == "kit":
                        for component in self.get_kit_items(original_product_id):
                            comp_qty = qty * float(component.get("qty", 1))
                            comp_id = int(component.get("product_id"))
                            conn.execute(
                                "INSERT OR IGNORE INTO product_stocks (product_id, branch_id) VALUES (?, ?)",
                                (comp_id, branch),
                            )
                            conn.execute(
                                "UPDATE product_stocks SET stock = stock - ?, updated_at = CURRENT_TIMESTAMP WHERE product_id = ? AND branch_id = ?",
                                (comp_qty, comp_id, branch),
                            )
                            self._log_inventory(conn, comp_id, branch, -comp_qty, "sale_kit", f"kit:{product_id}")
                    else:
                        conn.execute(
                            "INSERT OR IGNORE INTO product_stocks (product_id, branch_id) VALUES (?, ?)",
                            (product_id, branch),
                        )
                        conn.execute(
                            "UPDATE product_stocks SET stock = stock - ?, updated_at = CURRENT_TIMESTAMP WHERE product_id = ? AND branch_id = ?",
                            (qty, product_id, branch),
                        )
                        self._log_inventory(conn, product_id, branch, -qty, "sale", "sale")
            final_total = max(total - discount, 0)
            breakdown = payment_breakdown or {}
            payment_method = breakdown.get("method", "cash")
            reference = breakdown.get("reference")
            card_fee = float(breakdown.get("card_fee") or breakdown.get("fee") or 0.0)
            usd_amount = float(
                breakdown.get("usd_amount")
                or breakdown.get("usd_given")
                or (breakdown.get("usd") or {}).get("usd_amount")
                or 0.0
            )
            usd_exchange = float(
                breakdown.get("usd_exchange")
                or breakdown.get("exchange_rate")
                or (breakdown.get("usd") or {}).get("usd_exchange")
                or 0.0
            )
            voucher_amount = float(
                breakdown.get("voucher_amount")
                or breakdown.get("vouchers")
                or (breakdown.get("voucher") or {}).get("amount")
                or 0.0
            )
            check_number = breakdown.get("check_number")
            if payment_method == "mixed":
                nested = breakdown.get("breakdown") or {}
                card_info = nested.get("card") or {}
                card_fee += float(card_info.get("fee") or card_info.get("card_fee") or 0.0)
                reference = reference or card_info.get("reference")
                usd_info = nested.get("usd") or {}
                usd_amount = float(usd_info.get("usd_amount") or usd_info.get("usd_given") or usd_amount)
                usd_exchange = float(usd_info.get("usd_exchange") or usd_info.get("exchange_rate") or usd_exchange)
                voucher_amount = float(nested.get("vouchers") or voucher_amount)
                check_info = nested.get("check") or {}
                check_number = check_number or check_info.get("check_number")
            if card_fee > 0:
                final_total += card_fee
                breakdown["card_fee"] = card_fee
            if usd_amount and usd_exchange:
                breakdown["amount_mxn"] = usd_amount * usd_exchange
                breakdown.setdefault("usd_amount", usd_amount)
                breakdown.setdefault("usd_exchange", usd_exchange)
            if voucher_amount > 0:
                breakdown.setdefault("voucher_amount", voucher_amount)
            payment_credit_amount = float(breakdown.get("credit_amount") or 0.0)
            credit_delta = final_total if payment_method == "credit" else payment_credit_amount
            if credit_delta > 0:
                if not customer_id:
                    raise ValueError("Venta a crédito requiere cliente asignado")
                customer_row = self.get_customer(customer_id)
                if not customer_row:
                    raise ValueError("Cliente no encontrado para crédito")
                customer = dict(customer_row)
                current_balance = float(customer.get("credit_balance", 0.0) or 0.0)
                credit_limit = float(customer.get("credit_limit", 0.0) or 0.0)
                projected = current_balance + credit_delta
                if credit_limit and projected > credit_limit:
                    raise ValueError("Límite de crédito excedido para el cliente")
            cur = conn.execute(
                """
                INSERT INTO sales (
                    branch_id, user_id, customer_id, subtotal, discount, total, payment_method, payment_breakdown, reference, card_fee, usd_amount, usd_exchange, voucher_amount, check_number, turn_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    branch,
                    effective_user,
                    customer_id,
                    subtotal,
                    discount,
                    final_total,
                    payment_method,
                    json.dumps(breakdown or {}),
                    reference,
                    card_fee if card_fee else None,
                    usd_amount if usd_amount else None,
                    usd_exchange if usd_exchange else None,
                    voucher_amount if voucher_amount else None,
                    check_number,
                    (self.get_current_turn(branch, effective_user) or {}).get("id"),
                ),
            )
            sale_id = cur.lastrowid
            for product_id, qty, price, line_discount, line_total, includes_tax, metadata_json in prepared_items:
                conn.execute(
                    """
                    INSERT INTO sale_items (sale_id, product_id, qty, price, discount, total, price_includes_tax, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (sale_id, product_id, qty, price, line_discount, line_total, int(includes_tax), metadata_json),
                )
            if credit_delta > 0 and customer_id:
                conn.execute(
                    "UPDATE customers SET credit_balance = credit_balance + ? WHERE id = ?",
                    (credit_delta, customer_id),
                )
            logger.info("Registered sale %s with total %.2f (subtotal %.2f, tax %.2f)", sale_id, final_total, subtotal, tax_total)
            self.register_audit(
                user_id=effective_user,
                action="create_sale",
                payload={
                    "sale_id": sale_id,
                    "total": final_total,
                    "payment_method": payment_method,
                },
            )
            return sale_id

    def list_recent_sales(self, *, limit: int = 50) -> List[sqlite3.Row]:
        with self.connect() as conn:
            cur = conn.execute(
                "SELECT id, ts, total FROM sales ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            return cur.fetchall()

    def get_sale(self, sale_id: int) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            cur = conn.execute(
                """
                SELECT s.*, c.rfc as customer_rfc, c.first_name || ' ' || IFNULL(c.last_name,'') as customer_name
                FROM sales s
                LEFT JOIN customers c ON c.id = s.customer_id
                WHERE s.id = ?
                """,
                (sale_id,),
            )
            return cur.fetchone()

    def get_sale_items(self, sale_id: int) -> List[sqlite3.Row]:
        with self.connect() as conn:
            cur = conn.execute(
                """
                SELECT si.*, p.name
                FROM sale_items si
                JOIN products p ON p.id = si.product_id
                WHERE si.sale_id = ?
                ORDER BY si.id
                """,
                (sale_id,),
            )
            return cur.fetchall()

    # ------------------------------------------------------------------
    # Layaways
    def _compute_layaway_paid(self, conn: sqlite3.Connection, layaway_id: int) -> float:
        paid = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM layaway_payments WHERE layaway_id = ?",
            (layaway_id,),
        ).fetchone()
        return float(paid["total"] or 0.0) if paid else 0.0

    def _consume_reserved_stock(self, conn: sqlite3.Connection, layaway_id: int, branch_id: int) -> None:
        items = conn.execute(
            "SELECT product_id, qty FROM layaway_items WHERE layaway_id = ?",
            (layaway_id,),
        ).fetchall()
        for item in items:
            conn.execute(
                """
                UPDATE product_stocks
                SET reserved = MAX(reserved - ?, 0),
                    stock = stock - ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE product_id = ? AND branch_id = ?
                """,
                (item["qty"], item["qty"], item["product_id"], branch_id),
            )
            self._log_inventory(conn, item["product_id"], branch_id, -item["qty"], "layaway liquidate", "layaway", layaway_id)

    def _release_reserved_stock(self, conn: sqlite3.Connection, layaway_id: int, branch_id: int) -> None:
        items = conn.execute(
            "SELECT product_id, qty FROM layaway_items WHERE layaway_id = ?",
            (layaway_id,),
        ).fetchall()
        for item in items:
            conn.execute(
                """
                UPDATE product_stocks
                SET reserved = MAX(reserved - ?, 0),
                    stock = stock + ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE product_id = ? AND branch_id = ?
                """,
                (item["qty"], item["qty"], item["product_id"], branch_id),
            )
            self._log_inventory(conn, item["product_id"], branch_id, item["qty"], "layaway cancel", "layaway", layaway_id)

    def create_layaway(
        self,
        items: Sequence[dict[str, Any]],
        *,
        deposit: float = 0.0,
        due_date: Optional[str] = None,
        customer_id: Optional[int] = None,
        branch_id: Optional[int] = None,
        notes: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> int:
        if not items:
            raise ValueError("Layaway requires at least one item")
        with self.connect() as conn:
            branch = branch_id or self._get_active_branch_id(conn)
            total = sum((item.get("price", 0.0) * item.get("qty", 1)) - item.get("discount", 0.0) for item in items)
            deposit = min(float(deposit or 0.0), total)
            balance = max(total - deposit, 0)
            status = "liquidado" if balance <= 0 else "pendiente"
            cur = conn.execute(
                """
                INSERT INTO layaways (branch_id, customer_id, total, deposit, balance, status, due_date, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (branch, customer_id, total, deposit, balance, status, due_date, notes),
            )
            layaway_id = cur.lastrowid
            for item in items:
                product_id = item.get("product_id")
                qty = float(item.get("qty", 1))
                price = float(item.get("price", 0.0))
                line_discount = float(item.get("discount", 0.0))
                line_total = (qty * price) - line_discount
                conn.execute(
                    """
                    INSERT INTO layaway_items (layaway_id, product_id, qty, price, discount, total)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (layaway_id, product_id, qty, price, line_discount, line_total),
                )
                conn.execute(
                    "INSERT OR IGNORE INTO product_stocks (product_id, branch_id) VALUES (?, ?)",
                    (product_id, branch),
                )
                conn.execute(
                    "UPDATE product_stocks SET reserved = reserved + ?, updated_at = CURRENT_TIMESTAMP WHERE product_id = ? AND branch_id = ?",
                    (qty, product_id, branch),
                )
                self._log_inventory(conn, product_id, branch, -qty, "layaway reserve", "layaway", layaway_id)
            if deposit > 0:
                conn.execute(
                    """
                    INSERT INTO layaway_payments (layaway_id, amount, timestamp, notes, user_id)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (layaway_id, deposit, datetime.utcnow().isoformat(), "Depósito inicial", user_id),
                )
            if status == "liquidado":
                self._consume_reserved_stock(conn, layaway_id, branch)
            logger.info("Created layaway %s with balance %.2f", layaway_id, balance)
            self.register_audit(
                user_id=user_id,
                action="create_layaway",
                payload={"layaway_id": layaway_id, "total": total, "deposit": deposit},
            )
            return layaway_id

    def add_layaway_payment(
        self, layaway_id: int, amount: float, *, notes: Optional[str] = None, user_id: Optional[int] = None
    ) -> int:
        if amount <= 0:
            raise ValueError("El abono debe ser mayor a cero")
        with self.connect() as conn:
            layaway = conn.execute(
                "SELECT total, deposit, balance, status, branch_id FROM layaways WHERE id = ?",
                (layaway_id,),
            ).fetchone()
            if not layaway:
                raise ValueError("Apartado no encontrado")
            if layaway["status"] == "cancelado":
                raise ValueError("No se puede abonar a un apartado cancelado")
            paid_so_far = layaway["deposit"] + self._compute_layaway_paid(conn, layaway_id)
            balance_before = max(layaway["total"] - paid_so_far, 0)
            if amount > balance_before:
                raise ValueError("El abono no puede ser mayor al saldo")
            cur = conn.execute(
                """
                INSERT INTO layaway_payments (layaway_id, amount, timestamp, notes, user_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (layaway_id, amount, datetime.utcnow().isoformat(), notes, user_id),
            )
            paid_after = paid_so_far + amount
            new_balance = max(layaway["total"] - paid_after, 0)
            new_status = "liquidado" if new_balance <= 0 else "pendiente"
            conn.execute(
                "UPDATE layaways SET balance = ?, status = ? WHERE id = ?",
                (new_balance, new_status, layaway_id),
            )
            if new_status == "liquidado" and layaway["status"] != "liquidado":
                self._consume_reserved_stock(conn, layaway_id, layaway["branch_id"])
            logger.info("Recorded layaway payment %.2f for %s (new balance %.2f)", amount, layaway_id, new_balance)
            self.register_audit(
                user_id=user_id,
                action="layaway_payment",
                payload={"layaway_id": layaway_id, "amount": amount, "balance": new_balance},
            )
            return cur.lastrowid

    def list_layaways(
        self,
        *,
        branch_id: Optional[int] = None,
        status: Optional[str] = None,
        customer_id: Optional[int] = None,
        date_range: Optional[tuple[str, str]] = None,
        limit: int = 200,
    ) -> List[sqlite3.Row]:
        query = """
            WITH pagos AS (
                SELECT layaway_id, COALESCE(SUM(amount),0) AS paid
                FROM layaway_payments
                GROUP BY layaway_id
            )
            SELECT l.*, TRIM(COALESCE(c.first_name,'') || ' ' || COALESCE(c.last_name,'')) as customer_name,
                   COALESCE(p.paid, 0) + l.deposit AS paid_total,
                   MAX(l.total - (COALESCE(p.paid,0) + l.deposit), 0) AS balance_calc,
                   CASE
                       WHEN l.status = 'pendiente' AND l.due_date IS NOT NULL AND date(l.due_date) < date('now') THEN 'vencido'
                       ELSE l.status
                   END AS display_status
            FROM layaways l
            LEFT JOIN pagos p ON p.layaway_id = l.id
            LEFT JOIN customers c ON c.id = l.customer_id
            WHERE 1=1
        """
        params: list[Any] = []
        if branch_id:
            query += " AND l.branch_id = ?"
            params.append(branch_id)
        if customer_id:
            query += " AND l.customer_id = ?"
            params.append(customer_id)
        if date_range:
            query += " AND date(l.created_at) BETWEEN date(?) AND date(?)"
            params.extend([date_range[0], date_range[1]])
        if status and status not in ("all", "Todos"):
            if status == "vencido":
                query += " AND l.status = 'pendiente' AND l.due_date IS NOT NULL AND date(l.due_date) < date('now')"
            else:
                query += " AND l.status = ?"
                params.append(status)
        query += " ORDER BY l.id DESC LIMIT ?"
        params.append(limit)
        with self.connect() as conn:
            cur = conn.execute(query, params)
            return cur.fetchall()

    def get_layaway(self, layaway_id: int) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            cur = conn.execute(
                """
                WITH pagos AS (
                    SELECT layaway_id, COALESCE(SUM(amount),0) AS paid
                    FROM layaway_payments
                    GROUP BY layaway_id
                )
                SELECT l.*, TRIM(COALESCE(c.first_name,'') || ' ' || COALESCE(c.last_name,'')) AS customer_name,
                       COALESCE(p.paid,0) + l.deposit AS paid_total,
                       MAX(l.total - (COALESCE(p.paid,0) + l.deposit), 0) AS balance_calc,
                       CASE
                           WHEN l.status = 'pendiente' AND l.due_date IS NOT NULL AND date(l.due_date) < date('now') THEN 'vencido'
                           ELSE l.status
                       END AS display_status
                FROM layaways l
                LEFT JOIN pagos p ON p.layaway_id = l.id
                LEFT JOIN customers c ON c.id = l.customer_id
                WHERE l.id = ?
                """,
                (layaway_id,),
            )
            return cur.fetchone()

    def get_layaway_items(self, layaway_id: int) -> List[sqlite3.Row]:
        with self.connect() as conn:
            cur = conn.execute(
                """
                SELECT li.*, p.name
                FROM layaway_items li
                JOIN products p ON p.id = li.product_id
                WHERE li.layaway_id = ?
                ORDER BY li.id
                """,
                (layaway_id,),
            )
            return cur.fetchall()

    def get_layaway_payments(self, layaway_id: int) -> List[sqlite3.Row]:
        with self.connect() as conn:
            cur = conn.execute(
                "SELECT * FROM layaway_payments WHERE layaway_id = ? ORDER BY timestamp DESC",
                (layaway_id,),
            )
            return cur.fetchall()

    def cancel_layaway(self, layaway_id: int, *, user_id: Optional[int] = None) -> None:
        with self.connect() as conn:
            layaway = conn.execute("SELECT status, branch_id FROM layaways WHERE id = ?", (layaway_id,)).fetchone()
            if not layaway:
                raise ValueError("Apartado no encontrado")
            if layaway["status"] == "cancelado":
                return
            self._release_reserved_stock(conn, layaway_id, layaway["branch_id"])
            conn.execute(
                "UPDATE layaways SET status = 'cancelado', balance = 0 WHERE id = ?",
                (layaway_id,),
            )
            logger.info("Cancelled layaway %s", layaway_id)

    def liquidate_layaway(self, layaway_id: int, *, user_id: Optional[int] = None) -> None:
        with self.connect() as conn:
            layaway = conn.execute("SELECT status, branch_id FROM layaways WHERE id = ?", (layaway_id,)).fetchone()
            if not layaway:
                raise ValueError("Apartado no encontrado")
            if layaway["status"] == "cancelado":
                raise ValueError("No se puede liquidar un apartado cancelado")
            self._consume_reserved_stock(conn, layaway_id, layaway["branch_id"])
            conn.execute(
                "UPDATE layaways SET status = 'liquidado', balance = 0 WHERE id = ?",
                (layaway_id,),
            )
            logger.info("Liquidated layaway %s", layaway_id)

    # ------------------------------------------------------------------
    # Reporting helpers
    def sales_summary(
        self, *, date_from: Optional[str] = None, date_to: Optional[str] = None, branch_id: Optional[int] = None
    ) -> dict[str, Any]:
        query = "SELECT COUNT(*) AS sales_count, SUM(subtotal) AS subtotal, SUM(discount) AS discounts, SUM(total) AS total FROM sales WHERE 1=1"
        params: list[Any] = []
        if branch_id:
            query += " AND branch_id = ?"
            params.append(branch_id)
        if date_from:
            query += " AND date(ts) >= date(?)"
            params.append(date_from)
        if date_to:
            query += " AND date(ts) <= date(?)"
            params.append(date_to)
        with self.connect() as conn:
            row = conn.execute(query, params).fetchone()
            return {
                "sales_count": row["sales_count"] or 0,
                "subtotal": row["subtotal"] or 0.0,
                "discounts": row["discounts"] or 0.0,
                "total": row["total"] or 0.0,
            }

    def top_products(
        self, *, date_from: Optional[str] = None, date_to: Optional[str] = None, limit: int = 10
    ) -> List[sqlite3.Row]:
        query = """
            SELECT p.id, p.name, p.sku, SUM(si.qty) AS total_qty, SUM(si.total) AS revenue
            FROM sale_items si
            JOIN sales s ON s.id = si.sale_id
            JOIN products p ON p.id = si.product_id
            WHERE 1=1
        """
        params: list[Any] = []
        if date_from:
            query += " AND date(s.ts) >= date(?)"
            params.append(date_from)
        if date_to:
            query += " AND date(s.ts) <= date(?)"
            params.append(date_to)
        query += " GROUP BY p.id, p.name, p.sku ORDER BY revenue DESC LIMIT ?"
        params.append(limit)
        with self.connect() as conn:
            cur = conn.execute(query, params)
            return cur.fetchall()

    def daily_sales(
        self, *, date_from: Optional[str] = None, date_to: Optional[str] = None
    ) -> List[sqlite3.Row]:
        query = "SELECT date(ts) as day, SUM(total) as total, COUNT(*) as sales_count FROM sales WHERE 1=1"
        params: list[Any] = []
        if date_from:
            query += " AND date(ts) >= date(?)"
            params.append(date_from)
        if date_to:
            query += " AND date(ts) <= date(?)"
            params.append(date_to)
        query += " GROUP BY day ORDER BY day"
        with self.connect() as conn:
            cur = conn.execute(query, params)
            return cur.fetchall()

    def get_sales_by_range(
        self, *, date_from: Optional[str] = None, date_to: Optional[str] = None, branch_id: Optional[int] = None
    ) -> list[dict[str, Any]]:
        query = """
            SELECT s.*, u.full_name AS cashier,
                   COALESCE(c.first_name || ' ' || c.last_name, c.first_name, '') AS customer_name
            FROM sales s
            LEFT JOIN users u ON u.id = s.user_id
            LEFT JOIN customers c ON c.id = s.customer_id
            WHERE 1=1
        """
        params: list[Any] = []
        if date_from:
            query += " AND date(s.ts) >= date(?)"
            params.append(date_from)
        if date_to:
            query += " AND date(s.ts) <= date(?)"
            params.append(date_to)
        if branch_id:
            query += " AND s.branch_id = ?"
            params.append(branch_id)
        query += " ORDER BY s.ts DESC"
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            breakdown = json.loads(row["payment_breakdown"] or "{}")
            method_keys = [k for k, v in breakdown.items() if v]
            results.append(
                {
                    **dict(row),
                    "payment_methods": ", ".join(method_keys) if method_keys else "--",
                    "payment_data": breakdown,
                }
            )
        return results

    def get_sales_by_method(
        self, *, date_from: Optional[str] = None, date_to: Optional[str] = None, branch_id: Optional[int] = None
    ) -> list[dict[str, Any]]:
        """Aggregate sales totals by payment method including mixed breakdowns."""

        sales = self.get_sales_by_range(date_from=date_from, date_to=date_to, branch_id=branch_id)
        totals: dict[str, float] = {}
        for sale in sales:
            for method, amount in self._flatten_payment_amounts(sale.get("payment_data", {})).items():
                totals[method] = totals.get(method, 0.0) + float(amount or 0.0)
        return [
            {"method": method, "amount": total} for method, total in sorted(totals.items(), key=lambda x: x[1], reverse=True)
        ]

    def get_sale_items_by_range(
        self, *, date_from: Optional[str] = None, date_to: Optional[str] = None, branch_id: Optional[int] = None
    ) -> list[sqlite3.Row]:
        query = """
            SELECT si.product_id, p.name, p.sku, SUM(si.qty) AS qty, SUM(si.total) AS total
            FROM sale_items si
            JOIN sales s ON s.id = si.sale_id
            LEFT JOIN products p ON p.id = si.product_id
            WHERE 1=1
        """
        params: list[Any] = []
        if date_from:
            query += " AND date(s.ts) >= date(?)"
            params.append(date_from)
        if date_to:
            query += " AND date(s.ts) <= date(?)"
            params.append(date_to)
        if branch_id:
            query += " AND s.branch_id = ?"
            params.append(branch_id)
        query += " GROUP BY si.product_id, p.name, p.sku ORDER BY total DESC"
        with self.connect() as conn:
            return conn.execute(query, params).fetchall()

    def get_sales_grouped_by_date(
        self, *, date_from: Optional[str] = None, date_to: Optional[str] = None, branch_id: Optional[int] = None
    ) -> list[sqlite3.Row]:
        query = "SELECT date(ts) as day, SUM(subtotal) as subtotal, SUM(total) as total, SUM(discount) as discount FROM sales WHERE 1=1"
        params: list[Any] = []
        if date_from:
            query += " AND date(ts) >= date(?)"
            params.append(date_from)
        if date_to:
            query += " AND date(ts) <= date(?)"
            params.append(date_to)
        if branch_id:
            query += " AND branch_id = ?"
            params.append(branch_id)
        query += " GROUP BY day ORDER BY day"
        with self.connect() as conn:
            return conn.execute(query, params).fetchall()

    def get_sales_grouped_by_hour(
        self, *, date_from: Optional[str] = None, date_to: Optional[str] = None, branch_id: Optional[int] = None
    ) -> list[sqlite3.Row]:
        query = "SELECT strftime('%H', ts) as hour, SUM(total) as total, COUNT(*) as count FROM sales WHERE 1=1"
        params: list[Any] = []
        if date_from:
            query += " AND date(ts) >= date(?)"
            params.append(date_from)
        if date_to:
            query += " AND date(ts) <= date(?)"
            params.append(date_to)
        if branch_id:
            query += " AND branch_id = ?"
            params.append(branch_id)
        query += " GROUP BY hour ORDER BY hour"
        with self.connect() as conn:
            return conn.execute(query, params).fetchall()

    def get_sales_grouped_by_payment(
        self, *, date_from: Optional[str] = None, date_to: Optional[str] = None, branch_id: Optional[int] = None
    ) -> list[dict[str, Any]]:
        sales = self.get_sales_by_range(date_from=date_from, date_to=date_to, branch_id=branch_id)
        totals: dict[str, float] = {}
        for sale in sales:
            breakdown: dict[str, Any] = sale.get("payment_data", {})
            flat = self._flatten_payment_amounts(breakdown)
            for method, amount in flat.items():
                totals[method] = totals.get(method, 0.0) + float(amount)
        return [
            {"method": method, "amount": amount}
            for method, amount in sorted(totals.items(), key=lambda x: x[1], reverse=True)
        ]

    def get_sales_grouped_by_user(
        self, *, date_from: Optional[str] = None, date_to: Optional[str] = None, branch_id: Optional[int] = None
    ) -> list[sqlite3.Row]:
        query = """
            SELECT COALESCE(u.full_name, u.username, 'N/D') AS cashier,
                   COUNT(*) AS sales_count,
                   SUM(total) AS total
            FROM sales s
            LEFT JOIN users u ON u.id = s.user_id
            WHERE 1=1
        """
        params: list[Any] = []
        if date_from:
            query += " AND date(s.ts) >= date(?)"
            params.append(date_from)
        if date_to:
            query += " AND date(s.ts) <= date(?)"
            params.append(date_to)
        if branch_id:
            query += " AND s.branch_id = ?"
            params.append(branch_id)
        query += " GROUP BY cashier ORDER BY total DESC"
        with self.connect() as conn:
            return conn.execute(query, params).fetchall()

    def get_profit_by_range(
        self, *, date_from: Optional[str] = None, date_to: Optional[str] = None, branch_id: Optional[int] = None
    ) -> dict[str, Any]:
        query = """
            SELECT p.id, p.name, p.sku,
                   SUM(si.qty) AS qty,
                   SUM(si.total) AS revenue,
                   SUM(si.qty * p.cost) AS cost
            FROM sale_items si
            JOIN sales s ON s.id = si.sale_id
            LEFT JOIN products p ON p.id = si.product_id
            WHERE 1=1
        """
        params: list[Any] = []
        if date_from:
            query += " AND date(s.ts) >= date(?)"
            params.append(date_from)
        if date_to:
            query += " AND date(s.ts) <= date(?)"
            params.append(date_to)
        if branch_id:
            query += " AND s.branch_id = ?"
            params.append(branch_id)
        query += " GROUP BY p.id, p.name, p.sku"
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        total_revenue = sum(float(r["revenue"] or 0) for r in rows)
        total_cost = sum(float(r["cost"] or 0) for r in rows)
        return {
            "total_sales": total_revenue,
            "total_cost": total_cost,
            "margin": total_revenue - total_cost,
            "items": rows,
        }

    def get_returns_report(
        self, *, date_from: Optional[str] = None, date_to: Optional[str] = None, branch_id: Optional[int] = None
    ) -> list[sqlite3.Row]:
        query = """
            SELECT r.id, r.sale_id, r.qty, r.reason, r.created_at,
                   p.name AS product_name, p.sku,
                   s.branch_id,
                   COALESCE(u.full_name, u.username) AS cashier
            FROM sale_returns r
            JOIN products p ON p.id = r.product_id
            JOIN sales s ON s.id = r.sale_id
            LEFT JOIN users u ON u.id = s.user_id
            WHERE 1=1
        """
        params: list[Any] = []
        if date_from:
            query += " AND date(r.created_at) >= date(?)"
            params.append(date_from)
        if date_to:
            query += " AND date(r.created_at) <= date(?)"
            params.append(date_to)
        if branch_id:
            query += " AND s.branch_id = ?"
            params.append(branch_id)
        query += " ORDER BY r.created_at DESC"
        with self.connect() as conn:
            return conn.execute(query, params).fetchall()

    def get_credit_report(
        self, *, date_from: Optional[str] = None, date_to: Optional[str] = None, branch_id: Optional[int] = None
    ) -> dict[str, Any]:
        accounts = self.list_credit_accounts()
        total_balance = sum(float(acc["credit_balance"] or 0) for acc in accounts)
        payments = [dict(row) for row in self.list_all_credit_payments(limit=500)]
        if date_from or date_to:
            payments = [
                p
                for p in payments
                if (not date_from or str(p.get("timestamp", "")) >= date_from)
                and (not date_to or str(p.get("timestamp", "")) <= date_to)
            ]
        if branch_id:
            payments = [p for p in payments if p.get("branch_id") in (None, branch_id)]
        total_payments = sum(float(p.get("amount", 0.0) or 0.0) for p in payments)
        return {"accounts": accounts, "total": total_balance, "payments": payments, "total_payments": total_payments}

    def get_layaway_report(
        self, *, date_from: Optional[str] = None, date_to: Optional[str] = None, branch_id: Optional[int] = None
    ) -> dict[str, Any]:
        layaways = self.list_layaways(status=None, branch_id=branch_id, date_range=(date_from, date_to))
        total_balance = sum(float(l.get("balance_calc", l.get("balance", 0)) or 0) for l in layaways)
        total_deposits = sum(float(l.get("deposit", 0) or 0) for l in layaways)
        return {"layaways": layaways, "total_balance": total_balance, "total_deposits": total_deposits}

    def get_cash_report(self, turn_id: int) -> dict[str, Any]:
        totals = self.turn_totals(turn_id)
        movements = self.list_cash_movements(turn_id)
        return {"totals": totals, "movements": movements}

    def get_turn_report(self, turn_id: int) -> dict[str, Any]:
        summary = self.get_turn_summary(turn_id)
        movements = self.list_cash_movements(turn_id)
        return {"summary": summary, "movements": movements}

    def get_turns_by_range(
        self, *, date_from: Optional[str] = None, date_to: Optional[str] = None, branch_id: Optional[int] = None
    ) -> list[sqlite3.Row]:
        query = "SELECT * FROM turns WHERE 1=1"
        params: list[Any] = []
        if date_from:
            query += " AND date(opened_at) >= date(?)"
            params.append(date_from)
        if date_to:
            query += " AND date(opened_at) <= date(?)"
            params.append(date_to)
        if branch_id:
            query += " AND branch_id = ?"
            params.append(branch_id)
        query += " ORDER BY opened_at DESC"
        with self.connect() as conn:
            return conn.execute(query, params).fetchall()

    # ------------------------------------------------------------------
    # CFDI issuing
    def _pac_client(self) -> PACClient:
        cfg = self.get_fiscal_config()
        return PACClient(
            cfg.get("pac_base_url", ""),
            cfg.get("pac_user", ""),
            cfg.get("pac_password", ""),
            cfg.get("csd_cert_path"),
            cfg.get("csd_key_path"),
            cfg.get("csd_key_password"),
        )

    def issue_cfdi_for_sale(
        self,
        sale_id: int,
        uso_cfdi: str = "G03",
        forma_pago: str = "01",
        metodo_pago: str = "PUE",
    ) -> dict[str, Any]:
        sale_row = self.get_sale(sale_id)
        if not sale_row:
            raise ValueError("Venta no encontrada")
        cfg = self.get_fiscal_config()
        items_rows = self.get_sale_items(sale_id)
        items = [dict(r) for r in items_rows]
        folio = self.get_next_folio()
        sale_dict = dict(sale_row)
        sale_dict["folio"] = folio
        xml = build_cfdi_ingreso_xml(sale_dict, items, cfg, uso_cfdi=uso_cfdi, forma_pago=forma_pago, metodo_pago=metodo_pago)
        pac = self._pac_client()
        resp = pac.timbrar_xml(xml)
        cfdi_dir = DATA_DIR / "cfdi"
        cfdi_dir.mkdir(parents=True, exist_ok=True)
        xml_path = cfdi_dir / f"{folio}_{resp['uuid']}.xml"
        xml_path.write_text(resp.get("xml_timbrado", xml), encoding="utf-8")
        cfdi_payload = {
            "uuid": resp.get("uuid"),
            "serie": cfg.get("serie_factura", "F"),
            "folio": folio.replace(cfg.get("serie_factura", "F"), ""),
            "fecha": resp.get("fecha_timbrado", datetime.utcnow().isoformat()),
            "totals": {"subtotal": sale_dict.get("subtotal", 0), "tax": sale_dict.get("total", 0) - sale_dict.get("subtotal", 0), "total": sale_dict.get("total", 0)},
            "emitter": {"razon_social": cfg.get("razon_social_emisor", ""), "rfc": cfg.get("rfc_emisor", "")},
            "receiver": {"name": sale_dict.get("customer_name", "Publico en general"), "rfc": sale_dict.get("customer_rfc", "XAXX010101000")},
            "sello_sat": resp.get("sello_sat"),
            "cert_sat": resp.get("no_certificado_sat"),
        }
        pdf_path = cfdi_dir / f"{folio}_{resp['uuid']}.pdf"
        export_cfdi_pdf(cfdi_payload, items, resp.get("xml_timbrado", xml), pdf_path)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO cfdi_issued (sale_id, customer_id, uuid, serie, folio, fecha, total, xml_path, pdf_path, status, tipo_comprobante, uso_cfdi, forma_pago, metodo_pago, moneda)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'vigente', 'I', ?, ?, ?, 'MXN')
                """,
                (
                    sale_id,
                    sale_row.get("customer_id"),
                    resp.get("uuid"),
                    cfg.get("serie_factura", "F"),
                    folio.replace(cfg.get("serie_factura", "F"), ""),
                    resp.get("fecha_timbrado", datetime.utcnow().isoformat()),
                    sale_row.get("total", 0),
                    str(xml_path),
                    str(pdf_path),
                    uso_cfdi,
                    forma_pago,
                    metodo_pago,
                ),
            )
        self.register_audit(user_id=sale_row.get("user_id"), action="issue_cfdi", payload={"sale_id": sale_id, "uuid": resp.get("uuid")})
        return {"uuid": resp.get("uuid"), "xml_path": str(xml_path), "pdf_path": str(pdf_path)}

    def issue_cfdi_payment(self, cfdi_id: int, payments: list[dict[str, Any]]) -> dict[str, Any]:
        original = self.get_cfdi_by_id(cfdi_id)
        if not original:
            raise ValueError("CFDI original no encontrado")
        cfg = self.get_fiscal_config()
        xml = build_cfdi_pago_xml(dict(original), payments, cfg)
        pac = self._pac_client()
        resp = pac.timbrar_xml(xml)
        cfdi_dir = DATA_DIR / "cfdi"
        cfdi_dir.mkdir(parents=True, exist_ok=True)
        folio = self.get_next_folio()
        xml_path = cfdi_dir / f"P{folio}_{resp['uuid']}.xml"
        xml_path.write_text(resp.get("xml_timbrado", xml), encoding="utf-8")
        pdf_path = cfdi_dir / f"P{folio}_{resp['uuid']}.pdf"
        export_cfdi_pdf(
            {
                "uuid": resp.get("uuid"),
                "serie": cfg.get("serie_factura", "P"),
                "folio": folio.replace(cfg.get("serie_factura", "P"), ""),
                "fecha": resp.get("fecha_timbrado", datetime.utcnow().isoformat()),
                "totals": {"subtotal": 0, "tax": 0, "total": sum(float(p.get("amount", 0)) for p in payments)},
                "emitter": {"razon_social": cfg.get("razon_social_emisor", ""), "rfc": cfg.get("rfc_emisor", "")},
                "receiver": {"name": original.get("customer_name", "Publico en general"), "rfc": original.get("customer_rfc", "XAXX010101000")},
                "sello_sat": resp.get("sello_sat"),
                "cert_sat": resp.get("no_certificado_sat"),
            },
            [],
            resp.get("xml_timbrado", xml),
            pdf_path,
        )
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO cfdi_issued (sale_id, customer_id, uuid, serie, folio, fecha, total, xml_path, pdf_path, status, tipo_comprobante, uso_cfdi, forma_pago, metodo_pago, moneda)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'vigente', 'P', 'CP01', '99', 'PPD', 'MXN')
                """,
                (
                    original.get("sale_id"),
                    original.get("customer_id"),
                    resp.get("uuid"),
                    cfg.get("serie_factura", "P"),
                    folio.replace(cfg.get("serie_factura", "P"), ""),
                    resp.get("fecha_timbrado", datetime.utcnow().isoformat()),
                    sum(float(p.get("amount", 0)) for p in payments),
                    str(xml_path),
                    str(pdf_path),
                ),
            )
        return {"uuid": resp.get("uuid"), "xml_path": str(xml_path), "pdf_path": str(pdf_path)}

    def get_cfdi_by_id(self, cfdi_id: int) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            cur = conn.execute("SELECT * FROM cfdi_issued WHERE id = ?", (cfdi_id,))
            return cur.fetchone()

    def get_cfdi_for_sale(self, sale_id: int) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            cur = conn.execute(
                "SELECT * FROM cfdi_issued WHERE sale_id = ? AND status = 'vigente' ORDER BY id DESC LIMIT 1",
                (sale_id,),
            )
            return cur.fetchone()

    def list_cfdi(
        self,
        *,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        customer_id: Optional[int] = None,
        status: Optional[str] = None,
    ) -> list[sqlite3.Row]:
        query = """
        SELECT cfdi.*, c.first_name || ' ' || IFNULL(c.last_name,'') AS customer_name
        FROM cfdi_issued cfdi
        LEFT JOIN customers c ON c.id = cfdi.customer_id
        WHERE 1=1
        """
        params: list[Any] = []
        if date_from:
            query += " AND date(fecha) >= date(?)"
            params.append(date_from)
        if date_to:
            query += " AND date(fecha) <= date(?)"
            params.append(date_to)
        if customer_id:
            query += " AND customer_id = ?"
            params.append(customer_id)
        if status and status != "todos":
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY fecha DESC"
        with self.connect() as conn:
            return conn.execute(query, params).fetchall()

    def cancel_cfdi(self, cfdi_id: int, motivo: str, uuid_relacionado: Optional[str] = None) -> dict[str, Any]:
        cfdi = self.get_cfdi_by_id(cfdi_id)
        if not cfdi:
            raise ValueError("CFDI no encontrado")
        pac = self._pac_client()
        resp = pac.cancelar_cfdi(cfdi["uuid"], motivo, uuid_relacionado)
        with self.connect() as conn:
            conn.execute("UPDATE cfdi_issued SET status = 'cancelado' WHERE id = ?", (cfdi_id,))
            conn.execute(
                "INSERT INTO cfdi_cancelled (cfdi_id, fecha, motivo, uuid_relacionado) VALUES (?, ?, ?, ?)",
                (cfdi_id, datetime.utcnow().isoformat(), motivo, uuid_relacionado),
            )
        self.register_audit(user_id=STATE.user_id, action="cancel_cfdi", payload={"cfdi_id": cfdi_id, "motivo": motivo})
        return resp


STATE = AppState()

__all__ = [
    "POSCore",
    "STATE",
    "AppState",
    "DB_PATH",
    "CONFIG_FILE",
    "DATA_DIR",
    "APP_NAME",
]
