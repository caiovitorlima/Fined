# Publicar o Fined na Oracle Cloud

O Fined roda em uma VM Ubuntu com Docker Compose. O Caddy cuida do HTTPS e o Supabase guarda as contas e os dados financeiros. O projeto Fined já está criado em São Paulo, com o esquema inicial aplicado. O ZIP vem com o endereço do banco e o certificado público. Tenha à mão um domínio, sua chave SSH e acesso às contas da Oracle e do Supabase.

[Abrir o projeto Fined no Supabase](https://supabase.com/dashboard/project/kwlopoulfjqqbqbxuous)

## 1. Criar a VM e apontar o domínio

1. Na Oracle Cloud, crie uma instância **Ubuntu 24.04 LTS**, em uma sub-rede pública com Internet Gateway e rota `0.0.0.0/0` para esse gateway. Associe sua chave pública SSH. Para a VM de **512 MB** e uso de até três pessoas ao mesmo tempo, prepare a memória de apoio da etapa 2 antes de instalar o Docker.
2. Associe um **IP público reservado** à interface da VM. Na sua zona DNS, crie um registro `A` para o endereço do site, como `fined.seudominio.com.br`, apontando para esse IPv4. Crie um `AAAA` somente se o IPv6 também estiver configurado e alcançar a VM.
3. Nas regras de rede efetivas da instância, permita entrada TCP `80` e `443` da internet e TCP `22` apenas do seu IP público (`/32`). Revise a lista de segurança da sub-rede e os NSGs, pois suas permissões se somam. Mantenha saída para DNS, HTTPS e TCP `5432` para o Supabase. A porta `8000` fica na rede interna do Compose.
4. Se houver um firewall no Ubuntu, confira se ele permite o tráfego das portas `80` e `443`. Para a exposição pública, aplique as regras na OCI mesmo quando a VM usa um firewall local.

[IPs públicos na OCI](https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/managingpublicIPs.htm) · [Grupos de segurança de rede](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/networksecuritygroups.htm)

## 2. Instalar Docker na VM

Entre por SSH com o usuário `ubuntu`. No PowerShell, substitua `CAMINHO_DA_CHAVE` e `IP_DA_VM` pelos seus valores.

```powershell
ssh -i "CAMINHO_DA_CHAVE" ubuntu@IP_DA_VM
```

Na VM de **512 MB**, confira primeiro a memória, o espaço em disco e o swap. O swap usa espaço do disco para ajudar durante picos de memória. O PostgreSQL roda no Supabase.

```bash
free -h
df -h /
sudo swapon --show
```

Se a última linha não listar swap e houver pelo menos 2 GB livres na raiz, crie um arquivo de swap de 1 GB. Execute o bloco uma vez.

```bash
sudo sh -c 'umask 077 && dd if=/dev/zero of=/swapfile-fined bs=1M count=1024 oflag=excl status=progress' &&
  sudo mkswap /swapfile-fined &&
  sudo swapon /swapfile-fined &&
  printf '%s\n' '/swapfile-fined none swap sw 0 0' | sudo tee -a /etc/fstab
sudo swapon --show
```

Confirme que o arquivo aparece antes de seguir. [Manual do swapon](https://manpages.ubuntu.com/manpages/noble/man8/swapon.8.html)

Execute estes comandos na VM para instalar o Docker Engine e o Compose pelo repositório oficial.

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl unzip openssl postgresql-client
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
. /etc/os-release
sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${UBUNTU_CODENAME:-$VERSION_CODENAME}
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo docker compose version
```

Ao terminar, use `exit` para voltar ao PowerShell.

[Instalação do Docker no Ubuntu](https://docs.docker.com/engine/install/ubuntu/)

## 3. Preparar o Supabase

1. Abra as configurações de banco do projeto Fined. Em **Database password**, defina uma senha administrativa se ainda não tiver uma. Guarde-a em um gerenciador de senhas.
2. Em **SSL Configuration**, ative **Enforce SSL on incoming connections**. Se o Supabase reiniciar o banco, espere o projeto voltar ao estado ativo.
3. Em **Integrations → Data API**, desative **Enable Data API**. O Fined se conecta diretamente pelo protocolo PostgreSQL.

A migração inicial já está registrada nesse projeto. Reserve `deploy/sql/001_inicial.sql` para instalar o Fined em outro banco vazio.

[Conexão PostgreSQL no Supabase](https://supabase.com/docs/guides/database/connecting-to-postgres) · [SSL](https://supabase.com/docs/guides/platform/ssl-enforcement) · [Data API](https://supabase.com/docs/guides/api/securing-your-api#disable-the-data-api)

## 4. Enviar os arquivos e configurar os segredos

No seu computador, abra o PowerShell na pasta onde está o ZIP. Troque `CAMINHO_DA_CHAVE` pelo caminho da chave SSH privada e `IP_DA_VM` pelo IPv4 reservado.

```powershell
scp -i "CAMINHO_DA_CHAVE" .\Fined.zip ubuntu@IP_DA_VM:~/
ssh -i "CAMINHO_DA_CHAVE" ubuntu@IP_DA_VM
```

Na VM, extraia o ZIP e copie o arquivo de configuração. No editor, altere apenas `FINED_DOMINIO` para o nome DNS do seu site, sem `https://` ou barra.

```bash
cd "$HOME"
unzip -tq Fined.zip
unzip Fined.zip
cd Fined
umask 077
mkdir -p -m 700 secrets
cp -n .env.example .env
nano .env
```

Ainda na VM, abra o `psql` com a credencial administrativa. Digite a senha administrativa no prompt.

```bash
psql -X -W "host=aws-1-sa-east-1.pooler.supabase.com port=5432 dbname=postgres user=postgres.kwlopoulfjqqbqbxuous sslmode=verify-full sslrootcert=$PWD/deploy/supabase-ca.crt"
```

Dentro do `psql`, defina para `fined_app` uma senha nova e exclusiva, gerada pelo seu gerenciador, com pelo menos 32 caracteres. O comando abre o próprio prompt.

```text
\password fined_app
\q
```

No terminal da VM, digite a mesma senha de `fined_app` quando solicitado. Os arquivos ficam acessíveis ao usuário do contêiner por meio do grupo numérico `10001`. Use os comandos na pasta `Fined`.

```bash
read -rsp 'Senha de fined_app: ' FINED_SENHA; printf '\n'
printf '%s' "$FINED_SENHA" > secrets/db_password
unset FINED_SENHA
test -s secrets/secret_key || openssl rand -hex 48 > secrets/secret_key
sudo chgrp 10001 secrets/db_password secrets/secret_key
chmod 0440 secrets/db_password secrets/secret_key
```

[Usar psql com TLS no Supabase](https://supabase.com/docs/guides/database/psql)

## 5. Publicar e conferir

Antes de subir o site, teste a credencial da aplicação. Use a senha que você acabou de definir para `fined_app`.

```bash
psql -X -W "host=aws-1-sa-east-1.pooler.supabase.com port=5432 dbname=postgres user=fined_app.kwlopoulfjqqbqbxuous sslmode=verify-full sslrootcert=$PWD/deploy/supabase-ca.crt" \
  -c "SELECT current_user, has_schema_privilege(current_user, 'fined', 'CREATE') AS pode_alterar_esquema, (SELECT max(versao) FROM fined.versao_schema) AS versao, (SELECT count(*) FROM fined.usuarios) AS contas;"
```

Em uma instalação nova, a resposta deve mostrar `fined_app`, `f`, `1` e `0`, nessa ordem.

```bash
sudo docker compose config --quiet
sudo docker compose up -d --build --wait --wait-timeout 180
sudo docker compose ps
curl --fail --show-error https://fined.seudominio.com.br/healthz
```

Troque o domínio no comando `curl`. Quando o serviço estiver pronto, ele responde `ok`. A emissão do certificado depende de o DNS público apontar para a VM e de as portas web estarem acessíveis. Se o Caddy ainda estiver emitindo o certificado, aguarde e repita o `curl`.

Na VM de 512 MB, depois de testar o site, confira a coluna `available` de `free -h` e a coluna `MEM USAGE` de `sudo docker stats --no-stream`. Se houver lentidão contínua ou contêineres reiniciando, confira se o sistema registrou falta de memória com `sudo journalctl -k -g 'Out of memory|Killed process'`.

Abra o endereço HTTPS e crie uma conta para testar. O primeiro painel deve estar vazio. Registre uma despesa, saia, entre novamente e confira se o lançamento aparece. Em uma segunda conta, confira que o painel abre vazio. Ao terminar, exclua as duas contas de teste em **Perfil**.

No Supabase, restrinja as conexões PostgreSQL ao IP público de saída da VM (`IP/32`). Se a VM usar NAT, adicione o IP de saída do NAT. Inclua também o IP de uma estação administrativa se ela precisar acessar o PostgreSQL diretamente. Depois, reinicie o aplicativo para abrir novas conexões e teste o endpoint novamente.

```bash
sudo docker compose restart app
curl --fail --show-error https://fined.seudominio.com.br/healthz
```

[HTTPS automático do Caddy](https://caddyserver.com/docs/automatic-https) · [Restrições de rede do Supabase](https://supabase.com/docs/guides/platform/network-restrictions)

## 6. Operar o site

- Configure um monitor externo para consultar `https://SEU_DOMINIO/healthz` e avisar você se a resposta deixar de ser `200`. O Docker inicia com a VM e o Compose recupera processos encerrados. O estado `unhealthy` sozinho gera um sinal para investigação.
- Para evitar pausas por inatividade, use um plano Supabase sem suspensão automática e uma VM OCI fora das condições de retomada por ociosidade do Always Free. Com uma VM, reinicializações e manutenções podem causar interrupções.
- Configure backups conforme o plano do Supabase e teste a restauração em um projeto separado. Guarde a chave de sessão em local seguro. Se ela mudar, as pessoas precisam entrar novamente. Preserve os volumes `caddy_data` e `caddy_config` entre atualizações.
- Ative MFA nas contas administrativas da Oracle e do Supabase. Restrinja a chave SSH e os arquivos em `secrets/` às pessoas que operam o site.
- Aplique correções do Ubuntu e atualize as imagens do Docker regularmente, em janela de manutenção. Valide `/healthz` e o login após cada atualização.

```bash
sudo docker compose pull caddy
sudo docker compose build --pull app
sudo docker compose up -d
```

Se a página der `502`, veja os logs de `app` e `caddy`. Se o app falhar ao iniciar ou o `/healthz` responder `503`, rode de novo o teste com `psql` e confira a senha e as regras de rede. Se o certificado do banco precisar ser atualizado, baixe o certificado público em **Database Settings → SSL Configuration** no Supabase, substitua `deploy/supabase-ca.crt` e rode `sudo docker compose up -d --force-recreate app`. Se aparecer erro de TLS no navegador, confira o DNS público e os logs do Caddy.

```bash
sudo docker compose ps
sudo docker compose logs --tail=80 app caddy
```

[Reinício de contêineres](https://docs.docker.com/engine/containers/start-containers-automatically/) · [Pausas no Supabase](https://supabase.com/docs/guides/platform/free-project-pausing) · [Oracle Always Free](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)

## Dados e acesso

A autenticação é do Fined. O Supabase hospeda o PostgreSQL. O esquema `fined` fica separado, com permissões próprias. A aplicação usa o papel `fined_app`, que pode ler e gravar os dados necessários, mas não alterar o esquema. As rotas do Fined restringem cada lançamento e meta à conta que os criou. Mantenha o esquema `fined` fora da lista de esquemas expostos pela Data API.

O SQL inicial não importa o SQLite de instalações anteriores. Depois da instalação, o banco começa sem usuários, lançamentos ou metas. Os dados ficam no Supabase quando a VM ou os contêineres são reiniciados. A versão do esquema é registrada separadamente.

