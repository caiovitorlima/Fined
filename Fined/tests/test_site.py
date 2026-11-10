import csv
from io import StringIO
from datetime import date, timedelta

import pytest
from sqlalchemy import func, select

from app import db
from app.dinheiro import brl, ler_valor
from app.financas import deslocar_mes, fatias_rosca, gerar_avisos, resumir
from app.models import Contribuicao, Lancamento, Meta, Usuario
from app.rotas import auth

from .conftest import cadastrar, entrar, postar, sair, token

HOJE = date.today()
MES = f"{HOJE.year:04d}-{HOJE.month:02d}"


def lancar(client, tipo="despesa", valor="10,00", categoria="alimentacao", data=None, descricao=""):
    return postar(client, "/lancamentos/novo", {
        "tipo": tipo,
        "valor": valor,
        f"categoria_{tipo}": categoria,
        "data": (data or HOJE).isoformat(),
        "descricao": descricao,
    })


def texto(resposta):
    return resposta.get_data(as_text=True)


class TestDinheiro:
    @pytest.mark.parametrize("entrada,esperado", [
        ("10", 1000),
        ("10,5", 1050),
        ("10,50", 1050),
        ("10.50", 1050),
        ("1.234,56", 123456),
        ("1,234.56", 123456),
        ("1.500", 150000),
        ("R$ 2.000,00", 200000),
        ("0,01", 1),
        ("+5", 500),
    ])
    def test_formatos_aceitos(self, entrada, esperado):
        assert ler_valor(entrada) == esperado

    @pytest.mark.parametrize("entrada", ["", "abc", "-5", "0", "0,00", "1,2,3", "12,345", "1+2", "10000000,01"])
    def test_formatos_recusados(self, entrada):
        with pytest.raises(ValueError):
            ler_valor(entrada)

    def test_formatacao(self):
        assert brl(123456) == "R$ 1.234,56"
        assert brl(-500) == "−R$ 5,00"
        assert brl(5, sinal=True) == "+R$ 0,05"
        assert brl(0) == "R$ 0,00"


