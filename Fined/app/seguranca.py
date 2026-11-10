import hmac
import secrets
from functools import wraps
from hashlib import sha256
from urllib.parse import unquote, urlsplit

from flask import abort, current_app, g, redirect, request, session, url_for
from sqlalchemy import delete

from . import db
from .models import SessaoAutenticacao, Usuario, agora


def token_csrf():
    token = session.get("_csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf"] = token
    return token


def destino_seguro(alvo):
    if not alvo or not alvo.startswith("/") or alvo.startswith("//"):
        return None
    partes = urlsplit(alvo)
    caminho = unquote(partes.path)
    if partes.scheme or partes.netloc or caminho.startswith("//") or "\\" in caminho:
        return None
    if any(ord(caractere) < 32 or ord(caractere) == 127 for caractere in caminho):
        return None
    if any(ord(caractere) < 32 or ord(caractere) == 127 for caractere in alvo):
        return None
    return alvo


def _vinculo_senha(usuario):
    chave = current_app.secret_key
    if isinstance(chave, str):
        chave = chave.encode()
    return hmac.digest(chave, f"sessao:{usuario.id}:{usuario.senha_hash}".encode(), "sha256").hex()


def entrar_como(usuario):
    db.session.flush()
    token = secrets.token_urlsafe(32)
    instante = agora()
    db.session.execute(delete(SessaoAutenticacao).where(SessaoAutenticacao.expira_em <= instante))
    db.session.add(SessaoAutenticacao(
        token_hash=sha256(token.encode()).hexdigest(),
        usuario_id=usuario.id,
        expira_em=instante + current_app.permanent_session_lifetime,
    ))
    vinculo = _vinculo_senha(usuario)
    usuario_id = usuario.id
    db.session.commit()
    session.clear()
    session.permanent = True
    session["usuario_id"] = usuario_id
    session["vinculo_senha"] = vinculo
    session["token_sessao"] = token
    token_csrf()


def sair_da_sessao():
    token = session.get("token_sessao")
    if token:
        db.session.execute(delete(SessaoAutenticacao).where(
            SessaoAutenticacao.token_hash == sha256(token.encode()).hexdigest()
        ))
        db.session.commit()
    session.clear()


def login_obrigatorio(view):
    @wraps(view)
    def envolvida(*args, **kwargs):
        if g.usuario is None:
            destino = request.full_path.rstrip("?")
            return redirect(url_for("auth.entrar", next=destino))
        return view(*args, **kwargs)

    return envolvida


def registrar(app):
    @app.before_request
    def carregar_usuario():
        g.usuario = None
        if request.endpoint in ("static", "saude"):
            return
        usuario_id = session.get("usuario_id")
        if usuario_id is None:
            return
        token = session.get("token_sessao")
        registro = db.session.get(SessaoAutenticacao, sha256(token.encode()).hexdigest()) if token else None
        if registro is None or registro.usuario_id != usuario_id or registro.expira_em <= agora():
            session.clear()
            return
        usuario = db.session.get(Usuario, usuario_id)
        vinculo = session.get("vinculo_senha", "")
        if usuario is None or not hmac.compare_digest(vinculo, _vinculo_senha(usuario)):
            session.clear()
            return
        g.usuario = usuario

    @app.before_request
    def conferir_csrf():
        if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
            return
        enviado = request.form.get("_csrf", "").encode()
        esperado = session.get("_csrf", "").encode()
        if not enviado or not esperado or not hmac.compare_digest(enviado, esperado):
            abort(400)

    @app.context_processor
    def contexto():
        return {"csrf_token": token_csrf, "usuario": g.get("usuario")}

    @app.after_request
    def cabecalhos(resposta):
        resposta.headers.setdefault("X-Content-Type-Options", "nosniff")
        resposta.headers.setdefault("X-Frame-Options", "DENY")
        resposta.headers.setdefault("Referrer-Policy", "same-origin")
        if current_app.config.get("FINED_PRODUCAO"):
            resposta.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; object-src 'none'; base-uri 'none'; "
                "frame-ancestors 'none'; form-action 'self'",
            )
        if request.blueprint == "auth" or (g.get("usuario") is not None and request.endpoint != "static"):
            resposta.headers.setdefault("Cache-Control", "no-store")
        return resposta
