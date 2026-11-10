from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from . import db
from .categorias import DESPESA, RECEITA, cor, rotulo
from .dinheiro import brl
from .filtros import MESES_CURTOS, plural
from .models import Lancamento, Meta


def deslocar_mes(ano, mes, delta):
    indice = ano * 12 + (mes - 1) + delta
    return indice // 12, indice % 12 + 1


def chave_mes(ano, mes):
    return f"{ano:04d}-{mes:02d}"


def ler_mes(texto, hoje):
    if texto:
        try:
            ano_txt, mes_txt = texto.split("-")
            ano, mes = int(ano_txt), int(mes_txt)
        except ValueError:
            pass
        else:
            if 2000 <= ano <= 2100 and 1 <= mes <= 12:
                return ano, mes
    return hoje.year, hoje.month


def intervalo(ano, mes):
    seguinte_ano, seguinte_mes = deslocar_mes(ano, mes, 1)
    return date(ano, mes, 1), date(seguinte_ano, seguinte_mes, 1)


def navegacao_mes(ano, mes, hoje):
    anterior = deslocar_mes(ano, mes, -1)
    proximo = deslocar_mes(ano, mes, 1)
    return {
        "ano": ano,
        "mes": mes,
        "chave": chave_mes(ano, mes),
        "anterior": chave_mes(*anterior) if anterior[0] >= 2000 else None,
        "proximo": chave_mes(*proximo) if proximo[0] <= 2100 else None,
        "atual": (ano, mes) == (hoje.year, hoje.month),
        "chave_hoje": chave_mes(hoje.year, hoje.month),
    }


def lancamentos_do_mes(usuario_id, ano, mes, tipo=None):
    inicio, fim = intervalo(ano, mes)
    consulta = select(Lancamento).where(
        Lancamento.usuario_id == usuario_id,
        Lancamento.data >= inicio,
        Lancamento.data < fim,
    )
    if tipo:
        consulta = consulta.where(Lancamento.tipo == tipo)
    consulta = consulta.order_by(Lancamento.data.desc(), Lancamento.id.desc())
    return list(db.session.scalars(consulta))


@dataclass
class Resumo:
    receitas: int = 0
    despesas: int = 0
    qtd_receitas: int = 0
    qtd_despesas: int = 0
    categorias: list = field(default_factory=list)

    @property
    def resultado(self):
        return self.receitas - self.despesas

    @property
    def vazio(self):
        return self.qtd_receitas == 0 and self.qtd_despesas == 0


def resumir(lancamentos):
    resumo = Resumo()
    por_categoria = defaultdict(int)
    for item in lancamentos:
        if item.tipo == RECEITA:
            resumo.receitas += item.valor_centavos
            resumo.qtd_receitas += 1
        else:
            resumo.despesas += item.valor_centavos
            resumo.qtd_despesas += 1
            por_categoria[item.categoria] += item.valor_centavos
    ordenadas = sorted(por_categoria.items(), key=lambda par: (-par[1], par[0]))
    resumo.categorias = [
        {
            "chave": chave,
            "rotulo": rotulo(DESPESA, chave),
            "cor": cor(DESPESA, chave),
            "total": total,
            "fracao": total / resumo.despesas,
        }
        for chave, total in ordenadas
    ]
    return resumo


def fatias_rosca(categorias):
    fatias = []
    acumulado = 0.0
    folga = 0.9 if len(categorias) > 1 else 0.0
    for categoria in categorias:
        tamanho = categoria["fracao"] * 100
        arco = max(tamanho - folga, 0.05)
        fatias.append({
            "cor": categoria["cor"],
            "arco": arco,
            "resto": 100 - arco,
            "inicio": 25 - acumulado,
        })
        acumulado += tamanho
    return fatias


def historico(usuario_id, ano, mes, quantidade=6):
    primeiro_ano, primeiro_mes = deslocar_mes(ano, mes, -(quantidade - 1))
    inicio = date(primeiro_ano, primeiro_mes, 1)
    _, fim = intervalo(ano, mes)
    linhas = db.session.execute(
        select(Lancamento.data, Lancamento.tipo, Lancamento.valor_centavos).where(
            Lancamento.usuario_id == usuario_id,
            Lancamento.data >= inicio,
            Lancamento.data < fim,
        )
    ).all()
    totais = defaultdict(lambda: [0, 0])
    for data, tipo, valor in linhas:
        totais[(data.year, data.month)][0 if tipo == RECEITA else 1] += valor
    meses = []
    for passo in range(quantidade):
        a, m = deslocar_mes(primeiro_ano, primeiro_mes, passo)
        receitas, despesas = totais[(a, m)]
        meses.append({
            "ano": a,
            "mes": m,
            "chave": chave_mes(a, m),
            "rotulo": MESES_CURTOS[m - 1],
            "receitas": receitas,
            "despesas": despesas,
            "atual": (a, m) == (ano, mes),
        })
    maior = max(max(item["receitas"], item["despesas"]) for item in meses)
    for item in meses:
        item["altura_receitas"] = round(item["receitas"] / maior * 100, 2) if maior else 0
        item["altura_despesas"] = round(item["despesas"] / maior * 100, 2) if maior else 0
    return meses, maior


def metas_do_usuario(usuario_id):
    metas = list(
        db.session.scalars(
            select(Meta)
            .where(Meta.usuario_id == usuario_id)
            .options(selectinload(Meta.contribuicoes))
        )
    )
    metas.sort(key=lambda meta: (meta.concluida, meta.prazo, meta.id))
    return metas


def texto_prazo(meta, hoje):
    if meta.concluida:
        return "Meta concluída"
    dias = meta.dias_restantes(hoje)
    if dias < 0:
        return "O prazo já passou"
    if dias == 0:
        return "O prazo é hoje"
    return f"{'Falta' if dias == 1 else 'Faltam'} {plural(dias, 'dia', 'dias')}"


def gerar_avisos(resumo, metas, hoje):
    avisos = []
    if resumo.despesas > resumo.receitas:
        if resumo.receitas == 0:
            texto = (
                f"{brl(resumo.despesas)} em despesas e nenhuma entrada no mês."
            )
        else:
            texto = (
                f"Você gastou {brl(resumo.despesas - resumo.receitas)} a mais do que recebeu."
            )
        avisos.append({"tipo": "alerta", "titulo": "Despesas acima das receitas", "texto": texto})

    for meta in metas:
        if meta.concluida:
            continue
        dias = meta.dias_restantes(hoje)
        if dias < 0:
            avisos.append({
                "tipo": "atencao",
                "titulo": f"Prazo encerrado para “{meta.nome}”",
                "texto": f"Faltam {brl(meta.falta)}.",
                "meta_id": meta.id,
            })
        elif dias <= 30:
            quando = "hoje" if dias == 0 else ("em 1 dia" if dias == 1 else f"em {dias} dias")
            avisos.append({
                "tipo": "atencao",
                "titulo": f"“{meta.nome}” vence {quando}",
                "texto": f"Faltam {brl(meta.falta)}.",
                "meta_id": meta.id,
            })
    return avisos
