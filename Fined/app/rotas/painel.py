from datetime import date

from flask import Blueprint, g, render_template, request

from ..financas import (
    fatias_rosca,
    gerar_avisos,
    historico,
    lancamentos_do_mes,
    ler_mes,
    metas_do_usuario,
    navegacao_mes,
    resumir,
    texto_prazo,
)
from ..seguranca import login_obrigatorio

bp = Blueprint("painel", __name__)


@bp.get("/painel")
@login_obrigatorio
def inicio():
    hoje = date.today()
    ano, mes = ler_mes(request.args.get("mes"), hoje)
    lancamentos = lancamentos_do_mes(g.usuario.id, ano, mes)
    resumo = resumir(lancamentos)
    meses, _ = historico(g.usuario.id, ano, mes)
    metas = metas_do_usuario(g.usuario.id)
    return render_template(
        "app/painel.html",
        nav=navegacao_mes(ano, mes, hoje),
        resumo=resumo,
        fatias=fatias_rosca(resumo.categorias),
        meses=meses,
        metas=metas,
        avisos=gerar_avisos(resumo, metas, hoje),
        recentes=lancamentos[:5],
        texto_prazo=texto_prazo,
    )
