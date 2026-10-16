"""Production entry point. Start with: gunicorn --workers 1 --threads 4 wsgi:app."""

import hmac
import os
import re
import secrets
import threading
import time
from datetime import timedelta
from pathlib import Path

from flask import jsonify, redirect, render_template_string, request, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash


def _required_setting(name, minimum):
    value = os.environ.get(name, "")
    if len(value) < minimum or not value.strip():
        raise RuntimeError(f"Configure {name} com pelo menos {minimum} caracteres antes de iniciar.")
    return value


# Validate configuration BEFORE importing the original application, which opens its stores.
_admin_password = _required_setting("AXEL_ADMIN_PASSWORD", 12)
_secret_key = _required_setting("AXEL_SECRET_KEY", 32)
_admin_user = os.environ.get("AXEL_ADMIN_USER", "admin").strip()
if not _admin_user:
    raise RuntimeError("AXEL_ADMIN_USER não pode estar vazio.")
_storage_mode = os.environ.get("AXEL_STORAGE_MODE", "files")
if _storage_mode not in {"files", "postgres"}:
    raise RuntimeError("AXEL_STORAGE_MODE deve ser files ou postgres.")
_postgres_store = None
if _storage_mode == "postgres":
    from postgres_store import PostgresStore
    _postgres_store = PostgresStore(os.environ.get("DATABASE_URL", ""))
_data_dir_text = os.environ.get("AXEL_DATA_DIR", "").strip()
if not _data_dir_text or not Path(_data_dir_text).is_absolute():
    raise RuntimeError("Configure AXEL_DATA_DIR com um caminho absoluto para a pasta de execução.")
_render_hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip()
if _render_hostname and not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", _render_hostname):
    raise RuntimeError("RENDER_EXTERNAL_HOSTNAME deve conter somente o nome do host.")

os.environ["AXEL_DISABLE_LEGACY_MIGRATION"] = "1"
os.environ["AXEL_REQUIRE_DATA_DIR"] = "1"
_password_hash = generate_password_hash(_admin_password)
del _admin_password

from axel_ghl21 import app  # noqa: E402 -- configuration must be checked first

if _postgres_store is not None:
    import axel_ghl21 as _axel
    _postgres_store.check()
    _axel.read_store = _postgres_store.read
    _axel.write_store = _postgres_store.write


app.config.update(
    SECRET_KEY=_secret_key,
    SESSION_COOKIE_NAME="axel_session",
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    SESSION_REFRESH_EACH_REQUEST=False,
    MAX_CONTENT_LENGTH=105 * 1024 * 1024,
)
del _secret_key
if _render_hostname:
    app.config["TRUSTED_HOSTS"] = [_render_hostname]
if os.environ.get("RENDER", "").lower() == "true" and _render_hostname:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=0, x_port=0, x_prefix=0)

_LOGIN_WINDOW = 15 * 60
_LOGIN_MAX_FAILURES = 5
_SESSION_SECONDS = 8 * 60 * 60
_login_failures = {}
_login_lock = threading.Lock()
_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _authenticated():
    if session.get("axel_authenticated") is not True:
        return False
    logged_in_at = session.get("axel_logged_in_at")
    if not isinstance(logged_in_at, (int, float)) or not 0 <= time.time() - logged_in_at < _SESSION_SECONDS:
        session.clear()
        return False
    return True


def _csrf_token():
    token = session.get("axel_csrf")
    if not isinstance(token, str) or len(token) < 32:
        token = secrets.token_urlsafe(32)
        session["axel_csrf"] = token
    return token


def _valid_csrf():
    expected = session.get("axel_csrf")
    supplied = request.form.get("csrf_token", "")
    return isinstance(expected, str) and bool(expected) and hmac.compare_digest(expected, supplied)


def _same_origin():
    return request.headers.get("Origin") == request.host_url.rstrip("/")


def _failure(message, status):
    if request.path.startswith("/api/"):
        return jsonify(ok=False, error=message, msg=message), status
    return render_template_string(_LOGIN_PAGE, error=message, csrf_token=_csrf_token(), username=_admin_user), status


def _limited(ip):
    now = time.monotonic()
    with _login_lock:
        # Pruning all expired addresses also bounds memory across normal traffic.
        for address, attempts in list(_login_failures.items()):
            recent = [stamp for stamp in attempts if now - stamp < _LOGIN_WINDOW]
            if recent:
                _login_failures[address] = recent
            else:
                del _login_failures[address]
        return len(_login_failures.get(ip, [])) >= _LOGIN_MAX_FAILURES


def _record_failure(ip):
    with _login_lock:
        _login_failures.setdefault(ip, []).append(time.monotonic())


