# Fined

Aplicação de controle financeiro pessoal com lançamentos de receitas e despesas, painel mensal, metas e cinco leituras de educação financeira. Os lançamentos e as metas ficam vinculados à conta que os criou.

No extrato, escolha o mês e filtre por tipo, categoria ou descrição. O botão **Baixar CSV** exporta os lançamentos que aparecem com esses filtros.

## Publicação

O projeto Fined no Supabase já tem o esquema versionado em `deploy/sql/`. Use o [guia do Render](DEPLOY-RENDER.md) ou o [guia da Oracle Cloud](DEPLOY-ORACLE.md) conforme o destino da publicação.

## Executar localmente

Requer Python 3.10 ou superior. No PowerShell, dentro da pasta `Fined` extraída do ZIP:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

No macOS ou Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python run.py
```

Abra [http://127.0.0.1:5000](http://127.0.0.1:5000) e crie uma conta.

A prévia HTML abre uma demonstração com dados de exemplo. Use o servidor Flask para criar sua conta e entrar com seu e-mail e senha.

Novas senhas exigem de 15 a 128 caracteres. O login continua aceitando senhas antigas. O banco guarda temporariamente os limites de tentativas por endereço e por conta.

## Banco de dados

O Flask usa SQLAlchemy. Na configuração padrão, a primeira execução cria um SQLite vazio em `instance/trocado.db`. O nome do arquivo foi mantido para que instalações anteriores possam reutilizar o mesmo banco. O ZIP contém o código que define as tabelas.

O banco contém as tabelas `usuarios`, `lancamentos`, `metas`, `contribuicoes`, `limites_autenticacao` e `sessoes_autenticacao`. Os valores monetários são armazenados em centavos inteiros. As contribuições às metas são registradas à parte das receitas e despesas.

Para desenvolvimento com um PostgreSQL local, instale o driver no mesmo ambiente virtual e configure `DATABASE_URL`. Exemplo para PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install "psycopg[binary]"
$env:DATABASE_URL = "postgresql://usuario:senha@localhost:5432/fined"
.\.venv\Scripts\python.exe run.py
```

Em desenvolvimento, o código cria as tabelas ausentes na inicialização. Em produção, a aplicação valida o esquema previamente instalado no Supabase. Sessões emitidas por versões anteriores precisam de um novo login.

| Variável | Uso |
| --- | --- |
| `DATABASE_URL` | Endereço do banco. Sem ela, o projeto usa SQLite local. |
| `SECRET_KEY` | Chave das sessões. Sem ela, o projeto gera a chave e grava em `instance/chave_secreta`. |
| `COOKIE_SEGURO` | Defina como `1` para cookies de sessão enviados por HTTPS. |
| `HOST` e `PORT` | Endereço e porta. Os padrões são `127.0.0.1` e `5000`. |

## Testes

Execute `python -m pytest` no ambiente virtual. A suíte usa um banco SQLite temporário para testar autenticação, isolamento das contas, lançamentos, cálculos, metas, persistência, perfil e páginas públicas.

## Estrutura

- `app/rotas/` contém as páginas e operações do Flask.
- `app/templates/` e `app/static/` contêm a interface, os estilos e os guias.
- `app/models.py` define as tabelas.
- `app/financas.py` e `app/dinheiro.py` calculam e formatam os valores.
- `tests/` contém a suíte automatizada.
- `run.py` inicia o servidor local.
