from flask import Blueprint, render_template

from ..conteudo import ARTIGOS

bp = Blueprint("publico", __name__)


@bp.get("/")
def inicio():
    return render_template("publico/inicio.html", artigos=ARTIGOS)