@app.before_request
def hosting_require_authentication():
    if request.routing_exception is not None:
        return None
    if request.endpoint in {"hosting_login", "hosting_healthz"}:
        return None
    if not _authenticated():
        if request.path.startswith("/api/"):
            return jsonify(ok=False, error="Faça login para continuar.", msg="Faça login para continuar."), 401
        return redirect(url_for("hosting_login"))
    if request.method in _MUTATING_METHODS and not _same_origin():
        return _failure("Origem da solicitação inválida. Atualize a página e tente novamente.", 403)
    return None


@app.get("/healthz")
def hosting_healthz():
    return jsonify(ok=True)


@app.route("/login", methods=["GET", "POST"])
def hosting_login():
    if request.method == "GET":
        if _authenticated():
            return redirect(url_for("index"))
        return render_template_string(_LOGIN_PAGE, error="", csrf_token=_csrf_token(), username=_admin_user)
    if not _same_origin() or not _valid_csrf():
        return _failure("Sessão do formulário inválida. Atualize a página e tente novamente.", 403)
    ip = request.remote_addr or "unknown"
    if _limited(ip):
        response, status = _failure("Muitas tentativas. Aguarde 15 minutos para tentar novamente.", 429)
        response = app.make_response((response, status))
        response.headers["Retry-After"] = str(_LOGIN_WINDOW)
        return response
    username = request.form.get("username", "")
    password = request.form.get("password", "")
    # Check the hash for every candidate, including an incorrect username.
    password_ok = check_password_hash(_password_hash, password)
    username_ok = hmac.compare_digest(username.encode("utf-8"), _admin_user.encode("utf-8"))
    if not (username_ok and password_ok):
        _record_failure(ip)
        return _failure("Usuário ou senha incorretos.", 401)
    with _login_lock:
        _login_failures.pop(ip, None)
    session.clear()
    session.permanent = True
    session["axel_authenticated"] = True
    session["axel_logged_in_at"] = time.time()
    _csrf_token()
    return redirect(url_for("index"))


@app.post("/logout")
def hosting_logout():
    if not _valid_csrf():
        return _failure("Sessão do formulário inválida. Atualize a página e tente novamente.", 403)
    session.clear()
    return redirect(url_for("hosting_login"))


@app.after_request
def hosting_response_headers(response):
    if request.endpoint == "index" and response.status_code == 200 and _authenticated():
        logout = render_template_string(_LOGOUT_FORM, csrf_token=_csrf_token())
        html = response.get_data(as_text=True)
        response.set_data(html.replace("</header>", logout + "</header>", 1))
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


_LOGOUT_FORM = """
<form action="/logout" method="post" style="margin:0">
  <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
  <button type="submit" style="border:1px solid #22322d;border-radius:9px;padding:9px 15px;background:#141f1c;color:#e9f2ee;cursor:pointer;font:14px system-ui">Sair do AXEL</button>
</form>
"""

_LOGIN_PAGE = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Entrar · AXEL</title>
<style>
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;padding:24px;background:radial-gradient(ellipse at top,#173c30,#0e1614 65%);color:#e9f2ee;font:16px system-ui,sans-serif}
main{width:100%;max-width:410px;background:#141f1c;border:1px solid #22322d;border-radius:20px;padding:34px;box-shadow:0 18px 70px #0006}
h1{font-size:32px;letter-spacing:6px;margin:0 0 8px;color:#25d597}p{color:#8ba39a;margin:0 0 26px;line-height:1.5}label{display:block;font-size:14px;margin:18px 0 8px}
input{width:100%;border:1px solid #3b5047;border-radius:9px;background:#0e1614;color:#fff;padding:12px;font:inherit}input:focus{outline:2px solid #25d597;outline-offset:2px}
button{width:100%;margin-top:24px;border:0;border-radius:9px;background:#25d597;color:#09231b;padding:13px;font:700 16px system-ui;cursor:pointer}.error{border:1px solid #aa4a55;background:#49242e;color:#ffe4e5;border-radius:9px;padding:12px;font-size:14px;margin-bottom:18px}
</style></head><body><main><h1>AXEL</h1><p>Entre para gerenciar seus modelos.</p>
{% if error %}<div class="error" role="alert">{{ error }}</div>{% endif %}
<form method="post" action="/login"><input type="hidden" name="csrf_token" value="{{ csrf_token }}">
<label for="username">Usuário</label><input id="username" name="username" value="{{ username }}" autocomplete="username" maxlength="120" required>
<label for="password">Senha</label><input id="password" name="password" type="password" autocomplete="current-password" required>
<button type="submit">Entrar</button></form></main></body></html>"""
