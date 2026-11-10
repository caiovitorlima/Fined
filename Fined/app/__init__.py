import os
import re
import secrets
from base64 import b64decode
from datetime import timedelta
from ipaddress import ip_address
from pathlib import Path

from flask import Flask, Response, render_template, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event, text
from sqlalchemy.engine import Engine, URL
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase
from werkzeug.exceptions import SecurityError
from werkzeug.middleware.proxy_fix import ProxyFix


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)


@event.listens_for(Engine, "connect")
def _ativar_chaves_estrangeiras(conexao, _registro):
    if type(conexao).__module__.startswith("sqlite3"):
        cursor = conexao.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def _url_banco(pasta):
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        return "sqlite:///" + (pasta / "trocado.db").as_posix()
    for prefixo in ("postgres://", "postgresql://"):
        if url.startswith(prefixo):
            return "postgresql+psycopg://" + url[len(prefixo):]
    return url


def _chave_secreta(pasta):
    chave = os.environ.get("SECRET_KEY", "").strip()
    if chave:
        return chave
    arquivo = pasta / "chave_secreta"
    if arquivo.exists():
        return arquivo.read_text(encoding="utf-8").strip()
    chave = secrets.token_hex(32)
    arquivo.write_text(chave, encoding="utf-8")
    return chave


def _segredo_producao(nome):
    arquivo = Path("/run/secrets") / nome
    try:
        segredo = arquivo.read_text(encoding="utf-8").strip()
    except OSError:
        raise RuntimeError(f"Monte o arquivo de segredo {nome}.") from None
    if not segredo:
        raise RuntimeError(f"Preencha o arquivo de segredo {nome}.")
    return segredo


