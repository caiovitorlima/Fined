from flask import Blueprint, abort, g, render_template

from ..conteudo import ARTIGOS, POR_SLUG

bp = Blueprint("aprender", __name__, url_prefix="/aprender")


def _layout():
    return "layout_app.html" if g.usuario is not None else "layout_publico.html"


@bp.get("")
def indice():
    return render_template("aprender/indice.html", layout=_layout(), artigos=ARTIGOS)


@bp.get("/<slug>")
def artigo(slug):
    atual = POR_SLUG.get(slug)
    if atual is None:
        abort(404)
    posicao = ARTIGOS.index(atual)
    seguinte = ARTIGOS[(posicao + 1) % len(ARTIGOS)]
    return render_template(
        f"aprender/{slug}.html",
        layout=_layout(),
        artigo=atual,
        seguinte=seguinte,
    )
