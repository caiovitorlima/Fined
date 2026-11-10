import re
from hashlib import sha256
from time import time

from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from sqlalchemy import case, delete, or_, select
from sqlalchemy.dialects.postgresql import insert as inserir_postgresql
from sqlalchemy.dialects.sqlite import insert as inserir_sqlite
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from .. import db
from ..models import LimiteAutenticacao, Usuario
from ..seguranca import destino_seguro, entrar_como, sair_da_sessao

bp = Blueprint("auth", __name__)

EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
SENHA_MINIMA = 15
SENHA_MAXIMA = 128
JANELA_TENTATIVAS = 15 * 60
_hash_falso = None


def validar_nome(nome):
    if len(nome) < 2:
        return "Escreva seu nome."
    if "\0" in nome:
        return "Informe um nome válido."
    if len(nome) > 80:
        return "Use no máximo 80 caracteres."
    return None


def validar_email(email):
    if len(email) > 160 or "\0" in email or not EMAIL.fullmatch(email):
        return "Informe um e-mail válido."
    return None


def validar_senha(senha):
    if len(senha) < SENHA_MINIMA:
        return f"A senha precisa ter pelo menos {SENHA_MINIMA} caracteres."
    if len(senha) > SENHA_MAXIMA:
        return f"Use no máximo {SENHA_MAXIMA} caracteres."
    return None


def email_em_uso(email, ignorar_id=None):
    consulta = select(Usuario.id).where(Usuario.email == email)
    if ignorar_id is not None:
        consulta = consulta.where(Usuario.id != ignorar_id)
    return db.session.scalar(consulta) is not None


def _conferir_sem_usuario(senha):
    global _hash_falso
    if _hash_falso is None:
        _hash_falso = generate_password_hash("senha-que-ninguem-usa")
    check_password_hash(_hash_falso, senha)


def _chave_limite(tipo, valor):
    return sha256(f"{tipo}:{valor}".encode()).hexdigest()


def _registrar_tentativas(*limites):
    agora = int(time())
    tabela = LimiteAutenticacao.__table__
    inserir = inserir_postgresql if db.engine.dialect.name == "postgresql" else inserir_sqlite
    expirado = tabela.c.expira_em <= agora
    db.session.execute(delete(tabela).where(expirado))
    for chave, maximo in limites:
        fim = agora + JANELA_TENTATIVAS
        consulta = inserir(tabela).values(chave=chave, total=1, expira_em=fim)
        consulta = consulta.on_conflict_do_update(
            index_elements=[tabela.c.chave],
            set_={
                "total": case((expirado, 1), else_=tabela.c.total + 1),
                "expira_em": case((expirado, fim), else_=tabela.c.expira_em),
            },
            where=or_(expirado, tabela.c.total < maximo),
        ).returning(tabela.c.expira_em)
        if db.session.scalar(consulta) is None:
            fim = db.session.scalar(select(tabela.c.expira_em).where(tabela.c.chave == chave))
            db.session.rollback()
            return max(1, fim - agora)
    db.session.commit()
    return 0


@bp.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    proximo = destino_seguro(request.form.get("next") if request.method == "POST" else request.args.get("next"))
    if g.usuario is not None:
        return redirect(proximo or url_for("painel.inicio"))
    campos, erros = {"nome": "", "email": ""}, {}
    if request.method == "POST":
        campos["nome"] = " ".join(request.form.get("nome", "").split())
        campos["email"] = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")
        for chave, erro in (
            ("nome", validar_nome(campos["nome"])),
            ("email", validar_email(campos["email"])),
            ("senha", validar_senha(senha)),
        ):
            if erro:
                erros[chave] = erro
        if "email" not in erros and email_em_uso(campos["email"]):
            erros["email"] = "Já existe uma conta com esse e-mail."
        if not erros:
            espera = _registrar_tentativas((_chave_limite("cadastro-ip", request.remote_addr), 10))
            if espera:
                return render_template(
                    "auth/cadastro.html", campos=campos, erros=erros, proximo=proximo,
                    erro="Muitas tentativas de cadastro. Aguarde alguns minutos e tente de novo.",
                ), 429, {"Retry-After": str(espera)}
            usuario = Usuario(nome=campos["nome"], email=campos["email"])
            usuario.definir_senha(senha)
            db.session.add(usuario)
            try:
                entrar_como(usuario)
            except IntegrityError:
                db.session.rollback()
                erros["email"] = "Já existe uma conta com esse e-mail."
            else:
                flash("Conta criada.", "ok")
                return redirect(proximo or url_for("painel.inicio"))
    return render_template("auth/cadastro.html", campos=campos, erros=erros, proximo=proximo), 400 if erros else 200


@bp.route("/entrar", methods=["GET", "POST"])
def entrar():
    proximo = destino_seguro(request.form.get("next") if request.method == "POST" else request.args.get("next"))
    if g.usuario is not None:
        return redirect(proximo or url_for("painel.inicio"))
    email, erro = "", None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")
        erro = "E-mail ou senha incorretos."
        if not validar_email(email) and 0 < len(senha) <= SENHA_MAXIMA:
            chave_conta = _chave_limite("login-email", email)
            espera = _registrar_tentativas(
                (_chave_limite("login-ip", request.remote_addr), 40),
                (chave_conta, 8),
            )
            if espera:
                return render_template(
                    "auth/entrar.html", email=email, proximo=proximo,
                    erro="Muitas tentativas de login. Aguarde alguns minutos e tente de novo.",
                ), 429, {"Retry-After": str(espera)}
            usuario = db.session.scalar(select(Usuario).where(Usuario.email == email))
            if usuario is None:
                _conferir_sem_usuario(senha)
            elif usuario.confere_senha(senha):
                db.session.execute(delete(LimiteAutenticacao).where(LimiteAutenticacao.chave == chave_conta))
                entrar_como(usuario)
                return redirect(proximo or url_for("painel.inicio"))
    return render_template("auth/entrar.html", email=email, erro=erro, proximo=proximo), 401 if erro else 200


@bp.post("/sair")
def sair():
    sair_da_sessao()
    flash("Você saiu da sua conta.", "info")
    return redirect(url_for("publico.inicio"))
