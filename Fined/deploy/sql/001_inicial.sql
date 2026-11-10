-- Execute como postgres em um projeto dedicado. Defina a senha com \password no psql.
BEGIN;

CREATE ROLE fined_owner NOLOGIN;
CREATE ROLE fined_app LOGIN;
GRANT fined_owner TO postgres;
CREATE SCHEMA fined AUTHORIZATION fined_owner;
ALTER ROLE fined_app SET search_path = pg_catalog, fined;
ALTER ROLE fined_app SET statement_timeout = '10s';

SET LOCAL ROLE fined_owner;
REVOKE ALL ON SCHEMA fined FROM PUBLIC, anon, authenticated, service_role;

CREATE TABLE fined.versao_schema (versao integer PRIMARY KEY);
INSERT INTO fined.versao_schema (versao) VALUES (1);

CREATE TABLE fined.usuarios (
    id serial PRIMARY KEY,
    nome varchar(80) NOT NULL,
    email varchar(160) NOT NULL UNIQUE,
    senha_hash varchar(255) NOT NULL,
    criado_em timestamp without time zone NOT NULL
);

CREATE TABLE fined.lancamentos (
    id serial PRIMARY KEY,
    usuario_id integer NOT NULL REFERENCES fined.usuarios (id) ON DELETE CASCADE,
    tipo varchar(7) NOT NULL,
    valor_centavos integer NOT NULL,
    categoria varchar(30) NOT NULL,
    data date NOT NULL,
    descricao varchar(120),
    criado_em timestamp without time zone NOT NULL,
    CONSTRAINT ck_lancamentos_tipo CHECK (tipo IN ('receita', 'despesa')),
    CONSTRAINT ck_lancamentos_valor CHECK (valor_centavos > 0)
);
CREATE INDEX ix_lancamentos_usuario_data ON fined.lancamentos (usuario_id, data);

CREATE TABLE fined.metas (
    id serial PRIMARY KEY,
    usuario_id integer NOT NULL REFERENCES fined.usuarios (id) ON DELETE CASCADE,
    nome varchar(60) NOT NULL,
    valor_alvo_centavos integer NOT NULL,
    prazo date NOT NULL,
    criado_em timestamp without time zone NOT NULL,
    CONSTRAINT ck_metas_valor CHECK (valor_alvo_centavos > 0)
);
CREATE INDEX ix_metas_usuario_id ON fined.metas (usuario_id);

CREATE TABLE fined.contribuicoes (
    id serial PRIMARY KEY,
    meta_id integer NOT NULL REFERENCES fined.metas (id) ON DELETE CASCADE,
    valor_centavos integer NOT NULL,
    data date NOT NULL,
    criado_em timestamp without time zone NOT NULL,
    CONSTRAINT ck_contribuicoes_valor CHECK (valor_centavos > 0)
);
CREATE INDEX ix_contribuicoes_meta_id ON fined.contribuicoes (meta_id);

CREATE TABLE fined.limites_autenticacao (
    chave varchar(64) PRIMARY KEY,
    total integer NOT NULL,
    expira_em integer NOT NULL
);
CREATE INDEX ix_limites_autenticacao_expira_em ON fined.limites_autenticacao (expira_em);

CREATE TABLE fined.sessoes_autenticacao (
    token_hash varchar(64) PRIMARY KEY,
    usuario_id integer NOT NULL REFERENCES fined.usuarios (id) ON DELETE CASCADE,
    expira_em timestamp without time zone NOT NULL
);
CREATE INDEX ix_sessoes_autenticacao_usuario_id ON fined.sessoes_autenticacao (usuario_id);
CREATE INDEX ix_sessoes_autenticacao_expira_em ON fined.sessoes_autenticacao (expira_em);

GRANT USAGE ON SCHEMA fined TO fined_app;
GRANT SELECT ON fined.versao_schema TO fined_app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA fined TO fined_app;

DO $$
DECLARE
    tabela text;
BEGIN
    FOREACH tabela IN ARRAY ARRAY[
        'usuarios', 'lancamentos', 'metas', 'contribuicoes',
        'limites_autenticacao', 'sessoes_autenticacao'
    ] LOOP
        EXECUTE format('REVOKE ALL ON fined.%I FROM PUBLIC, anon, authenticated, service_role', tabela);
        EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON fined.%I TO fined_app', tabela);
        EXECUTE format('ALTER TABLE fined.%I ENABLE ROW LEVEL SECURITY', tabela);
        EXECUTE format(
            'CREATE POLICY acesso_backend ON fined.%I TO fined_app USING (true) WITH CHECK (true)',
            tabela
        );
    END LOOP;
END
$$;

COMMIT;
