"""Isolated checks for durable account and per-user AXEL storage."""
import unittest
from pathlib import Path

from postgres_store import PostgresStore


class MemoryConnection:
    def __init__(self, database):
        self.database = database

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql, params=()):
        statement = " ".join(sql.split())
        if statement.startswith("CREATE TABLE"):
            self.database.schemas.append(statement)
            return Cursor(None)
        if statement.startswith("SELECT name FROM axel_store") or statement.startswith("SELECT owner_id FROM axel_user_store") or statement.startswith("SELECT user_id FROM axel_users"):
            return Cursor(None)
        if statement.startswith("SELECT data FROM axel_store"):
            return Cursor((self.database.legacy[params[0]],) if params[0] in self.database.legacy else None)
        if statement.startswith("SELECT data FROM axel_user_store"):
            key = (params[0], params[1])
            return Cursor((self.database.user_data[key],) if key in self.database.user_data else None)
        if statement.startswith("INSERT INTO axel_store"):
            self.database.legacy[params[0]] = params[1]
            return Cursor(None)
        if statement.startswith("INSERT INTO axel_user_store"):
            self.database.user_data[(params[0], params[1])] = params[2]
            return Cursor(None)
        if statement.startswith("SELECT user_id, username, password_hash FROM axel_users"):
            return Cursor(self.database.users.get(params[0]))
        if statement.startswith("INSERT INTO axel_users"):
            if params[2] in self.database.users:
                return Cursor(None)
            self.database.users[params[2]] = (params[0], params[1], params[3])
            return Cursor((params[0],))
        raise AssertionError(f"Unexpected SQL: {statement}")


class Cursor:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class MemoryDatabase:
    def __init__(self):
        self.schemas = []
        self.legacy = {}
        self.user_data = {}
        self.users = {}

    def connect(self):
        return MemoryConnection(self)


class PostgresStoreTests(unittest.TestCase):
    def setUp(self):
        self.database = MemoryDatabase()
        self.store = PostgresStore("postgresql://localhost/axel?sslmode=require",
                                   connect=self.database.connect)

    def test_initialization_creates_legacy_user_and_tenant_tables(self):
        self.store.initialize()
        self.assertEqual(len(self.database.schemas), 3)
        self.assertTrue(any("axel_users" in sql for sql in self.database.schemas))
        self.assertTrue(any("axel_user_store" in sql for sql in self.database.schemas))
        self.store.check()

    def test_legacy_admin_data_is_kept_and_each_user_is_scoped(self):
        self.store.write("subaccounts.json", {"admin": {"label": "Admin"}})
        self.store.write("subaccounts.json", {"one": {"label": "One"}}, owner_id="user-1")
        self.store.write("subaccounts.json", {"two": {"label": "Two"}}, owner_id="user-2")
        self.assertEqual(self.store.read("subaccounts.json"), {"admin": {"label": "Admin"}})
        self.assertEqual(self.store.read("subaccounts.json", owner_id="user-1"), {"one": {"label": "One"}})
        self.assertEqual(self.store.read("subaccounts.json", owner_id="user-2"), {"two": {"label": "Two"}})
        self.assertEqual(self.store.read("creds.json", owner_id="user-1"), {})

    def test_user_records_store_hash_and_enforce_unique_normalized_username(self):
        self.assertTrue(self.store.create_user("user-1", "LojaTeste", "lojateste", "hash-only"))
        self.assertFalse(self.store.create_user("user-2", "lojateste", "lojateste", "other-hash"))
        self.assertEqual(self.store.find_user("lojateste"), {
            "user_id": "user-1", "username": "LojaTeste", "password_hash": "hash-only",
        })
        self.assertIsNone(self.store.find_user("missing"))

    def test_invalid_store_names_and_payload_types_are_rejected(self):
        with self.assertRaises(ValueError):
            self.store.read(Path("outside.txt"))
        with self.assertRaises(ValueError):
            self.store.write("creds.json", ["not", "an", "object"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