class TestContas:
    def test_cadastro_retorna_ao_lancamento_solicitado(self, client):
        destino = "/lancamentos/novo?tipo=despesa"
        redirecionamento = client.get(destino)
        assert "/entrar?next=" in redirecionamento.headers["Location"]
        cadastro = "/cadastro?next=/lancamentos/novo%3Ftipo%3Ddespesa"
        assert f'name="next" value="{destino}"' in texto(client.get(cadastro))
        resposta = postar(client, "/cadastro", {
            "nome": "Ana Souza", "email": "ana@exemplo.com",
            "senha": "senha de teste antiga longa", "next": destino,
        }, pagina=cadastro)
        assert resposta.headers["Location"] == destino
        assert client.get(destino).status_code == 200

    def test_limite_de_login_por_conta_e_expiracao(self, client, app, monkeypatch):
        agora = 10000
        monkeypatch.setattr(auth, "time", lambda: agora)
        cadastrar(client)
        sair(client)
        for _ in range(8):
            assert entrar(client, senha="senha incorreta").status_code == 401
        outro_cliente = app.test_client()
        outro_cliente.environ_base["REMOTE_ADDR"] = "192.0.2.1"
        bloqueio = entrar(outro_cliente)
        assert bloqueio.status_code == 429
        assert int(bloqueio.headers["Retry-After"]) == auth.JANELA_TENTATIVAS
        agora += auth.JANELA_TENTATIVAS
        assert entrar(outro_cliente).status_code == 302

    def test_senha_antiga_funciona_e_troca_encerra_outras_sessoes(self, client, app):
        with app.app_context():
            usuario = Usuario(nome="Ana Souza", email="ana@exemplo.com")
            usuario.definir_senha("senha123")
            db.session.add(usuario)
            db.session.commit()
        outro_cliente = app.test_client()
        assert entrar(client, senha="senha123").status_code == 302
        assert entrar(outro_cliente, senha="senha123").status_code == 302
        resposta = postar(client, "/perfil/senha", {
            "senha_atual": "senha123", "senha_nova": "nova senha de teste longa",
        }, pagina="/perfil")
        assert resposta.status_code == 302
        assert client.get("/perfil").status_code == 200
        assert outro_cliente.get("/perfil").status_code == 302

    def test_cadastro_entra_direto_no_painel(self, client):
        resposta = cadastrar(client)
        assert resposta.status_code == 302
        assert resposta.headers["Location"].endswith("/painel")
        assert "Painel financeiro" in texto(client.get("/painel"))

    def test_cadastro_mostra_alerta_apenas_quando_bloqueado(self, client, monkeypatch):
        pagina = client.get("/cadastro")
        assert pagina.status_code == 200
        assert 'class="alerta-form"' not in texto(pagina)

        monkeypatch.setattr("app.rotas.auth._registrar_tentativas", lambda *limites: 60)
        bloqueio = cadastrar(client)
        assert bloqueio.status_code == 429
        assert bloqueio.headers["Retry-After"] == "60"
        assert 'class="alerta-form"' in texto(bloqueio)
        assert "Muitas tentativas de cadastro." in texto(bloqueio)

    def test_cadastro_valida_campos(self, client):
        resposta = cadastrar(client, nome="A", email="sem-arroba", senha="123")
        corpo = texto(resposta)
        assert resposta.status_code == 400
        assert "Escreva seu nome." in corpo
        assert "Informe um e-mail válido." in corpo
        assert "pelo menos 15 caracteres" in corpo

    def test_email_duplicado(self, client):
        cadastrar(client)
        sair(client)
        resposta = cadastrar(client, email="ANA@exemplo.com")
        assert resposta.status_code == 400
        assert "Já existe uma conta com esse e-mail." in texto(resposta)

    def test_senha_guardada_com_hash(self, client, app):
        cadastrar(client)
        with app.app_context():
            usuario = db.session.scalar(select(Usuario))
            assert usuario.senha_hash != "senha de teste antiga longa"
            assert usuario.confere_senha("senha de teste antiga longa")

    def test_login_e_senha_incorreta(self, client):
        cadastrar(client)
        sair(client)
        assert client.get("/painel").status_code == 302
        errado = entrar(client, senha="errada-123")
        assert errado.status_code == 401
        assert "E-mail ou senha incorretos." in texto(errado)
        assert client.get("/painel").status_code == 302
        certo = entrar(client)
        assert certo.status_code == 302
        assert client.get("/painel").status_code == 200

    def test_email_inexistente(self, client):
        resposta = entrar(client, email="ninguem@exemplo.com")
        assert resposta.status_code == 401

    def test_rotas_protegidas_redirecionam(self, client):
        for url in ("/painel", "/lancamentos", "/lancamentos/novo", "/metas", "/metas/nova", "/perfil"):
            resposta = client.get(url)
            assert resposta.status_code == 302, url
            assert "/entrar?next=" in resposta.headers["Location"], url

    def test_volta_para_pagina_pedida(self, client):
        cadastrar(client)
        sair(client)
        dados = {"email": "ana@exemplo.com", "senha": "senha de teste antiga longa", "next": "/metas"}
        resposta = postar(client, "/entrar", dados)
        assert resposta.headers["Location"].endswith("/metas")

    @pytest.mark.parametrize("destino", ["https://malicioso.com", "//malicioso.com", "/\\malicioso.com"])
    def test_bloqueia_redirecionamento_externo(self, client, destino):
        cadastrar(client)
        sair(client)
        dados = {"email": "ana@exemplo.com", "senha": "senha de teste antiga longa", "next": destino}
        resposta = postar(client, "/entrar", dados)
        assert resposta.headers["Location"].endswith("/painel")

    def test_post_sem_csrf_e_recusado(self, client):
        resposta = client.post("/cadastro", data={"nome": "Ana", "email": "a@b.com", "senha": "12345678"})
        assert resposta.status_code == 400
        resposta = client.post("/cadastro", data={"_csrf": "ç-invalido", "nome": "Ana"})
        assert resposta.status_code == 400

    def test_sair_encerra_sessao(self, client, app):
        cadastrar(client)
        nome_cookie = app.config["SESSION_COOKIE_NAME"]
        copia = app.test_client()
        copia.set_cookie(nome_cookie, client.get_cookie(nome_cookie).value)
        assert copia.get("/painel").status_code == 200

        sair(client)
        assert client.get("/painel").status_code == 302
        assert copia.get("/painel").status_code == 302


