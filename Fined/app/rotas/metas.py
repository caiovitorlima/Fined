from datetime import date

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .. import db
from ..dinheiro import MAXIMO_CENTAVOS, ler_valor, para_campo
from ..financas import metas_do_usuario, texto_prazo
from ..models import Contribuicao, Meta
from ..seguranca import login_obrigatorio
from .lancamentos import ler_data

bp = Blueprint("metas", __name__, url_prefix="/metas")


def buscar(id_):
    meta = db.session.get(Meta, id_)
    if meta is None or meta.usuario_id != g.usuario.id:
        abort(404)
    return meta


def ler_formulario(form, criando, hoje):
    erros = {}
    nome = " ".join(form.get("nome", "").split())
    if not nome:
        erros["nome"] = "Informe o nome da meta."
    elif "\0" in nome:
        erros["nome"] = "Informe um nome válido."
    elif len(nome) > 60:
        erros["nome"] = "Use no máximo 60 caracteres."
    alvo = None
    try:
        alvo = ler_valor(form.get("valor_alvo"))
    except ValueError as erro:
        erros["valor_alvo"] = str(erro)
    prazo = ler_data(form.get("prazo"))
    if prazo is None:
        erros["prazo"] = "Informe uma data válida."
    elif criando and prazo < hoje:
        erros["prazo"] = "O prazo precisa ser hoje ou depois."
    inicial = 0
    if criando and form.get("guardado", "").strip():
        try:
            inicial = ler_valor(form.get("guardado"))
        except ValueError as erro:
            erros["guardado"] = str(erro)
    campos = {
        "nome": nome,
        "valor_alvo": form.get("valor_alvo", ""),
        "prazo": form.get("prazo", ""),
        "guardado": form.get("guardado", ""),
    }
    dados = {"nome": nome, "valor_alvo_centavos": alvo, "prazo": prazo}
    return campos, dados, inicial, erros


@bp.get("")
@login_obrigatorio
def lista():
    metas = metas_do_usuario(g.usuario.id)
    ativas = [meta for meta in metas if not meta.concluida]
    batidas = [meta for meta in metas if meta.concluida]
    return render_template(
        "app/metas/lista.html",
        ativas=ativas,
        batidas=batidas,
        total_guardado=sum(meta.guardado for meta in metas),
        texto_prazo=texto_prazo,
    )


@bp.route("/nova", methods=["GET", "POST"])
@login_obrigatorio
def nova():
    hoje = date.today()
    erros = {}
    if request.method == "POST":
        campos, dados, inicial, erros = ler_formulario(request.form, True, hoje)
        if not erros:
            meta = Meta(usuario_id=g.usuario.id, **dados)
            if inicial:
                meta.contribuicoes.append(Contribuicao(valor_centavos=inicial, data=hoje))
            db.session.add(meta)
            db.session.commit()
            flash("Meta criada.", "ok")
            return redirect(url_for(".detalhe", id_=meta.id))
    else:
        nome = " ".join(request.args.get("nome", "").split())[:60]
        valor = ""
        try:
            valor = para_campo(ler_valor(request.args.get("valor")))
        except ValueError:
            pass
        prazo = ler_data(request.args.get("prazo"))
        campos = {
            "nome": nome,
            "valor_alvo": valor,
            "prazo": prazo.isoformat() if prazo and prazo >= hoje else "",
            "guardado": "",
        }
    return render_template("app/metas/form.html", campos=campos, erros=erros, meta=None), 400 if erros else 200


@bp.get("/<int:id_>")
@login_obrigatorio
def detalhe(id_, erros=None, campos=None, status=200):
    meta = buscar(id_)
    hoje = date.today()
    return render_template(
        "app/metas/detalhe.html",
        meta=meta,
        texto_prazo=texto_prazo,
        sugestao=meta.sugestao_mensal(hoje),
        erros=erros or {},
        campos=campos or {"valor": "", "data": hoje.isoformat()},
    ), status


@bp.post("/<int:id_>/guardar")
@login_obrigatorio
def guardar(id_):
    meta = buscar(id_)
    hoje = date.today()
    erros = {}
    valor = None
    try:
        valor = ler_valor(request.form.get("valor"))
    except ValueError as erro:
        erros["valor"] = str(erro)
    data = ler_data(request.form.get("data"))
    if data is None:
        erros["data"] = "Informe uma data válida."
    elif data > hoje:
        erros["data"] = "A data não pode estar no futuro."
    if valor is not None and meta.guardado + valor > MAXIMO_CENTAVOS:
        erros["valor"] = "O valor excede o limite permitido."
    if erros:
        campos = {"valor": request.form.get("valor", ""), "data": request.form.get("data", "")}
        return detalhe(id_, erros=erros, campos=campos, status=400)
    estava_concluida = meta.concluida
    meta.contribuicoes.append(Contribuicao(valor_centavos=valor, data=data))
    db.session.commit()
    if meta.concluida and not estava_concluida:
        flash("Contribuição registrada. Meta concluída.", "ok")
    else:
        flash("Contribuição registrada.", "ok")
    return redirect(url_for(".detalhe", id_=meta.id))


@bp.post("/<int:id_>/contribuicoes/<int:contribuicao_id>/excluir")
@login_obrigatorio
def excluir_contribuicao(id_, contribuicao_id):
    meta = buscar(id_)
    contribuicao = db.session.get(Contribuicao, contribuicao_id)
    if contribuicao is None or contribuicao.meta_id != meta.id:
        abort(404)
    db.session.delete(contribuicao)
    db.session.commit()
    flash("Registro removido da meta.", "info")
    return redirect(url_for(".detalhe", id_=meta.id))


@bp.route("/<int:id_>/editar", methods=["GET", "POST"])
@login_obrigatorio
def editar(id_):
    meta = buscar(id_)
    erros = {}
    if request.method == "POST":
        campos, dados, _, erros = ler_formulario(request.form, False, date.today())
        if not erros:
            for chave, valor in dados.items():
                setattr(meta, chave, valor)
            db.session.commit()
            flash("Meta atualizada.", "ok")
            return redirect(url_for(".detalhe", id_=meta.id))
    else:
        campos = {
            "nome": meta.nome,
            "valor_alvo": para_campo(meta.valor_alvo_centavos),
            "prazo": meta.prazo.isoformat(),
            "guardado": "",
        }
    return render_template("app/metas/form.html", campos=campos, erros=erros, meta=meta), 400 if erros else 200


@bp.post("/<int:id_>/excluir")
@login_obrigatorio
def excluir(id_):
    meta = buscar(id_)
    db.session.delete(meta)
    db.session.commit()
    flash("Meta excluída.", "info")
    return redirect(url_for(".lista"))
