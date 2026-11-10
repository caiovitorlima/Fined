from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from .. import db
from ..models import Lancamento, Meta, SessaoAutenticacao
from ..seguranca import entrar_como, login_obrigatorio
from .auth import email_em_uso, validar_email, validar_nome, validar_senha

bp = Blueprint("perfil", __name__, url_prefix="/perfil")


def _pagina(status=200, **extra):
    usuario = g.usuario
    contexto = {
        "dados": {"nome": usuario.nome, "email": usuario.email},
        "erros_dados": {},
        "erros_senha": {},
        "erro_excluir": None,
        "total_lancamentos": db.session.scalar(
            select(func.count(Lancamento.id)).where(Lancamento.usuario_id == usuario.id)
        ),
        "total_metas": db.session.scalar(
            select(func.count(Meta.id)).where(Meta.usuario_id == usuario.id)
        ),
    }
    contexto.update(extra)
    return render_template("app/perfil.html", **contexto), status


@bp.get("")
@login_obrigatorio
def inicio():
    return _pagina()


@bp.post("/dados")
@login_obrigatorio
def dados():
    nome = " ".join(request.form.get("nome", "").split())
    email = request.form.get("email", "").strip().lower()
    erros = {}
    erro = validar_nome(nome)
    if erro:
        erros["nome"] = erro
    erro = validar_email(email)
    if erro:
        erros["email"] = erro
    elif email_em_uso(email, ignorar_id=g.usuario.id):
        erros["email"] = "Esse e-mail já está em outra conta."
    elif email != g.usuario.email and not g.usuario.confere_senha(request.form.get("senha_atual", "")):
        erros["senha_atual"] = "Confirme sua senha atual para trocar o e-mail."
    if erros:
        return _pagina(400, dados={"nome": nome, "email": email}, erros_dados=erros)
    g.usuario.nome = nome
    g.usuario.email = email
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _pagina(400, dados={"nome": nome, "email": email},
                       erros_dados={"email": "Esse e-mail já está em outra conta."})
    flash("Dados atualizados.", "ok")
    return redirect(url_for(".inicio"))


@bp.post("/senha")
@login_obrigatorio
def senha():
    atual = request.form.get("senha_atual", "")
    nova = request.form.get("senha_nova", "")
    erros = {}
    if not g.usuario.confere_senha(atual):
        erros["senha_atual"] = "A senha atual não confere."
    erro = validar_senha(nova)
    if erro:
        erros["senha_nova"] = erro
    if erros:
        return _pagina(400, erros_senha=erros)
    g.usuario.definir_senha(nova)
    db.session.execute(delete(SessaoAutenticacao).where(
        SessaoAutenticacao.usuario_id == g.usuario.id
    ))
    entrar_como(g.usuario)
    flash("Senha alterada.", "ok")
    return redirect(url_for(".inicio"))


@bp.post("/excluir")
@login_obrigatorio
def excluir():
    if not g.usuario.confere_senha(request.form.get("senha", "")):
        return _pagina(400, erro_excluir="Senha incorreta. Nada foi apagado.")
    db.session.delete(g.usuario)
    db.session.commit()
    session.clear()
    flash("Sua conta e todos os seus dados foram apagados.", "info")
    return redirect(url_for("publico.inicio"))