class TestLancamentos:
    def test_criar_editar_excluir(self, client, app):
        cadastrar(client)
        resposta = lancar(client, valor="25,90", descricao="Lanche da tarde")
        assert resposta.status_code == 302
        assert f"mes={MES}" in resposta.headers["Location"]
        assert "Lanche da tarde" in texto(client.get("/lancamentos"))

        with app.app_context():
            item = db.session.scalar(select(Lancamento))
            assert item.valor_centavos == 2590
            assert item.categoria == "alimentacao"
            id_ = item.id

        editar = client.get(f"/lancamentos/{id_}/editar")
        assert 'value="25,90"' in texto(editar)
        dados = {
            "tipo": "despesa", "valor": "30", "categoria_despesa": "transporte",
            "data": HOJE.isoformat(), "descricao": "Uber",
        }
        resposta = postar(client, f"/lancamentos/{id_}/editar", dados)
        assert resposta.status_code == 302
        with app.app_context():
            item = db.session.get(Lancamento, id_)
            assert (item.valor_centavos, item.categoria, item.descricao) == (3000, "transporte", "Uber")

        resposta = postar(client, f"/lancamentos/{id_}/excluir", {}, pagina="/lancamentos")
        assert resposta.status_code == 302
        with app.app_context():
            assert db.session.get(Lancamento, id_) is None

    def test_validacao(self, client):
        cadastrar(client)
        resposta = postar(client, "/lancamentos/novo", {
            "tipo": "receita", "valor": "-3", "categoria_receita": "alimentacao", "data": "31/12/2026",
        })
        corpo = texto(resposta)
        assert resposta.status_code == 400
        assert "maior que zero" in corpo
        assert "Escolha uma categoria." in corpo
        assert "Informe uma data válida." in corpo

    def test_tipo_invalido(self, client):
        cadastrar(client)
        resposta = postar(client, "/lancamentos/novo", {
            "tipo": "transferencia", "valor": "10", "categoria_despesa": "lazer", "data": HOJE.isoformat(),
        })
        assert resposta.status_code == 400
        assert "Escolha receita ou despesa." in texto(resposta)

    def test_salvar_e_continuar(self, client):
        cadastrar(client)
        resposta = postar(client, "/lancamentos/novo", {
            "tipo": "receita", "valor": "100", "categoria_receita": "mesada",
            "data": HOJE.isoformat(), "continuar": "1",
        })
        assert "/lancamentos/novo?tipo=receita" in resposta.headers["Location"]

    def test_filtro_por_mes_e_tipo(self, client):
        cadastrar(client)
        passado = date(*deslocar_mes(HOJE.year, HOJE.month, -1), 15)
        lancar(client, valor="11", descricao="Gasto deste mes")
        lancar(client, valor="22", descricao="Gasto do mes passado", data=passado)
        lancar(client, tipo="receita", valor="500", categoria="mesada", descricao="Mesada do mes")

        atual = texto(client.get(f"/lancamentos?mes={MES}"))
        assert "Gasto deste mes" in atual and "Mesada do mes" in atual
        assert "Gasto do mes passado" not in atual

        anterior = texto(client.get(f"/lancamentos?mes={passado:%Y-%m}"))
        assert "Gasto do mes passado" in anterior and "Gasto deste mes" not in anterior

        so_entradas = texto(client.get(f"/lancamentos?mes={MES}&tipo=receita"))
        assert "Mesada do mes" in so_entradas and "Gasto deste mes" not in so_entradas

        so_saidas = texto(client.get(f"/lancamentos?mes={MES}&tipo=despesa"))
        assert "Gasto deste mes" in so_saidas and "Mesada do mes" not in so_saidas

    def test_busca_categoria_e_exportacao(self, client, app):
        url = f"/lancamentos/exportar.csv?mes={MES}"
        assert client.get(url).status_code == 302
        cadastrar(client)
        lancar(client, categoria="alimentacao", descricao="Café; almoço")
        lancar(client, categoria="transporte", descricao="Café no caminho")
        lancar(client, categoria="alimentacao", descricao="=1+1")
        outra_conta = app.test_client()
        cadastrar(outra_conta, nome="Outra pessoa", email="outra@example.com")
        lancar(outra_conta, categoria="alimentacao", descricao="Café particular")
        filtros = "&tipo=despesa&categoria=alimentacao&q=cafe"
        corpo = texto(client.get(f"/lancamentos?mes={MES}" + filtros))
        assert "Café; almoço" in corpo
        assert "Café no caminho" not in corpo and "Café particular" not in corpo
        resposta = client.get(url + filtros)
        assert resposta.mimetype == "text/csv"
        assert f"fined-{MES}.csv" in resposta.headers["Content-Disposition"]
        linhas = list(csv.reader(StringIO(resposta.data.decode("utf-8-sig")), delimiter=";"))
        assert len(linhas) == 2
        assert linhas[1][1:] == ["Despesa", "Alimentação", "Café; almoço", "-10,00"]
        assert "'=1+1" in client.get(url).get_data(as_text=True)

    def test_mes_invalido_cai_no_atual(self, client):
        cadastrar(client)
        for valor in ("abc", "2026-13", "1999-01", "2026"):
            assert client.get(f"/lancamentos?mes={valor}").status_code == 200
            assert client.get(f"/painel?mes={valor}").status_code == 200


