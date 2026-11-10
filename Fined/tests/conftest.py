import re

import pytest

from app import create_app, db


@pytest.fixture
def app(tmp_path):
    aplicacao = create_app({
        "TESTING": True,
        "SECRET_KEY": "teste",
        "SQLALCHEMY_DATABASE_URI": "sqlite:///" + (tmp_path / "teste.db").as_posix(),
    })
    yield aplicacao
    with aplicacao.app_context():
        db.session.remove()
        db.engine.dispose()


@pytest.fixture
def client(app):
    return app.test_client()


def token(client, url="/entrar"):
    resposta = client.get(url)
    achado = re.search(r'name="_csrf" value="([^"]+)"', resposta.get_data(as_text=True))
    assert achado, f"sem token em {url}"
    return achado.group(1)


def postar(client, url, dados, pagina=None):
    dados = dict(dados)
    dados["_csrf"] = token(client, pagina or url)
    return client.post(url, data=dados)


def cadastrar(client, nome="Ana Souza", email="ana@exemplo.com", senha="senha de teste antiga longa"):
    return postar(client, "/cadastro", {"nome": nome, "email": email, "senha": senha})


def sair(client):
    return postar(client, "/sair", {}, pagina="/painel")


def entrar(client, email="ana@exemplo.com", senha="senha de teste antiga longa"):
    return postar(client, "/entrar", {"email": email, "senha": senha})
