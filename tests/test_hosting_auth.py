"""Offline production-wrapper checks; never reads the user's saved credentials."""

import importlib
import os
import re
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from werkzeug.security import check_password_hash

PROJECT = Path(__file__).resolve().parents[1]
WORK = PROJECT.parents[1] / "work" / "hosting-tests"
WORK.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(PROJECT))
BASE = "https://axel-test.example"
PASSWORD = "test123"


def forbid_network(*args, **kwargs):
    raise AssertionError("External network is forbidden in hosting tests")


class HostingAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="isolated-", dir=WORK)
        cls.env = patch.dict(os.environ, {
            "AXEL_ADMIN_PASSWORD": PASSWORD,
            "AXEL_SECRET_KEY": "test-secret-at-least-thirty-two-characters-long",
            "AXEL_ADMIN_USER": "admin",
            "AXEL_DATA_DIR": cls.temp.name,
            "RENDER": "false",
            "RENDER_EXTERNAL_HOSTNAME": "",
        })
        cls.env.start()
        cls.network = patch("requests.sessions.Session.request", side_effect=forbid_network)
        cls.network.start()
        for name in ("wsgi", "axel_ghl21"):
            sys.modules.pop(name, None)
        cls.hosting = importlib.import_module("wsgi")
        cls.app = cls.hosting.app
        cls.app.config.update(TESTING=True)

    @classmethod
    def tearDownClass(cls):
        cls.network.stop()
        cls.env.stop()
        cls.temp.cleanup()

    def setUp(self):
        self.client = self.app.test_client()
        with self.hosting._login_lock:
            self.hosting._login_failures.clear()

    def csrf(self, client=None):
        response = (client or self.client).get("/login", base_url=BASE)
        self.assertEqual(response.status_code, 200)
        return re.search(r'name="csrf_token" value="([^"]+)"', response.get_data(as_text=True))[1]

    def login(self, password=PASSWORD, username="admin", client=None):
        client = client or self.client
        token = self.csrf(client)
        return client.post("/login", base_url=BASE, headers={"Origin": BASE}, data={
            "username": username, "password": password, "csrf_token": token,
        })

    def enable_isolated_postgres(self):
        class MemoryPostgresStore:
            def __init__(self):
                self.users = {}
                self.data = {}

            def find_user(self, username_key):
                return self.users.get(username_key)

            def create_user(self, user_id, username, username_key, password_hash):
                if username_key in self.users:
                    return False
                self.users[username_key] = {"user_id": user_id, "username": username,
                                            "password_hash": password_hash}
                return True

            def read(self, path, owner_id="admin"):
                return self.data.get((owner_id, Path(path).name), {}).copy()

            def write(self, path, data, owner_id="admin"):
                self.data[(owner_id, Path(path).name)] = data.copy()

        self.fake_store = MemoryPostgresStore()
        self.old_store = self.hosting._postgres_store
        self.old_read = self.hosting._axel.read_store
        self.old_write = self.hosting._axel.write_store
        self.hosting._postgres_store = self.fake_store
        self.hosting._axel.read_store = lambda path: self.fake_store.read(
            path, owner_id=self.hosting._current_user_id())
        self.hosting._axel.write_store = lambda path, data: self.fake_store.write(
            path, data, owner_id=self.hosting._current_user_id())
        self.addCleanup(self.restore_postgres)

    def restore_postgres(self):
        if hasattr(self, "old_store"):
            self.hosting._postgres_store = self.old_store
            self.hosting._axel.read_store = self.old_read
            self.hosting._axel.write_store = self.old_write

    def signup(self, username, password="new-password-123", client=None, confirm=None):
        client = client or self.client
        token = re.search(r'name="csrf_token" value="([^"]+)"',
                          client.get("/signup", base_url=BASE).get_data(as_text=True))[1]
        return client.post("/signup", base_url=BASE, headers={"Origin": BASE}, data={
            "username": username, "password": password,
            "password_confirm": password if confirm is None else confirm,
            "csrf_token": token,
        })

    def test_fail_closed_before_original_import(self):
        # Execute only this wrapper under an isolated name. Invalid config must fail
        # before any import of the original application or data-store initialization.
        source = (PROJECT / "wsgi.py").read_text(encoding="utf-8")
        real_import = __import__
        def guarded_import(name, *args, **kwargs):
            if name == "axel_ghl21":
                raise AssertionError("Imported original app before validating config")
            return real_import(name, *args, **kwargs)
        cases = [
            {"AXEL_ADMIN_PASSWORD": ""},
            {"AXEL_ADMIN_PASSWORD": "short"},
            {"AXEL_SECRET_KEY": "short"},
            {"AXEL_DATA_DIR": ""},
            {"AXEL_DATA_DIR": "relative-path"},
            {"AXEL_ADMIN_USER": " "},
            {"AXEL_STORAGE_MODE": "invalid"},
            {"AXEL_STORAGE_MODE": "postgres", "DATABASE_URL": ""},
        ]
        for overrides in cases:
            with self.subTest(overrides=list(overrides)), patch.dict(os.environ, overrides), patch("builtins.__import__", guarded_import):
                with self.assertRaises(RuntimeError):
                    exec(compile(source, str(PROJECT / "wsgi.py"), "exec"), {"__name__": "invalid_hosting_config"})

    def test_only_login_and_health_are_anonymous(self):
        self.assertEqual(self.client.get("/healthz", base_url=BASE).get_json(), {"ok": True})
        self.assertEqual(self.client.get("/login", base_url=BASE).status_code, 200)
        self.assertEqual(self.client.get("/signup", base_url=BASE).status_code, 200)
        # Exhaustively inspect the real application's registered routes, including APIs.
        for rule in self.app.url_map.iter_rules():
            if rule.endpoint in {"hosting_login", "hosting_signup", "hosting_healthz"}:
                continue
            method = "POST" if "POST" in rule.methods else "GET"
            with self.subTest(path=rule.rule, method=method):
                response = self.client.open(rule.rule, method=method, base_url=BASE)
                self.assertEqual(response.status_code, 401 if rule.rule.startswith("/api/") else 302)
                if response.status_code == 401:
                    self.assertFalse(response.get_json()["ok"])

    def test_login_requires_origin_and_csrf(self):
        token = self.csrf()
        data = {"username": "admin", "password": PASSWORD, "csrf_token": token}
        self.assertEqual(self.client.post("/login", base_url=BASE, data=data).status_code, 403)
        self.assertEqual(self.client.post("/login", base_url=BASE, headers={"Origin": "https://other.example"}, data=data).status_code, 403)
        self.assertEqual(self.client.post("/login", base_url=BASE, headers={"Origin": BASE}, data={**data, "csrf_token": "invalid"}).status_code, 403)
        anonymous = self.app.test_client()
        self.assertEqual(anonymous.post("/login", base_url=BASE, headers={"Origin": BASE}, data=data).status_code, 403)

    def test_login_cookie_and_logout(self):
        response = self.login()
        self.assertEqual(response.status_code, 302)
        cookie = response.headers["Set-Cookie"]
        for attribute in ("Secure", "HttpOnly", "SameSite=Lax", "Expires="):
            self.assertIn(attribute, cookie)
        self.assertEqual(self.client.get("/api/bodies", base_url=BASE).status_code, 200)
        home = self.client.get("/", base_url=BASE)
        self.assertEqual(home.status_code, 200)
        self.assertIn("Sair do AXEL", home.get_data(as_text=True))
        self.assertEqual(self.client.post("/logout", base_url=BASE, headers={"Origin": BASE}, data={"csrf_token": "invalid"}).status_code, 403)
        with self.client.session_transaction(base_url=BASE) as auth_session:
            token = auth_session["axel_csrf"]
        self.assertEqual(self.client.post("/logout", base_url=BASE, headers={"Origin": BASE}, data={"csrf_token": token}).status_code, 302)
        self.assertEqual(self.client.get("/api/bodies", base_url=BASE).status_code, 401)

    def test_mutations_require_same_origin(self):
        self.login()
        for origin in (None, "null", "https://other.example", BASE + "/"):
            with self.subTest(origin=origin):
                headers = {} if origin is None else {"Origin": origin}
                response = self.client.post("/api/bodies/save", base_url=BASE, headers=headers, json={"name": "origem", "text": "teste"})
                self.assertEqual(response.status_code, 403)
        response = self.client.post("/api/bodies/save", base_url=BASE, headers={"Origin": BASE}, json={"name": "origem", "text": "teste"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])

    def test_invalid_credentials_and_rate_limit(self):
        token = self.csrf()
        for attempt in range(5):
            response = self.client.post("/login", base_url=BASE, headers={"Origin": BASE}, data={"username": "admin", "password": "wrong-password", "csrf_token": token})
            self.assertEqual(response.status_code, 401, attempt)
            self.assertNotIn("wrong-password", response.get_data(as_text=True))
        response = self.client.post("/login", base_url=BASE, headers={"Origin": BASE}, data={"username": "admin", "password": PASSWORD, "csrf_token": token})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["Retry-After"], "900")
        with self.hosting._login_lock:
            self.hosting._login_failures["127.0.0.1"] = [time.monotonic() - 901] * 5
        self.assertEqual(self.login().status_code, 302)

    def test_wrong_username_and_absolute_session_expiry(self):
        self.assertEqual(self.login(username="another-user").status_code, 401)
        self.assertEqual(self.login().status_code, 302)
        with self.client.session_transaction(base_url=BASE) as auth_session:
            auth_session["axel_logged_in_at"] = time.time() - 8 * 60 * 60 - 1
        self.assertEqual(self.client.get("/api/bodies", base_url=BASE).status_code, 401)

    def test_signed_session_cannot_be_forged(self):
        self.client.set_cookie("axel_session", "fake.authentication.signature", domain="axel-test.example", secure=True)
        self.assertEqual(self.client.get("/api/bodies", base_url=BASE).status_code, 401)

    def test_headers_and_upload_limit(self):
        for path in ("/login", "/healthz", "/api/bodies"):
            response = self.client.get(path, base_url=BASE)
            self.assertIn("no-store", response.headers["Cache-Control"])
            self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
            self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertEqual(self.app.config["MAX_CONTENT_LENGTH"], 105 * 1024 * 1024)

    def test_data_and_migration_are_isolated(self):
        original = sys.modules["axel_ghl21"]
        self.assertEqual(Path(original.DATA_DIR).resolve(), Path(self.temp.name).resolve())
        self.assertEqual(os.environ["AXEL_DISABLE_LEGACY_MIGRATION"], "1")
        self.assertEqual(os.environ["AXEL_REQUIRE_DATA_DIR"], "1")
        self.assertEqual(original.MIGRATION_REPORT, [])
        self.assertEqual(original.migrate_legacy_files(), [])

    def test_trusted_host_rejects_unexpected_hosts(self):
        old = self.app.config.get("TRUSTED_HOSTS")
        self.app.config["TRUSTED_HOSTS"] = ["axel-test.example"]
        try:
            self.assertEqual(self.client.get("/healthz", base_url="https://other.example").status_code, 400)
            self.assertEqual(self.client.get("/healthz", base_url=BASE).status_code, 200)
        finally:
            self.app.config["TRUSTED_HOSTS"] = old

    def test_signup_hashes_password_and_logs_user_in(self):
        self.enable_isolated_postgres()
        response = self.signup("yuri.teste")
        self.assertEqual(response.status_code, 302)
        record = self.fake_store.users["yuri.teste"]
        self.assertNotEqual(record["password_hash"], "new-password-123")
        self.assertTrue(check_password_hash(record["password_hash"], "new-password-123"))
        with self.client.session_transaction(base_url=BASE) as auth_session:
            self.assertEqual(auth_session["axel_user_id"], record["user_id"])
            self.assertEqual(auth_session["axel_username"], "yuri.teste")
        self.assertEqual(self.client.get("/api/list-subaccounts", base_url=BASE).get_json()["subaccounts"], [])

    def test_users_get_separate_axel_data_and_admin_data_stays_intact(self):
        self.enable_isolated_postgres()
        first = self.app.test_client()
        self.signup("primeira", client=first)
        with first.session_transaction(base_url=BASE) as auth_session:
            first_id = auth_session["axel_user_id"]
        saved = first.post("/api/save-subaccount", base_url=BASE, headers={"Origin": BASE}, json={
            "label": "Loja primeira", "location_id": "location-first",
        })
        self.assertEqual(saved.status_code, 200)

        second = self.app.test_client()
        self.signup("segunda", client=second)
        self.assertEqual(second.get("/api/list-subaccounts", base_url=BASE).get_json()["subaccounts"], [])
        with second.session_transaction(base_url=BASE) as auth_session:
            second_id = auth_session["axel_user_id"]
        self.assertNotEqual(first_id, second_id)
        self.assertIn((first_id, "subaccounts.json"), self.fake_store.data)
        self.assertNotIn((second_id, "subaccounts.json"), self.fake_store.data)

        admin = self.app.test_client()
        self.assertEqual(self.login(client=admin).status_code, 302)
        self.assertEqual(admin.get("/api/list-subaccounts", base_url=BASE).get_json()["subaccounts"], [])

    def test_signup_rejects_bad_input_and_case_insensitive_duplicate(self):
        self.enable_isolated_postgres()
        self.assertEqual(self.signup("ab").status_code, 400)
        self.assertEqual(self.signup("gooduser", confirm="different-password").status_code, 400)
        first = self.app.test_client()
        self.assertEqual(self.signup("NomeUsuario", client=first).status_code, 302)
        duplicate = self.app.test_client()
        response = self.signup("nomeusuario", client=duplicate)
        self.assertEqual(response.status_code, 409)
        self.assertIn("já está cadastrado", response.get_data(as_text=True))

    def test_registered_user_can_log_in_with_saved_password(self):
        self.enable_isolated_postgres()
        self.assertEqual(self.signup("retorno").status_code, 302)
        client = self.app.test_client()
        response = self.login(username="RETORNO", password="new-password-123", client=client)
        self.assertEqual(response.status_code, 302)
        with client.session_transaction(base_url=BASE) as auth_session:
            self.assertEqual(auth_session["axel_username"], "retorno")

    def test_signup_requires_same_origin_and_csrf(self):
        self.enable_isolated_postgres()
        token = re.search(r'name="csrf_token" value="([^"]+)"',
                          self.client.get("/signup", base_url=BASE).get_data(as_text=True))[1]
        payload = {"username": "secureuser", "password": "new-password-123",
                   "password_confirm": "new-password-123", "csrf_token": token}
        self.assertEqual(self.client.post("/signup", base_url=BASE, data=payload).status_code, 403)
        self.assertEqual(self.client.post("/signup", base_url=BASE, headers={"Origin": BASE},
                                          data={**payload, "csrf_token": "wrong"}).status_code, 403)


if __name__ == "__main__":
    unittest.main(verbosity=2)

