"""Offline SQL-contract checks. Live Neon connectivity is checked on deployment."""
import importlib
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from postgres_store import PostgresStore, STORE_NAMES

TEST_URL = "postgresql://test:discardable@db.example/test?sslmode=require"


class LocalSQL:
    """DB-API contract over SQLite, using the same statements as production."""
    def __init__(self, path):
        self.conn = sqlite3.connect(path)
    def __enter__(self):
        return self
    def execute(self, sql, args=()):
        return self.conn.execute(sql.replace("%s", "?"), args)
    def __exit__(self, kind, value, traceback):
        if kind is None:
            self.conn.commit()
        else:
            self.conn.rollback()
        self.conn.close()


class PostgresStorageTests(unittest.TestCase):
    def setUp(self):
        work = PROJECT.parents[1] / "work" / "hosting-tests"
        work.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=work)
        self.db = Path(self.temp.name) / "stores.sqlite"
        self.connect = lambda: LocalSQL(self.db)
        self.store = PostgresStore(TEST_URL, connect=self.connect)
        self.store.initialize()

    def tearDown(self):
        self.temp.cleanup()

    def test_all_stores_survive_new_instance_and_update(self):
        for name in STORE_NAMES:
            data = {"name": "Afétos", "nested": [1, {"body": "{{1}}"}], "empty": ""}
            self.store.write(name, data)
            reopened = PostgresStore(TEST_URL, connect=self.connect)
            reopened.check()
            self.assertEqual(reopened.read(name), data)
            reopened.write(name, {"updated": True})
            self.assertEqual(self.store.read(name), {"updated": True})

    def test_missing_row_returns_empty_but_corruption_raises(self):
        self.assertEqual(self.store.read("creds.json"), {})
        with self.connect() as conn:
            conn.execute("INSERT INTO axel_store(name,data) VALUES(%s,%s)", ("creds.json", "invalid JSON"))
        with self.assertRaises(OSError):
            self.store.read("creds.json")

    def test_failure_is_not_empty_and_does_not_leak_connection_secret(self):
        def failed():
            raise RuntimeError(TEST_URL)
        broken = PostgresStore(TEST_URL, connect=failed)
        for operation in (broken.check, broken.initialize,
                          lambda: broken.read("creds.json"), lambda: broken.write("creds.json", {})):
            with self.subTest(operation=operation), self.assertRaises(OSError) as caught:
                operation()
            self.assertNotIn(TEST_URL, str(caught.exception))

    def test_requires_postgres_ssl_and_known_records(self):
        for url in ("", "sqlite:///file", "postgresql://", TEST_URL.replace("require", "disable")):
            with self.subTest(url=url), self.assertRaises(RuntimeError):
                PostgresStore(url, connect=self.connect)
        with self.assertRaises(ValueError):
            self.store.read("other.json")
        with self.assertRaises(ValueError):
            self.store.write("bodies.json", [])

    def test_web_app_routes_use_database_store(self):
        modules = {name: sys.modules.pop(name, None) for name in ("wsgi", "axel_ghl21")}
        try:
            with patch.dict(os.environ, {
                "AXEL_ADMIN_PASSWORD": "discardable-test-password",
                "AXEL_SECRET_KEY": "discardable-test-secret-at-least-thirty-two-characters",
                "AXEL_DATA_DIR": self.temp.name,
                "AXEL_STORAGE_MODE": "postgres", "DATABASE_URL": TEST_URL,
                "RENDER": "false", "RENDER_EXTERNAL_HOSTNAME": "",
            }), patch.object(PostgresStore, "_connect", lambda _: self.connect()):
                hosted = importlib.import_module("wsgi")
                hosted.app.config["TESTING"] = True
                client = hosted.app.test_client()
                base = "https://axel-test.example"
                with client.session_transaction(base_url=base) as auth:
                    import time
                    auth["axel_authenticated"] = True
                    auth["axel_logged_in_at"] = time.time()
                response = client.post("/api/bodies/save", base_url=base, headers={"Origin": base},
                                       json={"name": "Banco", "text": "Corpo persistente"})
                self.assertTrue(response.get_json()["ok"])
                self.assertTrue(any(item["name"] == "Banco" for item in self.store.read("bodies.json")["items"]))
                self.assertFalse((Path(self.temp.name) / "bodies.json").exists())
        finally:
            for name, previous in modules.items():
                sys.modules.pop(name, None)
                if previous is not None:
                    sys.modules[name] = previous


if __name__ == "__main__":
    unittest.main()