class TestPainel:
    def test_totais_e_grafico_atualizam(self, client):
        cadastrar(client)
        lancar(client, tipo="receita", valor="1.000,00", categoria="salario")
        lancar(client, valor="300", categoria="alimentacao")
        lancar(client, valor="120", categoria="transporte")
        corpo = texto(client.get("/painel"))
        assert '<span class="vg__reais">1.000</span>' in corpo
        assert '<span class="vg__reais">420</span>' in corpo
        assert '<span class="vg__reais">580</span>' in corpo
        assert "Alimentação" in corpo and "R$ 300,00" in corpo
        assert "Transporte" in corpo and "R$ 120,00" in corpo
        assert "stroke-dasharray" in corpo
        assert "Resultado do mês" in corpo

        lancar(client, valor="900", categoria="lazer")
        corpo = texto(client.get("/painel"))
        assert "is-negativo" in corpo
        assert '<span class="vg__reais">320</span>' in corpo
        assert "Despesas acima das receitas" in corpo

    def test_painel_vazio(self, client):
        cadastrar(client)
        corpo = texto(client.get("/painel"))
        assert "Nenhum lançamento no mês." in corpo
        assert "Nenhuma despesa neste mês" in corpo

    def test_resumo_e_avisos(self, app):
        with app.app_context():
            itens = [
                Lancamento(tipo="receita", valor_centavos=50000, categoria="mesada", data=HOJE),
                Lancamento(tipo="despesa", valor_centavos=30000, categoria="lazer", data=HOJE),
                Lancamento(tipo="despesa", valor_centavos=5000, categoria="alimentacao", data=HOJE),
                Lancamento(tipo="despesa", valor_centavos=5000, categoria="transporte", data=HOJE),
            ]
            resumo = resumir(itens)
            assert (resumo.receitas, resumo.despesas, resumo.resultado) == (50000, 40000, 10000)
            assert resumo.categorias[0]["chave"] == "lazer"
            assert resumo.categorias[0]["fracao"] == pytest.approx(0.75)
            assert gerar_avisos(resumo, [], HOJE) == []

            fatias = fatias_rosca(resumo.categorias)
            assert len(fatias) == 3
            assert fatias[0]["inicio"] == pytest.approx(25)
            assert all(f["arco"] + f["resto"] == pytest.approx(100) for f in fatias)

    def test_aviso_sem_receita(self, app):
        with app.app_context():
            resumo = resumir([Lancamento(tipo="despesa", valor_centavos=1000, categoria="lazer", data=HOJE)])
            avisos = gerar_avisos(resumo, [], HOJE)
            assert avisos[0]["tipo"] == "alerta"
            assert "nenhuma entrada" in avisos[0]["texto"]


