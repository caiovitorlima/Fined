# Publicar o Fined no Render

O Blueprint `render.yaml` cria um Web Service Docker no plano **Free**, na região **Virginia**. O Render fornece o endereço HTTPS. O PostgreSQL continua no projeto Fined do Supabase, em São Paulo, com o esquema já aplicado.

[Projeto Fined no Supabase](https://supabase.com/dashboard/project/kwlopoulfjqqbqbxuous) · [Painel do Render](https://dashboard.render.com/)

## 1. Colocar o código em um repositório privado

1. Extraia `Fined-Render.zip` em uma pasta fora de outros repositórios, como `Downloads`.
2. No GitHub, crie um repositório **Private** chamado `fined`. Na criação, deixe README, licença e gitignore desmarcados para o repositório começar vazio.
3. Abra o PowerShell na pasta extraída `Fined`, onde está `render.yaml`. Com o Git instalado, rode os comandos abaixo. Troque `SEU_USUARIO` pelo seu nome de usuário no GitHub.

```powershell
git init -b main
git add .
git commit -m "Prepara o Fined para o Render"
git remote add origin https://github.com/SEU_USUARIO/fined.git
git push -u origin main
```

Se o Git pedir autenticação, conclua pelo navegador. Se o commit der `Author identity unknown`, defina seu nome com `git config user.name "Seu nome"` e o e-mail da conta com `git config user.email "seu e-mail do GitHub"`. Depois repita a partir de `git commit`. O arquivo `render.yaml` deve aparecer na raiz do repositório. Guarde a senha do banco no gerenciador de senhas e no Render.

[Criar um repositório no GitHub](https://docs.github.com/pt/repositories/creating-and-managing-repositories/creating-a-new-repository) · [Conectar o GitHub ao Render](https://render.com/docs/git-provider)

## 2. Definir a senha do papel de produção

Se você já configurou a senha de `fined_app`, use essa senha na etapa 3. Se ainda não configurou, escolha uma senha aleatória de pelo menos 32 caracteres no seu gerenciador. No Supabase, abra **Database → Settings**. Se você ainda não tem a senha administrativa do projeto, defina uma em **Database password**. Ative **Enforce SSL on incoming connections** para exigir TLS. Se o banco reiniciar, espere voltar ao estado ativo.

Com o cliente PostgreSQL `psql` instalado, execute este comando no PowerShell dentro da pasta `Fined`. O primeiro prompt pede a senha administrativa.

```powershell
$caFined = (Resolve-Path .\deploy\supabase-ca.crt).Path.Replace('\', '/')
psql -X -W "host=aws-1-sa-east-1.pooler.supabase.com port=5432 dbname=postgres user=postgres.kwlopoulfjqqbqbxuous sslmode=verify-full sslrootcert='$caFined'"
```

Se o `psql` ainda não estiver no PATH do Windows, use o caminho completo para o executável instalado, como `& "C:\Program Files\PostgreSQL\17\bin\psql.exe"`, seguido dos mesmos argumentos.

Dentro do `psql`, rode os comandos abaixo. No primeiro, digite a nova senha de `fined_app` duas vezes.

```text
\password fined_app
\q
```

[Conexão segura com psql no Supabase](https://supabase.com/docs/guides/database/psql) · [Instalador oficial do PostgreSQL para Windows](https://www.postgresql.org/download/windows/)

## 3. Criar o serviço gratuito

1. No Render, abra **New → Blueprint**. Conecte sua conta do GitHub e dê ao Render acesso ao repositório privado `fined`.
2. Selecione esse repositório e o branch `main`. Mantenha `render.yaml` como caminho do Blueprint.
3. Confirme que será criado um **Web Service** no plano **Free**. Preencha **FINED_DB_PASSWORD** com a senha de `fined_app`. O Render gera a chave de sessão. O Blueprint já traz o host, a referência do Supabase e a rota de saúde.
4. Clique em **Deploy Blueprint** e aguarde o deploy. Abra o endereço `onrender.com` mostrado pelo serviço.

Se você já ativou restrições de rede no Supabase, em **Connect → Outbound** do serviço Render copie os intervalos de saída e inclua-os na lista permitida do banco. Preserve o acesso da máquina que você usa para administrar o banco.

[Blueprints no Render](https://render.com/docs/infrastructure-as-code) · [IPs de saída no Render](https://render.com/docs/outbound-ip-addresses)

## 4. Conferir a publicação

Abra `/healthz` no endereço do serviço. A resposta deve ser `ok`, indicando que o aplicativo conseguiu consultar o banco. Crie uma conta temporária, registre uma despesa, saia e entre de novo para conferir se o lançamento continua lá. Apague a conta de teste pelo **Perfil**.

Se o deploy falhar, abra **Logs** no Render. Se aparecer falha ao conectar ao Supabase, confira se `FINED_DB_PASSWORD` é a senha de `fined_app`, se o projeto está ativo e se as restrições de rede incluem os IPs de saída do Render. Após uma alteração de senha, espere alguns instantes e tente novamente.

O plano gratuito hiberna após 15 minutos sem tráfego. A primeira visita depois disso pode levar cerca de um minuto.

[Health checks no Render](https://render.com/docs/health-checks) · [Limites do plano gratuito](https://render.com/docs/free)
