import csv
import unicodedata
from datetime import date
from io import StringIO
from itertools import groupby

from flask import Blueprint, Response, abort, flash, g, redirect, render_template, request, url_for

from .. import db
from ..categorias import CATEGORIAS, DESPESA, RECEITA, TIPOS, existe, rotulo
from ..dinheiro import ler_valor, para_campo
from ..financas import chave_mes, lancamentos_do_mes, ler_mes, navegacao_mes, resumir
from ..models import Lancamento
from ..seguranca import login_obrigatorio

bp = Blueprint("lancamentos", __name__, url_prefix="/lancamentos")


def ler_data(texto):
    try:
        valor = date.fromisoformat((texto or "").strip())
    except ValueError:
        return None
    if not 2000 <= valor.year <= 2100:
        return None
    return valor


def ler_formulario(form):
    erros = {}
    tipo = form.get("tipo", "")
    if tipo not in TIPOS:
        erros["tipo"] = "Escolha receita ou despesa."
        tipo = DESPESA
    categoria = form.get(f"categoria_{tipo}", "")
    if not existe(tipo, categoria):
        erros["categoria"] = "Escolha uma categoria."
    valor = None
    try:
        valor = ler_valor(form.get("valor"))
    except ValueError as erro:
        erros["valor"] = str(erro)
    data = ler_data(form.get("data"))
    if data is None:
        erros["data"] = "Informe uma data válida."
    descricao = " ".join(form.get("descricao", "").split())
    if "\0" in descricao:
        erros["descricao"] = "Informe uma descrição válida."
    elif len(descricao) > 120:
        erros["descricao"] = "Use no máximo 120 caracteres."
    campos = {
        "tipo": tipo,
        "categoria": categoria,
        "valor": form.get("valor", ""),
        "data": form.get("data", ""),
        "descricao": descricao,
    }
    dados = {
        "tipo": tipo,
        "categoria": categoria,
        "valor_centavos": valor,
        "data": data,
        "descricao": descricao or None,
    }
    return campos, dados, erros


def buscar(id_):
    lancamento = db.session.get(Lancamento, id_)
    if lancamento is None or lancamento.usuario_id != g.usuario.id:
        abort(404)
    return lancamento


CATEGORIAS_FILTRO = dict(sorted(
    ((chave, nome) for itens in CATEGORIAS.values() for chave, nome, _ in itens),
    key=lambda item: item[1].casefold(),
))


def normalizar_busca(texto):
    texto = unicodedata.normalize("NFD", texto.casefold())
    return "".join(letra for letra in texto if not unicodedata.combining(letra))


def extrato_do_mes():
    hoje = date.today()
    ano, mes = ler_mes(request.args.get("mes"), hoje)
    nav = navegacao_mes(ano, mes, hoje)
    tipo = request.args.get("tipo", "")
    categoria = request.args.get("categoria", "")
    busca = request.args.get("q", "").strip()[:120]
    filtros = {
        "tipo": tipo if tipo in TIPOS else "",
        "categoria": categoria if categoria in CATEGORIAS_FILTRO else "",
        "q": busca,
    }
    busca_normalizada = normalizar_busca(busca)
    do_mes = lancamentos_do_mes(g.usuario.id, ano, mes)
    visiveis = [
        item for item in do_mes
        if (not filtros["tipo"] or item.tipo == filtros["tipo"])
        and (not filtros["categoria"] or item.categoria == filtros["categoria"])
        and busca_normalizada in normalizar_busca(
            f"{item.descricao or ''} {rotulo(item.tipo, item.categoria)}"
        )
    ]
    return hoje, nav, filtros, do_mes, visiveis


