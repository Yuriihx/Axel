"""Production entry point. Start with: gunicorn --workers 1 --threads 4 wsgi:app."""

import hmac
import os
import re
import secrets
import threading
import time
from datetime import timedelta
from pathlib import Path

from flask import g, has_request_context, jsonify, redirect, render_template_string, request, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash


def _required_setting(name, minimum):
    value = os.environ.get(name, "")
    if len(value) < minimum or not value.strip():
        raise RuntimeError(f"Configure {name} com pelo menos {minimum} caracteres antes de iniciar.")
    return value


# Validate configuration BEFORE importing the original application, which opens its stores.
_admin_password = _required_setting("AXEL_ADMIN_PASSWORD", 7)
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
_dummy_password_hash = generate_password_hash(secrets.token_urlsafe(32))
_admin_user_key = _admin_user.casefold()
del _admin_password

from axel_ghl21 import app  # noqa: E402 -- configuration must be checked first
import axel_ghl21 as _axel


def _current_user_id():
    return getattr(g, "axel_user_id", "admin") if has_request_context() else "admin"

if _postgres_store is not None:
    _postgres_store.check()

    def _read_scoped_store(path):
        return _postgres_store.read(path, owner_id=_current_user_id())

    def _write_scoped_store(path, data):
        return _postgres_store.write(path, data, owner_id=_current_user_id())

    _axel.read_store = _read_scoped_store
    _axel.write_store = _write_scoped_store


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
    # Sessions created by the previous single-user AXEL version belong to its
    # configured owner, so they keep access to the existing saved data.
    if not isinstance(session.get("axel_user_id"), str) or not session.get("axel_user_id"):
        session["axel_user_id"] = "admin"
        session["axel_username"] = _admin_user
    return True


_USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,31}$")


def _username_key(value):
    username = str(value or "").strip()
    if not _USERNAME_RE.fullmatch(username):
        return ""
    return username.casefold()


def _start_user_session(user_id, username):
    session.clear()
    session.permanent = True
    session["axel_authenticated"] = True
    session["axel_logged_in_at"] = time.time()
    session["axel_user_id"] = user_id
    session["axel_username"] = username
    _csrf_token()


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
    return render_template_string(_LOGIN_PAGE, error=message, csrf_token=_csrf_token(),
                                  username=request.form.get("username", "")), status


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
    if request.endpoint in {"hosting_login", "hosting_signup", "hosting_healthz"}:
        return None
    if not _authenticated():
        if request.path.startswith("/api/"):
            return jsonify(ok=False, error="Faça login para continuar.", msg="Faça login para continuar."), 401
        return redirect(url_for("hosting_login"))
    g.axel_user_id = session["axel_user_id"]
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
        return render_template_string(_LOGIN_PAGE, error="", csrf_token=_csrf_token(), username="")
    if not _same_origin() or not _valid_csrf():
        return _failure("Sessão do formulário inválida. Atualize a página e tente novamente.", 403)
    ip = request.remote_addr or "unknown"
    if _limited(ip):
        response = app.make_response((render_template_string(
            _SIGNUP_PAGE, error="Muitas tentativas. Aguarde 15 minutos para tentar novamente.",
            csrf_token=_csrf_token(), username=request.form.get("username", "")), 429))
        response.headers["Retry-After"] = str(_LOGIN_WINDOW)
        return response
    username = request.form.get("username", "")
    password = request.form.get("password", "")
    username_key = _username_key(username)
    user = None
    try:
        if username_key and hmac.compare_digest(username_key, _admin_user_key):
            candidate_hash = _password_hash
            user_id = "admin"
            display_name = _admin_user
        else:
            user = _postgres_store.find_user(username_key) if (_postgres_store is not None and username_key) else None
            candidate_hash = user["password_hash"] if user else _dummy_password_hash
            user_id = user["user_id"] if user else ""
            display_name = user["username"] if user else ""
        password_ok = check_password_hash(candidate_hash, password[:256])
    except OSError:
        return _failure("Não consegui consultar as contas agora. Tente novamente em instantes.", 503)
    username_ok = bool(username_key and (user_id or hmac.compare_digest(username_key, _admin_user_key)))
    if not (username_ok and password_ok):
        _record_failure(ip)
        return _failure("Usuário ou senha incorretos.", 401)
    with _login_lock:
        _login_failures.pop(ip, None)
    _start_user_session(user_id, display_name)
    return redirect(url_for("index"))