class TestMetas:
    def criar(self, client, nome="Fone novo", alvo="500", prazo=None, guardado=""):
        return postar(client, "/metas/nova", {
            "nome": nome,
            "valor_alvo": alvo,
            "prazo": (prazo or HOJE + timedelta(days=90)).isoformat(),
            "guardado": guardado,
        })

    def test_criar_guardar_e_bater(self, client, app):
        cadastrar(client)
        resposta = self.criar(client, guardado="100")
        assert resposta.status_code == 302
        url = resposta.headers["Location"]
        corpo = texto(client.get(url))
        assert "Fone novo" in corpo and "20%" in corpo

        meta_url = url.split("localhost")[-1]
        resposta = postar(client, meta_url + "/guardar", {"valor": "150", "data": HOJE.isoformat()}, pagina=meta_url)
        assert resposta.status_code == 302
        assert "50%" in texto(client.get(meta_url))

        resposta = postar(client, meta_url + "/guardar", {"valor": "250", "data": HOJE.isoformat()}, pagina=meta_url)
        corpo = texto(client.get(meta_url))
        assert "100%" in corpo and "concluída" in corpo
        with app.app_context():
            meta = db.session.scalar(select(Meta))
            assert meta.guardado == 50000 and meta.concluida
            assert db.session.scalar(select(func.count(Lancamento.id))) == 0

    def test_meta_nao_mexe_nas_despesas(self, client):
        cadastrar(client)
        lancar(client, tipo="receita", valor="1000", categoria="salario")
        self.criar(client, guardado="400")
        corpo = texto(client.get("/painel"))
        assert '<span class="vg__reais">1.000</span>' in corpo
        assert "Nenhuma despesa neste mês" in corpo

    def test_validacoes(self, client):
        cadastrar(client)
        resposta = self.criar(client, nome="", alvo="0", prazo=HOJE - timedelta(days=1))
        corpo = texto(resposta)
        assert resposta.status_code == 400
        assert "Informe o nome da meta." in corpo
        assert "maior que zero" in corpo
        assert "hoje ou depois" in corpo

    def test_contribuicao_futura_recusada(self, client):
        cadastrar(client)
        url = self.criar(client).headers["Location"].split("localhost")[-1]
        amanha = (HOJE + timedelta(days=1)).isoformat()
        resposta = postar(client, url + "/guardar", {"valor": "10", "data": amanha}, pagina=url)
        assert resposta.status_code == 400
        assert "não pode estar no futuro" in texto(resposta)

    def test_editar_remover_contribuicao_e_excluir(self, client, app):
        cadastrar(client)
        url = self.criar(client, guardado="50").headers["Location"].split("localhost")[-1]
        with app.app_context():
            meta = db.session.scalar(select(Meta))
            contribuicao_id = meta.contribuicoes[0].id
            meta_id = meta.id

        postar(client, f"{url}/editar", {
            "nome": "Fone bom", "valor_alvo": "800", "prazo": (HOJE + timedelta(days=10)).isoformat(),
        })
        postar(client, f"{url}/contribuicoes/{contribuicao_id}/excluir", {}, pagina=url)
        with app.app_context():
            meta = db.session.get(Meta, meta_id)
            assert (meta.nome, meta.valor_alvo_centavos, meta.guardado) == ("Fone bom", 80000, 0)

        assert "vence em 10 dias" in texto(client.get("/painel"))

        postar(client, f"{url}/excluir", {}, pagina=url)
        with app.app_context():
            assert db.session.get(Meta, meta_id) is None
            assert db.session.scalar(select(func.count(Contribuicao.id))) == 0

    def test_preenche_meta_pelos_parametros(self, client):
        cadastrar(client)
        prazo = (HOJE + timedelta(days=200)).isoformat()
        corpo = texto(client.get(f"/metas/nova?nome=Reserva+de+emergência&valor=1800,00&prazo={prazo}"))
        assert 'value="Reserva de emergência"' in corpo
        assert 'value="1800,00"' in corpo
        assert f'value="{prazo}"' in corpo

    def test_sugestao_mensal(self, app):
        with app.app_context():
            meta = Meta(nome="X", valor_alvo_centavos=60000, prazo=HOJE + timedelta(days=183))
            meta.contribuicoes.append(Contribuicao(valor_centavos=10000, data=HOJE))
            assert meta.percentual == 16
            assert meta.falta == 50000
            assert meta.sugestao_mensal(HOJE) == 50000 // 7 + 1


class TestPersistenciaEIsolamento:
    def test_dados_continuam_apos_novo_login(self, client):
        cadastrar(client)
        lancar(client, valor="42,00", descricao="Ingresso do cinema")
        postar(client, "/metas/nova", {"nome": "Viagem", "valor_alvo": "900", "prazo": (HOJE + timedelta(days=60)).isoformat()})
        sair(client)
        entrar(client)
        assert "Ingresso do cinema" in texto(client.get("/lancamentos"))
        assert "Viagem" in texto(client.get("/metas"))

    def test_outra_conta_nao_acessa(self, client, app):
        cadastrar(client)
        lancar(client, valor="77", descricao="Segredo da Ana")
        postar(client, "/metas/nova", {"nome": "Meta da Ana", "valor_alvo": "900", "prazo": (HOJE + timedelta(days=60)).isoformat()})
        with app.app_context():
            lancamento_id = db.session.scalar(select(Lancamento.id))
            meta = db.session.scalar(select(Meta))
            meta_id = meta.id
        sair(client)

        cadastrar(client, nome="Beto", email="beto@exemplo.com")
        assert "Segredo da Ana" not in texto(client.get("/lancamentos"))
        assert "Meta da Ana" not in texto(client.get("/metas"))
        assert "Segredo da Ana" not in texto(client.get("/painel"))
        assert client.get(f"/lancamentos/{lancamento_id}/editar").status_code == 404
        assert client.get(f"/metas/{meta_id}").status_code == 404
        assert client.get(f"/metas/{meta_id}/editar").status_code == 404

        csrf = token(client, "/painel")
        assert client.post(f"/lancamentos/{lancamento_id}/excluir", data={"_csrf": csrf}).status_code == 404
        assert client.post(f"/lancamentos/{lancamento_id}/editar", data={
            "_csrf": csrf, "tipo": "despesa", "valor": "1", "categoria_despesa": "lazer", "data": HOJE.isoformat(),
        }).status_code == 404
        assert client.post(f"/metas/{meta_id}/guardar", data={"_csrf": csrf, "valor": "1", "data": HOJE.isoformat()}).status_code == 404
        assert client.post(f"/metas/{meta_id}/excluir", data={"_csrf": csrf}).status_code == 404

        with app.app_context():
            assert db.session.get(Lancamento, lancamento_id).valor_centavos == 7700
            assert db.session.get(Meta, meta_id).guardado == 0


