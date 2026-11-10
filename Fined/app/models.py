import math
from datetime import date, datetime, timezone

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from werkzeug.security import check_password_hash, generate_password_hash

from . import db


def agora():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Usuario(db.Model):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(80))
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    senha_hash: Mapped[str] = mapped_column(String(255))
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)

    lancamentos: Mapped[list["Lancamento"]] = relationship(
        back_populates="usuario", cascade="all, delete-orphan"
    )
    metas: Mapped[list["Meta"]] = relationship(
        back_populates="usuario", cascade="all, delete-orphan"
    )

    def definir_senha(self, senha):
        self.senha_hash = generate_password_hash(senha)

    def confere_senha(self, senha):
        return check_password_hash(self.senha_hash, senha)


class LimiteAutenticacao(db.Model):
    __tablename__ = "limites_autenticacao"

    chave: Mapped[str] = mapped_column(String(64), primary_key=True)
    total: Mapped[int] = mapped_column(Integer)
    expira_em: Mapped[int] = mapped_column(Integer, index=True)


class SessaoAutenticacao(db.Model):
    __tablename__ = "sessoes_autenticacao"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"), index=True
    )
    expira_em: Mapped[datetime] = mapped_column(DateTime, index=True)


class Lancamento(db.Model):
    __tablename__ = "lancamentos"
    __table_args__ = (
        CheckConstraint("tipo IN ('receita', 'despesa')", name="ck_lancamentos_tipo"),
        CheckConstraint("valor_centavos > 0", name="ck_lancamentos_valor"),
        Index("ix_lancamentos_usuario_data", "usuario_id", "data"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"))
    tipo: Mapped[str] = mapped_column(String(7))
    valor_centavos: Mapped[int] = mapped_column(Integer)
    categoria: Mapped[str] = mapped_column(String(30))
    data: Mapped[date] = mapped_column(Date)
    descricao: Mapped[str | None] = mapped_column(String(120), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)

    usuario: Mapped["Usuario"] = relationship(back_populates="lancamentos")

    @property
    def valor_com_sinal(self):
        return self.valor_centavos if self.tipo == "receita" else -self.valor_centavos


class Meta(db.Model):
    __tablename__ = "metas"
    __table_args__ = (
        CheckConstraint("valor_alvo_centavos > 0", name="ck_metas_valor"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"), index=True
    )
    nome: Mapped[str] = mapped_column(String(60))
    valor_alvo_centavos: Mapped[int] = mapped_column(Integer)
    prazo: Mapped[date] = mapped_column(Date)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)

    usuario: Mapped["Usuario"] = relationship(back_populates="metas")
    contribuicoes: Mapped[list["Contribuicao"]] = relationship(
        back_populates="meta",
        cascade="all, delete-orphan",
        order_by=lambda: (Contribuicao.data.desc(), Contribuicao.id.desc()),
    )

    @property
    def guardado(self):
        return sum(c.valor_centavos for c in self.contribuicoes)

    @property
    def falta(self):
        return max(0, self.valor_alvo_centavos - self.guardado)

    @property
    def concluida(self):
        return self.guardado >= self.valor_alvo_centavos

    @property
    def percentual(self):
        return min(100, self.guardado * 100 // self.valor_alvo_centavos)

    def dias_restantes(self, hoje):
        return (self.prazo - hoje).days

    def sugestao_mensal(self, hoje):
        if self.concluida:
            return None
        dias = self.dias_restantes(hoje)
        if dias <= 0:
            return None
        meses = max(1, math.ceil(dias / 30.44))
        return math.ceil(self.falta / meses)


class Contribuicao(db.Model):
    __tablename__ = "contribuicoes"
    __table_args__ = (
        CheckConstraint("valor_centavos > 0", name="ck_contribuicoes_valor"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    meta_id: Mapped[int] = mapped_column(
        ForeignKey("metas.id", ondelete="CASCADE"), index=True
    )
    valor_centavos: Mapped[int] = mapped_column(Integer)
    data: Mapped[date] = mapped_column(Date)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)

    meta: Mapped["Meta"] = relationship(back_populates="contribuicoes")