@bp.get("")
@login_obrigatorio
def lista():
    hoje, nav, filtros, do_mes, visiveis = extrato_do_mes()
    dias = [
        {"data": data, "itens": list(itens)}
        for data, itens in groupby(visiveis, key=lambda item: item.data)
    ]
    for dia in dias:
        dia["total"] = sum(item.valor_com_sinal for item in dia["itens"])
    return render_template(
        "app/lancamentos/lista.html",
        nav=nav,
        filtros=filtros,
        categorias_filtro=CATEGORIAS_FILTRO,
        dias=dias,
        resumo=resumir(do_mes),
        quantidade=len(visiveis),
        hoje=hoje,
    )


def texto_csv(texto):
    return "'" + texto if texto.lstrip().startswith(("=", "+", "-", "@")) else texto


@bp.get("/exportar.csv")
@login_obrigatorio
def exportar():
    _, nav, _, _, visiveis = extrato_do_mes()
    arquivo = StringIO(newline="")
    arquivo.write("\ufeff")
    csv_saida = csv.writer(arquivo, delimiter=";")
    csv_saida.writerow(("Data", "Tipo", "Categoria", "Descrição", "Valor (R$)"))
    for item in visiveis:
        sinal = "-" if item.tipo == DESPESA else ""
        reais, centavos = divmod(item.valor_centavos, 100)
        csv_saida.writerow((
            item.data.strftime("%d/%m/%Y"),
            "Receita" if item.tipo == RECEITA else "Despesa",
            texto_csv(rotulo(item.tipo, item.categoria)),
            texto_csv(item.descricao or ""),
            f"{sinal}{reais},{centavos:02d}",
        ))
    return Response(
        arquivo.getvalue(),
        content_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="fined-{nav["chave"]}.csv"',
            "Cache-Control": "no-store",
        },
    )


@bp.route("/novo", methods=["GET", "POST"])
@login_obrigatorio
def novo():
    erros = {}
    if request.method == "POST":
        campos, dados, erros = ler_formulario(request.form)
        if not erros:
            lancamento = Lancamento(usuario_id=g.usuario.id, **dados)
            db.session.add(lancamento)
            db.session.commit()
            palavra = "Receita" if lancamento.tipo == RECEITA else "Despesa"
            flash(f"{palavra} registrada.", "ok")
            if "continuar" in request.form:
                return redirect(url_for(".novo", tipo=lancamento.tipo, data=lancamento.data.isoformat()))
            return redirect(url_for(".lista", mes=chave_mes(lancamento.data.year, lancamento.data.month)))
    else:
        tipo = request.args.get("tipo")
        data = ler_data(request.args.get("data")) or date.today()
        campos = {
            "tipo": tipo if tipo in TIPOS else DESPESA,
            "categoria": "",
            "valor": "",
            "data": data.isoformat(),
            "descricao": "",
        }
    return render_template(
        "app/lancamentos/form.html", campos=campos, erros=erros, lancamento=None
    ), 400 if erros else 200


@bp.route("/<int:id_>/editar", methods=["GET", "POST"])
@login_obrigatorio
def editar(id_):
    lancamento = buscar(id_)
    erros = {}
    if request.method == "POST":
        campos, dados, erros = ler_formulario(request.form)
        if not erros:
            for chave, valor in dados.items():
                setattr(lancamento, chave, valor)
            db.session.commit()
            flash("Lançamento atualizado.", "ok")
            return redirect(url_for(".lista", mes=chave_mes(lancamento.data.year, lancamento.data.month)))
    else:
        campos = {
            "tipo": lancamento.tipo,
            "categoria": lancamento.categoria,
            "valor": para_campo(lancamento.valor_centavos),
            "data": lancamento.data.isoformat(),
            "descricao": lancamento.descricao or "",
        }
    return render_template(
        "app/lancamentos/form.html", campos=campos, erros=erros, lancamento=lancamento
    ), 400 if erros else 200


@bp.post("/<int:id_>/excluir")
@login_obrigatorio
def excluir(id_):
    lancamento = buscar(id_)
    mes = chave_mes(lancamento.data.year, lancamento.data.month)
    db.session.delete(lancamento)
    db.session.commit()
    flash("Lançamento excluído.", "info")
    return redirect(url_for(".lista", mes=mes))