class TestPerfil:
    def test_atualizar_dados_e_senha(self, client, app):
        cadastrar(client)
        dados = {"nome": "Ana Clara", "email": "ana.clara@exemplo.com"}
        assert postar(client, "/perfil/dados", dados, pagina="/perfil").status_code == 400
        dados["senha_atual"] = "senha de teste antiga longa"
        resposta = postar(client, "/perfil/dados", dados, pagina="/perfil")
        assert resposta.status_code == 302
        resposta = postar(client, "/perfil/senha", {"senha_atual": "errada", "senha_nova": "nova senha de teste longa"}, pagina="/perfil")
        assert resposta.status_code == 400
        resposta = postar(client, "/perfil/senha", {"senha_atual": "senha de teste antiga longa", "senha_nova": "nova senha de teste longa"}, pagina="/perfil")
        assert resposta.status_code == 302
        sair(client)
        assert entrar(client, email="ana.clara@exemplo.com", senha="senha de teste antiga longa").status_code == 401
        assert entrar(client, email="ana.clara@exemplo.com", senha="nova senha de teste longa").status_code == 302

    def test_email_de_outra_conta(self, client):
        cadastrar(client, nome="Beto", email="beto@exemplo.com")
        sair(client)
        cadastrar(client)
        resposta = postar(client, "/perfil/dados", {"nome": "Ana", "email": "beto@exemplo.com"}, pagina="/perfil")
        assert resposta.status_code == 400
        assert "já está em outra conta" in texto(resposta)

    def test_excluir_conta_apaga_tudo(self, client, app):
        cadastrar(client)
        lancar(client)
        postar(client, "/metas/nova", {"nome": "Viagem", "valor_alvo": "900", "prazo": (HOJE + timedelta(days=60)).isoformat(), "guardado": "10"})
        assert postar(client, "/perfil/excluir", {"senha": "errada"}, pagina="/perfil").status_code == 400
        assert postar(client, "/perfil/excluir", {"senha": "senha de teste antiga longa"}, pagina="/perfil").status_code == 302
        with app.app_context():
            for modelo in (Usuario, Lancamento, Meta, Contribuicao):
                assert db.session.scalar(select(func.count()).select_from(modelo)) == 0
        assert client.get("/painel").status_code == 302


class TestPaginasPublicas:
    def test_paginas_abrem(self, client):
        for url in ("/", "/entrar", "/cadastro", "/aprender"):
            assert client.get(url).status_code == 200, url

    @pytest.mark.parametrize("slug", [
        "orcamento", "controle-de-gastos", "reserva-de-emergencia", "consumo-consciente", "investimentos-basico",
    ])
    def test_artigos(self, client, slug):
        resposta = client.get(f"/aprender/{slug}")
        assert resposta.status_code == 200
        corpo = texto(resposta)
        assert "Próxima leitura" in corpo
        assert "data-calc" not in corpo
        assert "Material educativo" not in corpo

    def test_artigo_logado_usa_layout_do_app(self, client):
        cadastrar(client)
        assert 'aria-label="Área da conta"' in texto(client.get("/aprender/orcamento"))

    def test_404(self, client):
        assert client.get("/aprender/nao-existe").status_code == 404
        assert client.get("/qualquer-coisa").status_code == 404
