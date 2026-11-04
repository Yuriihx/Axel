"""Durable storage for the original AXEL stores; no local credential files."""
import json
import os
from urllib.parse import parse_qs, urlsplit

SCHEMA_SQL = """CREATE TABLE IF NOT EXISTS axel_store (
    name TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
)"""
USER_STORE_SQL = """CREATE TABLE IF NOT EXISTS axel_user_store (
    owner_id TEXT NOT NULL,
    name TEXT NOT NULL,
    data TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (owner_id, name)
)"""
USERS_SQL = """CREATE TABLE IF NOT EXISTS axel_users (
    user_id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    username_key TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
)"""
STORE_NAMES = frozenset({"creds.json", "subaccounts.json", "presets.json", "meta.json", "bodies.json", "company_presets.json"})


class PostgresStore:
    def __init__(self, database_url, connect=None):
        try:
            parsed = urlsplit(database_url)
            mode = parse_qs(parsed.query).get("sslmode", ["require"])[-1]
            valid = parsed.scheme in {"postgres", "postgresql"} and bool(parsed.hostname)
        except (ValueError, TypeError):
            valid, mode = False, ""
        if not valid or mode not in {"require", "verify-ca", "verify-full"}:
            raise RuntimeError("Configure DATABASE_URL PostgreSQL com conexão SSL obrigatória.")
        self._database_url = database_url
        self._sslmode = mode
        self._connector = connect

    def _connect(self):
        if self._connector is not None:
            return self._connector()
        import psycopg
        return psycopg.connect(self._database_url, connect_timeout=15, sslmode=self._sslmode)

    @staticmethod
    def _name(path):
        name = os.path.basename(os.fspath(path))
        if name not in STORE_NAMES:
            raise ValueError("Armazenamento solicitado não é um registro do AXEL.")
        return name

    def initialize(self):
        try:
            with self._connect() as conn:
                conn.execute(SCHEMA_SQL)
                conn.execute(USER_STORE_SQL)
                conn.execute(USERS_SQL)
        except Exception:
            raise OSError("Não foi possível preparar o banco de dados do AXEL.") from None

    def check(self):
        try:
            with self._connect() as conn:
                conn.execute("SELECT name FROM axel_store LIMIT 1").fetchone()
                conn.execute("SELECT owner_id FROM axel_user_store LIMIT 1").fetchone()
                conn.execute("SELECT user_id FROM axel_users LIMIT 1").fetchone()
        except Exception:
            raise OSError("O banco de dados do AXEL não está disponível.") from None

    def read(self, path, owner_id="admin"):
        name = self._name(path)
        try:
            with self._connect() as conn:
                if owner_id == "admin":
                    row = conn.execute("SELECT data FROM axel_store WHERE name = %s", (name,)).fetchone()
                else:
                    row = conn.execute("SELECT data FROM axel_user_store WHERE owner_id = %s AND name = %s",
                                       (owner_id, name)).fetchone()
            if row is None:
                return {}
            value = json.loads(row[0])
            if not isinstance(value, dict):
                raise ValueError("Invalid record")
            return value
        except Exception:
            # An unavailable DB must never be mistaken for an empty configuration.
            raise OSError("Não foi possível ler os dados salvos do AXEL.") from None

    def write(self, path, data, owner_id="admin"):
        name = self._name(path)
        if not isinstance(data, dict):
            raise ValueError("Os dados salvos devem ser um objeto JSON.")
        encoded = json.dumps(data, ensure_ascii=False, allow_nan=False)
        try:
            with self._connect() as conn:
                if owner_id == "admin":
                    conn.execute(
                        "INSERT INTO axel_store (name, data) VALUES (%s, %s) "
                        "ON CONFLICT (name) DO UPDATE SET data = EXCLUDED.data, updated_at = CURRENT_TIMESTAMP",
                        (name, encoded),
                    )
                else:
                    conn.execute(
                        "INSERT INTO axel_user_store (owner_id, name, data) VALUES (%s, %s, %s) "
                        "ON CONFLICT (owner_id, name) DO UPDATE SET data = EXCLUDED.data, updated_at = CURRENT_TIMESTAMP",
                        (owner_id, name, encoded),
                    )
        except Exception:
            raise OSError("Não foi possível salvar os dados do AXEL.") from None

    def find_user(self, username_key):
        if not username_key:
            return None
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT user_id, username, password_hash FROM axel_users WHERE username_key = %s",
                    (username_key,),
                ).fetchone()
            if row is None:
                return None
            return {"user_id": row[0], "username": row[1], "password_hash": row[2]}
        except Exception:
            raise OSError("Não foi possível consultar a conta do AXEL.") from None

    def create_user(self, user_id, username, username_key, password_hash):
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "INSERT INTO axel_users (user_id, username, username_key, password_hash) "
                    "VALUES (%s, %s, %s, %s) ON CONFLICT (username_key) DO NOTHING RETURNING user_id",
                    (user_id, username, username_key, password_hash),
                ).fetchone()
            return row is not None
        except Exception:
            raise OSError("Não foi possível criar a conta do AXEL.") from None