@app.route("/signup", methods=["GET", "POST"])
def hosting_signup():
    if _authenticated():
        return redirect(url_for("index"))
    if request.method == "GET":
        return render_template_string(_SIGNUP_PAGE, error="", csrf_token=_csrf_token(), username="")
    if not _same_origin() or not _valid_csrf():
        return render_template_string(_SIGNUP_PAGE,
                                      error="Sessão do formulário inválida. Atualize a página e tente novamente.",
                                      csrf_token=_csrf_token(), username=request.form.get("username", "")), 403
    if _postgres_store is None:
        return render_template_string(_SIGNUP_PAGE,
                                      error="Cadastro indisponível: o AXEL precisa do banco PostgreSQL.",
                                      csrf_token=_csrf_token(), username=request.form.get("username", "")), 503
    ip = request.remote_addr or "unknown"
    if _limited(ip):
        response, status = _failure("Muitas tentativas. Aguarde 15 minutos para tentar novamente.", 429)
        response = app.make_response((response, status))
        response.headers["Retry-After"] = str(_LOGIN_WINDOW)
        return response

    username = request.form.get("username", "").strip()
    username_key = _username_key(username)
    password = request.form.get("password", "")
    password_confirm = request.form.get("password_confirm", "")
    error = ""
    if not username_key:
        error = "Use um usuário de 3 a 32 caracteres: letras, números, ponto, hífen ou sublinhado."
    elif hmac.compare_digest(username_key, _admin_user_key):
        error = "Esse nome de usuário não está disponível."
    elif not 8 <= len(password) <= 128:
        error = "A senha precisa ter entre 8 e 128 caracteres."
    elif not hmac.compare_digest(password, password_confirm):
        error = "As senhas não conferem."
    if error:
        _record_failure(ip)
        return render_template_string(_SIGNUP_PAGE, error=error, csrf_token=_csrf_token(), username=username), 400

    user_id = secrets.token_hex(16)
    try:
        created = _postgres_store.create_user(user_id, username, username_key,
                                              generate_password_hash(password))
    except OSError:
        app.logger.exception("Falha ao criar conta AXEL")
        return render_template_string(_SIGNUP_PAGE,
                                      error="Não consegui salvar a conta agora. Tente novamente em instantes.",
                                      csrf_token=_csrf_token(), username=username), 503
    if not created:
        _record_failure(ip)
        return render_template_string(_SIGNUP_PAGE, error="Esse usuário já está cadastrado.",
                                      csrf_token=_csrf_token(), username=username), 409
    with _login_lock:
        _login_failures.pop(ip, None)
    _start_user_session(user_id, username)
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
    if request.endpoint in {"index", "hosting_login", "hosting_signup"} and response.status_code == 200 and response.mimetype == "text/html":
        html = response.get_data(as_text=True)
        response.set_data(html.replace("</body>", _CREATOR_WATERMARK + "</body>", 1))
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

_CREATOR_WATERMARK = """
<style>
.axel-creator-watermark{position:fixed;left:12px;bottom:3px;z-index:850;max-width:calc(100vw - 24px);color:#9bb7aa;opacity:.76;font:11px/1.4 system-ui,sans-serif;letter-spacing:.02em;text-shadow:0 1px 3px #000;pointer-events:none;user-select:none}
.axel-creator-watermark strong{font-weight:600}
@media(max-width:480px){.axel-creator-watermark{font-size:9px}}
</style>
<aside class="axel-creator-watermark" aria-label="Criador do sistema: Yuri Bibiano dos Santos">Criado por <strong>Yuri Bibiano dos Santos</strong></aside>
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
<label for="username">Usuário</label><input id="username" name="username" value="{{ username }}" autocomplete="username" maxlength="32" required>
<label for="password">Senha</label><input id="password" name="password" type="password" autocomplete="current-password" required>
<button type="submit">Entrar</button></form><p class="auth-link">Ainda não tem conta? <a href="/signup">Cadastre-se</a></p></main></body></html>"""

_SIGNUP_PAGE = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Criar conta · AXEL</title>
<style>
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;padding:24px;background:radial-gradient(ellipse at top,#173c30,#0e1614 65%);color:#e9f2ee;font:16px system-ui,sans-serif}
main{width:100%;max-width:410px;background:#141f1c;border:1px solid #22322d;border-radius:20px;padding:34px;box-shadow:0 18px 70px #0006}
h1{font-size:32px;letter-spacing:6px;margin:0 0 8px;color:#25d597}p{color:#8ba39a;margin:0 0 22px;line-height:1.5}label{display:block;font-size:14px;margin:18px 0 8px}
input{width:100%;border:1px solid #3b5047;border-radius:9px;background:#0e1614;color:#fff;padding:12px;font:inherit}input:focus{outline:2px solid #25d597;outline-offset:2px}
button{width:100%;margin-top:24px;border:0;border-radius:9px;background:#25d597;color:#09231b;padding:13px;font:700 16px system-ui;cursor:pointer}.error{border:1px solid #aa4a55;background:#49242e;color:#ffe4e5;border-radius:9px;padding:12px;font-size:14px;margin-bottom:18px}.auth-link{margin:20px 0 0;text-align:center;font-size:14px}.auth-link a{color:#25d597}
</style></head><body><main><h1>AXEL</h1><p>Crie sua conta. Suas subcontas e configurações ficarão só no seu AXEL.</p>
{% if error %}<div class="error" role="alert">{{ error }}</div>{% endif %}
<form method="post" action="/signup"><input type="hidden" name="csrf_token" value="{{ csrf_token }}">
<label for="username">Usuário</label><input id="username" name="username" value="{{ username }}" autocomplete="username" minlength="3" maxlength="32" required>
<label for="password">Senha</label><input id="password" name="password" type="password" autocomplete="new-password" minlength="8" maxlength="128" required>
<label for="password_confirm">Confirme a senha</label><input id="password_confirm" name="password_confirm" type="password" autocomplete="new-password" minlength="8" maxlength="128" required>
<button type="submit">Criar conta</button></form><p class="auth-link">Já tem conta? <a href="/login">Entrar</a></p></main></body></html>"""

