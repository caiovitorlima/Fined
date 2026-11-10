from datetime import date, timedelta

from .categorias import CATEGORIAS, cor, rotulo
from .dinheiro import brl, centavos, para_campo, reais

MESES = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)
MESES_CURTOS = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")
DIAS_SEMANA = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")


def data_br(valor):
    return valor.strftime("%d/%m/%Y") if valor else ""


def data_curta(valor):
    return f"{valor.day:02d} {MESES_CURTOS[valor.month - 1]}"


def data_extensa(valor):
    return f"{valor.day} de {MESES[valor.month - 1]} de {valor.year}"


def titulo_dia(valor, hoje):
    if valor == hoje:
        return "Hoje"
    if valor == hoje - timedelta(days=1):
        return "Ontem"
    return f"{DIAS_SEMANA[valor.weekday()]}, {valor.day} de {MESES[valor.month - 1]}"


def mes_extenso(ano, mes):
    return f"{MESES[mes - 1]} de {ano}"


def primeiro_nome(nome):
    partes = (nome or "").split()
    return partes[0] if partes else ""


def iniciais(nome):
    partes = (nome or "").split()
    if not partes:
        return "?"
    if len(partes) == 1:
        return partes[0][:2].upper()
    return (partes[0][0] + partes[-1][0]).upper()


def plural(numero, singular, plural_):
    return f"{numero} {singular if numero == 1 else plural_}"


def porcento(fracao):
    valor = fracao * 100
    if 0 < valor < 1:
        return "<1%"
    return f"{round(valor)}%"


def registrar(app):
    app.jinja_env.filters.update(
        brl=brl,
        reais=reais,
        centavos=centavos,
        para_campo=para_campo,
        data_br=data_br,
        data_curta=data_curta,
        data_extensa=data_extensa,
        primeiro_nome=primeiro_nome,
        iniciais=iniciais,
        porcento=porcento,
    )
    app.jinja_env.globals.update(
        CATEGORIAS=CATEGORIAS,
        rotulo_categoria=rotulo,
        cor_categoria=cor,
        mes_extenso=mes_extenso,
        titulo_dia=titulo_dia,
        plural=plural,
    )

    @app.context_processor
    def datas():
        return {"hoje": date.today()}