def _config_producao(render):
    dominio = os.environ.get("FINED_DOMINIO", "").strip().lower()
    dominios = [dominio] if dominio else []
    if render:
        dominio_render = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip().lower()
        if not dominio_render.endswith(".onrender.com"):
            raise RuntimeError("O Render precisa fornecer o hostname público do serviço.")
        dominios.append(dominio_render)
    host = os.environ.get("FINED_DB_HOST", "").strip()
    projeto = os.environ.get("FINED_DB_PROJETO", "").strip()
    ca = Path("/certs/supabase-ca.crt")
    if not dominios or any(not re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+", nome) for nome in dominios):
        raise RuntimeError("Configure FINED_DOMINIO com o domínio público do site.")
    if not re.fullmatch(r"[a-z0-9-]+\.pooler\.supabase\.com", host):
        raise RuntimeError("Copie o host do Session pooler para FINED_DB_HOST.")
    if not re.fullmatch(r"[a-z0-9]{20}", projeto):
        raise RuntimeError("Preencha FINED_DB_PROJETO com a referência do projeto Supabase.")
    if not ca.is_file():
        raise RuntimeError("Monte o certificado do Supabase em /certs/supabase-ca.crt.")
    if render:
        try:
            chave = b64decode(os.environ.get("FINED_SECRET_KEY", ""), validate=True)
        except ValueError:
            chave = b""
        if len(chave) != 32:
            raise RuntimeError("Gere FINED_SECRET_KEY pelo Blueprint do Render.")
        senha = os.environ.get("FINED_DB_PASSWORD", "")
        if not senha:
            raise RuntimeError("Preencha FINED_DB_PASSWORD no painel do Render.")
    else:
        chave = _segredo_producao("secret_key")
        if not re.fullmatch(r"[a-f0-9]{64,128}", chave):
            raise RuntimeError("Gere a chave de sessão com openssl rand -hex 48.")
        senha = _segredo_producao("db_password")
    return {
        "SECRET_KEY": chave,
        "SQLALCHEMY_DATABASE_URI": URL.create(
            "postgresql+psycopg", username=f"fined_app.{projeto}",
            password=senha, host=host, port=5432,
            database="postgres",
            query={"sslmode": "verify-full", "sslrootcert": str(ca), "connect_timeout": "5"},
        ),
        "SQLALCHEMY_ENGINE_OPTIONS": {
            "pool_pre_ping": True, "pool_size": 2, "max_overflow": 1,
            "pool_timeout": 5, "hide_parameters": True,
            "execution_options": {"schema_translate_map": {None: "fined"}},
        },
        "TRUSTED_HOSTS": dominios,
        "SESSION_COOKIE_NAME": "__Host-fined",
        "SESSION_COOKIE_SECURE": True,
        "PERMANENT_SESSION_LIFETIME": timedelta(hours=12),
    }


def _verificar_banco_producao(conexao):
    papel, pode_criar, versao = conexao.execute(text("""
        SELECT current_user, has_schema_privilege(current_user, 'fined', 'CREATE'),
               (SELECT max(versao) FROM fined.versao_schema)
    """)).one()
    if papel != "fined_app" or pode_criar or versao != 1:
        raise RuntimeError("O banco precisa do esquema Fined versão 1 e do papel restrito fined_app.")


def create_app(config=None):
    app = Flask(__name__, instance_relative_config=True)
    render = os.environ.get("RENDER") == "true"
    producao = render or os.environ.get("FINED_PRODUCAO") == "1"

    app.config.update(
        FINED_PRODUCAO=producao,
        SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True},
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SEGURO") == "1",
        SESSION_REFRESH_EACH_REQUEST=False,
        PERMANENT_SESSION_LIFETIME=timedelta(days=14),
        MAX_CONTENT_LENGTH=64 * 1024,
    )
    if config:
        app.config.update(config)
    if producao:
        app.config.update(_config_producao(render))
        # O Caddy controla X-Forwarded-For. O Render identifica o cliente pelo Cloudflare.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=0 if render else 1, x_proto=1)
        if render:
            @app.before_request
            def _carregar_ip_render():
                ip = request.headers.get("CF-Connecting-IP", "")
                try:
                    request.remote_addr = str(ip_address(ip))
                except ValueError:
                    pass
    else:
        pasta = Path(app.instance_path)
        if not app.config.get("SECRET_KEY") or not app.config.get("SQLALCHEMY_DATABASE_URI"):
            pasta.mkdir(parents=True, exist_ok=True)
        if not app.config.get("SECRET_KEY"):
            app.config["SECRET_KEY"] = _chave_secreta(pasta)
        if not app.config.get("SQLALCHEMY_DATABASE_URI"):
            app.config["SQLALCHEMY_DATABASE_URI"] = _url_banco(pasta)

    db.init_app(app)

    from . import models
    from .filtros import registrar as registrar_filtros
    from .seguranca import registrar as registrar_seguranca
    from .rotas import aprender, auth, lancamentos, metas, painel, perfil, publico

    registrar_seguranca(app)
    registrar_filtros(app)

    for modulo in (publico, auth, painel, lancamentos, metas, aprender, perfil):
        app.register_blueprint(modulo.bp)

    @app.get("/healthz")
    def saude():
        try:
            with db.engine.connect() as conexao:
                if producao:
                    _verificar_banco_producao(conexao)
                else:
                    conexao.execute(text("SELECT 1"))
        except (SQLAlchemyError, RuntimeError):
            return Response("indisponível\n", status=503, mimetype="text/plain")
        return Response("ok\n", mimetype="text/plain")

    @app.errorhandler(400)
    def _erro_400(_erro):
        if isinstance(_erro, SecurityError):
            return Response("Endereço inválido.\n", status=400, mimetype="text/plain")
        return render_template(
            "erro.html",
            codigo=400,
            titulo="Não foi possível enviar o formulário",
            texto="Volte à página anterior, atualize a página e envie o formulário novamente.",
        ), 400

    @app.errorhandler(404)
    def _erro_404(_erro):
        return render_template(
            "erro.html",
            codigo=404,
            titulo="Página não encontrada",
            texto="Confira o endereço ou volte à página inicial.",
        ), 404

    @app.errorhandler(413)
    def _erro_413(_erro):
        return render_template(
            "erro.html",
            codigo=413,
            titulo="Limite de envio excedido",
            texto="Reduza os dados enviados e tente novamente.",
        ), 413

    @app.errorhandler(500)
    def _erro_500(_erro):
        db.session.rollback()
        return render_template(
            "erro.html",
            codigo=500,
            titulo="Erro interno",
            texto="Tente novamente em instantes.",
        ), 500

    with app.app_context():
        if producao:
            try:
                with db.engine.connect() as conexao:
                    _verificar_banco_producao(conexao)
            except SQLAlchemyError:
                raise RuntimeError("Falha ao conectar ao Supabase ou verificar o esquema Fined.") from None
        else:
            db.create_all()

    return app
