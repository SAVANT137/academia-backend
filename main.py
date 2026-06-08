
import base64
import os
import re
from datetime import date, datetime, timedelta
from calendar import monthrange
from io import BytesIO
from typing import Optional, Literal

import qrcode
import requests
from fastapi import FastAPI, HTTPException, Query, Body, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    inspect,
    text,
    or_,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

APP_TITLE = "Coliseu Fit API"
APP_VERSION = "5.2.4"

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./coliseu_fit.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

QR_CATRACA = os.getenv("QR_CATRACA", "CATRACA_ACADEMIA_01").strip()
ADMIN_LOGIN = os.getenv("ADMIN_LOGIN", "Coliseufit")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Coliseu_fit2026")
INFINITEPAY_HANDLE = os.getenv("INFINITEPAY_HANDLE", "indael").strip()

PAYMENT_LINK_MENSAL = os.getenv("PAYMENT_LINK_MENSAL", "https://link.infinitepay.io/aylen-65425645-v40/VC1D-JncUSFq47-125,00").strip()
PAYMENT_LINK_SEMESTRAL = os.getenv("PAYMENT_LINK_SEMESTRAL", "https://link.infinitepay.io/aylen-65425645-v40/VC1D-1HCUNRg7PL-720,00").strip()
PAYMENT_LINK_ANUAL = os.getenv("PAYMENT_LINK_ANUAL", "https://link.infinitepay.io/aylen-65425645-v40/VC1D-7fCwy6Ol2L-1320,00").strip()
PAYMENT_LINK_PROMOCIONAL = os.getenv("PAYMENT_LINK_PROMOCIONAL", "").strip()

MENSAL_VALOR = 125.0
SEMESTRAL_VALOR = 720.0
ANUAL_VALOR = 1320.0
PROMOCIONAL_VALOR_PADRAO = 80.90
PROMOCIONAL_DIAS_PADRAO = 30
DIARIA_VALOR = 35.0
GYMPASS_VALOR = 0.0
TOTAL_PASS_VALOR = 0.0

INFINITEPAY_CHECKOUT_URL = "https://api.checkout.infinitepay.io/links"
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://academia-backend-aksl.onrender.com").strip()
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://coliseufit26.netlify.app").strip()

PLANOS_FIXOS = {
    30: {"nome": "Mensal", "valor": MENSAL_VALOR},
    180: {"nome": "Semestral", "valor": SEMESTRAL_VALOR},
    365: {"nome": "Anual", "valor": ANUAL_VALOR},
}

class ConfigDB(Base):
    __tablename__ = "configuracoes"
    id = Column(Integer, primary_key=True, index=True)
    chave = Column(String, unique=True, nullable=False)
    valor = Column(Text, nullable=False)


class AlunoDB(Base):
    __tablename__ = "alunos"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    telefone = Column(String, nullable=True)
    cpf = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, nullable=True)
    sexo = Column(String, nullable=True)

    status_manual = Column(String, default="pendente")  # pendente / em_dia / atrasado / inativo
    plano_nome = Column(String, nullable=True)
    valor_plano = Column(Float, default=0.0)
    desconto_percentual = Column(Float, default=0.0)
    desconto_valor = Column(Float, default=0.0)
    vencimento = Column(String, nullable=True)  # YYYY-MM-DD
    data_inicio_plano = Column(String, nullable=True)  # YYYY-MM-DD
    dia_vencimento_fixo = Column(Integer, nullable=True)  # 1..31

    foto_url = Column(Text, nullable=True)
    foto_base64 = Column(Text, nullable=True)
    data_cadastro = Column(String, nullable=True)

    status_cliente_raw = Column(String, nullable=True)
    status_contrato_raw = Column(String, nullable=True)

    valor_personalizado = Column(Float, nullable=True)
    beneficio_ativo = Column(Boolean, default=True)
    valor_padrao_plano = Column(Float, nullable=True)
    origem_valor = Column(String, nullable=True)
    valor_final_manual = Column(Float, nullable=True)
    valor_final_manual_ativo = Column(Boolean, default=False)
    pre_cadastro_origem = Column(Boolean, default=False)
    aprovado_em = Column(DateTime, nullable=True)
    premium_admin = Column(Boolean, default=False)
    acesso_livre = Column(Boolean, default=False)
    pode_acessar_adm = Column(Boolean, default=False)
    pode_atender_chat = Column(Boolean, default=False)
    juros_perdoado_vencimento = Column(String, nullable=True)
    juros_perdoado_em = Column(DateTime, nullable=True)
    juros_perdoado_por = Column(String, nullable=True)
    deletado = Column(Boolean, default=False)
    deletado_em = Column(DateTime, nullable=True)
    cpf_original = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

class PagamentoDB(Base):
    __tablename__ = "pagamentos"
    id = Column(Integer, primary_key=True, index=True)
    aluno_id = Column(Integer, ForeignKey("alunos.id"), nullable=False, index=True)
    plano_nome = Column(String, nullable=False)
    valor = Column(Float, default=0.0)
    dias = Column(Integer, nullable=False)
    status = Column(String, default="pago")
    origem = Column(String, default="manual")
    link_pagamento = Column(Text, nullable=True)
    order_nsu = Column(String, nullable=True, index=True)
    data_pagamento = Column(DateTime, default=datetime.utcnow)
    vencimento_anterior = Column(String, nullable=True)
    novo_vencimento = Column(String, nullable=True)
    reembolsado_em = Column(DateTime, nullable=True)
    pagamento_reembolsado_id = Column(Integer, nullable=True)
    observacao = Column(Text, nullable=True)
    tipo_evento = Column(String, nullable=True)
    valor_juros = Column(Float, default=0.0)

    aluno = relationship("AlunoDB")

class AvisoDB(Base):
    __tablename__ = "avisos"
    id = Column(Integer, primary_key=True, index=True)
    titulo = Column(String, nullable=False)
    mensagem = Column(Text, nullable=False)
    imagem_base64 = Column(Text, nullable=True)
    data = Column(DateTime, default=datetime.utcnow)

class AvisoLeituraDB(Base):
    __tablename__ = "avisos_leituras"
    id = Column(Integer, primary_key=True, index=True)
    aviso_id = Column(Integer, ForeignKey("avisos.id"), nullable=False, index=True)
    aluno_id = Column(Integer, ForeignKey("alunos.id"), nullable=False, index=True)
    lido = Column(Boolean, default=True)
    data = Column(DateTime, default=datetime.utcnow)

class TreinoDB(Base):
    __tablename__ = "treinos"
    id = Column(Integer, primary_key=True, index=True)
    aluno_id = Column(Integer, ForeignKey("alunos.id"), nullable=False, index=True)
    categoria = Column(String, nullable=False)  # A/B/C/D/E
    titulo = Column(String, nullable=False)
    descricao = Column(Text, nullable=True)
    exercicios = Column(Text, nullable=True)  # texto puro separado por quebras de linha
    video_url = Column(Text, nullable=True)


class EntradaDB(Base):
    __tablename__ = "entradas"
    id = Column(Integer, primary_key=True, index=True)
    aluno_id = Column(Integer, ForeignKey("alunos.id"), nullable=False, index=True)
    nome = Column(Text, nullable=False)
    status = Column(Text, nullable=False)  # liberado / bloqueado
    motivo = Column(Text, nullable=False)
    data_entrada = Column(DateTime, default=datetime.utcnow)


class LiberacaoCatracaDB(Base):
    __tablename__ = "liberacoes_catraca"

    id = Column(Integer, primary_key=True, index=True)
    aluno_id = Column(Integer, ForeignKey("alunos.id"), nullable=False, index=True)
    cpf = Column(Text, nullable=True)
    nome = Column(Text, nullable=True)

    status = Column(Text, default="pendente", index=True)
    # pendente | em_execucao | executado | erro | negado

    segundos = Column(Integer, default=5)
    sentido = Column(Text, default="ambos")
    motivo = Column(Text, nullable=True)
    erro = Column(Text, nullable=True)

    criado_em = Column(DateTime, default=datetime.utcnow)
    executado_em = Column(DateTime, nullable=True)
    atualizado_em = Column(DateTime, default=datetime.utcnow)

    aluno = relationship("AlunoDB")


class GympassSolicitacaoDB(Base):
    __tablename__ = "gympass_solicitacoes"

    id = Column(Integer, primary_key=True, index=True)
    aluno_id = Column(Integer, ForeignKey("alunos.id"), nullable=False, index=True)
    cpf = Column(Text, nullable=True)
    nome = Column(Text, nullable=True)
    status = Column(Text, default="solicitado", index=True)
    # solicitado | liberado | negado | expirado
    usado_no_dia = Column(Integer, default=0)
    tipo_pass = Column(Text, default="Gympass", index=True)
    liberado_por_id = Column(Integer, nullable=True)
    liberado_por_nome = Column(Text, nullable=True)
    observacao = Column(Text, nullable=True)
    criado_em = Column(DateTime, default=datetime.utcnow, index=True)
    liberado_em = Column(DateTime, nullable=True)
    atualizado_em = Column(DateTime, default=datetime.utcnow)

    aluno = relationship("AlunoDB")


class PreCadastroAlunoDB(Base):
    __tablename__ = "pre_cadastros_alunos"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    telefone = Column(String, nullable=True)
    cpf = Column(String, unique=True, nullable=False, index=True)
    status = Column(String, default="aguardando_aprovacao", index=True)
    observacao = Column(Text, nullable=True)
    criado_em = Column(DateTime, default=datetime.utcnow, index=True)
    aprovado_em = Column(DateTime, nullable=True)
    recusado_em = Column(DateTime, nullable=True)


class PromocaoDB(Base):
    __tablename__ = "promocoes"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    tipo = Column(String, nullable=False)  # indicacao | novos_membros
    descricao = Column(Text, nullable=True)
    desconto_valor = Column(Float, default=0.0)
    ativa = Column(Boolean, default=True, index=True)
    observacao = Column(Text, nullable=True)
    criado_em = Column(DateTime, default=datetime.utcnow, index=True)
    atualizado_em = Column(DateTime, default=datetime.utcnow)


class PromocaoAplicacaoDB(Base):
    __tablename__ = "promocoes_aplicacoes"

    id = Column(Integer, primary_key=True, index=True)
    promocao_id = Column(Integer, ForeignKey("promocoes.id"), nullable=False, index=True)
    aluno_id = Column(Integer, ForeignKey("alunos.id"), nullable=False, index=True)
    valor_desconto = Column(Float, default=0.0)
    observacao = Column(Text, nullable=True)
    criado_em = Column(DateTime, default=datetime.utcnow, index=True)

    promocao = relationship("PromocaoDB")
    aluno = relationship("AlunoDB")



class ConversaChatDB(Base):
    __tablename__ = "conversas_chat"
    id = Column(Integer, primary_key=True, index=True)
    aluno_id = Column(Integer, ForeignKey("alunos.id"), nullable=False, index=True)
    criada_em = Column(DateTime, default=datetime.utcnow)
    atualizada_em = Column(DateTime, default=datetime.utcnow)
    ultima_mensagem_em = Column(DateTime, nullable=True)
    status = Column(String, default="aberta")
    mensagens_nao_lidas_professor = Column(Integer, default=0)
    mensagens_nao_lidas_aluno = Column(Integer, default=0)
    aluno = relationship("AlunoDB")

class MensagemChatDB(Base):
    __tablename__ = "mensagens_chat"
    id = Column(Integer, primary_key=True, index=True)
    conversa_id = Column(Integer, ForeignKey("conversas_chat.id"), nullable=False, index=True)
    aluno_id = Column(Integer, ForeignKey("alunos.id"), nullable=False, index=True)
    remetente_tipo = Column(String, nullable=False)  # aluno / professor / adm
    remetente_id = Column(Integer, nullable=True)
    remetente_nome = Column(String, nullable=True)
    mensagem = Column(Text, nullable=False)
    criada_em = Column(DateTime, default=datetime.utcnow)
    lida_em = Column(DateTime, nullable=True)
    status = Column(String, default="enviada")
    conversa = relationship("ConversaChatDB")

def ensure_schema_updates():
    """
    Mantém o banco compatível com o app mesmo quando o PostgreSQL é recriado vazio
    ou quando a importação cria apenas a tabela alunos. Isso evita erro 500 em
    /avisos, /treinos, pagamentos e catraca por tabela ausente.
    """
    insp = inspect(engine)
    is_postgres = str(DATABASE_URL).startswith("postgres")

    # 1) Garante a tabela principal primeiro, pois várias outras têm FK para alunos.
    if "alunos" not in insp.get_table_names():
        AlunoDB.__table__.create(bind=engine, checkfirst=True)
        insp = inspect(engine)

    # 2) Garante colunas esperadas na tabela alunos importada pelo SQL.
    if "alunos" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("alunos")}
        alter_cmds = []

        expected_columns = {
            "email": "ALTER TABLE alunos ADD COLUMN email VARCHAR(255)",
            "sexo": "ALTER TABLE alunos ADD COLUMN sexo VARCHAR(50)",
            "status_manual": "ALTER TABLE alunos ADD COLUMN status_manual VARCHAR(20) DEFAULT 'pendente'",
            "plano_nome": "ALTER TABLE alunos ADD COLUMN plano_nome VARCHAR(100)",
            "valor_plano": "ALTER TABLE alunos ADD COLUMN valor_plano FLOAT DEFAULT 0",
            "desconto_percentual": "ALTER TABLE alunos ADD COLUMN desconto_percentual FLOAT DEFAULT 0",
            "desconto_valor": "ALTER TABLE alunos ADD COLUMN desconto_valor FLOAT DEFAULT 0",
            "vencimento": "ALTER TABLE alunos ADD COLUMN vencimento VARCHAR(20)",
            "data_inicio_plano": "ALTER TABLE alunos ADD COLUMN data_inicio_plano VARCHAR(20)",
            "dia_vencimento_fixo": "ALTER TABLE alunos ADD COLUMN dia_vencimento_fixo INTEGER",
            "foto_url": "ALTER TABLE alunos ADD COLUMN foto_url TEXT",
            "foto_base64": "ALTER TABLE alunos ADD COLUMN foto_base64 TEXT",
            "data_cadastro": "ALTER TABLE alunos ADD COLUMN data_cadastro VARCHAR(50)",
            "status_cliente_raw": "ALTER TABLE alunos ADD COLUMN status_cliente_raw VARCHAR(50)",
            "status_contrato_raw": "ALTER TABLE alunos ADD COLUMN status_contrato_raw VARCHAR(50)",
            "valor_personalizado": "ALTER TABLE alunos ADD COLUMN valor_personalizado FLOAT",
            "beneficio_ativo": "ALTER TABLE alunos ADD COLUMN beneficio_ativo BOOLEAN DEFAULT TRUE",
            "valor_padrao_plano": "ALTER TABLE alunos ADD COLUMN valor_padrao_plano FLOAT",
            "origem_valor": "ALTER TABLE alunos ADD COLUMN origem_valor VARCHAR(50)",
            "valor_final_manual": "ALTER TABLE alunos ADD COLUMN valor_final_manual FLOAT",
            "valor_final_manual_ativo": "ALTER TABLE alunos ADD COLUMN valor_final_manual_ativo BOOLEAN DEFAULT FALSE",
            "pre_cadastro_origem": "ALTER TABLE alunos ADD COLUMN pre_cadastro_origem BOOLEAN DEFAULT FALSE",
            "aprovado_em": "ALTER TABLE alunos ADD COLUMN aprovado_em TIMESTAMP",
            "premium_admin": "ALTER TABLE alunos ADD COLUMN premium_admin BOOLEAN DEFAULT FALSE",
            "acesso_livre": "ALTER TABLE alunos ADD COLUMN acesso_livre BOOLEAN DEFAULT FALSE",
            "pode_acessar_adm": "ALTER TABLE alunos ADD COLUMN pode_acessar_adm BOOLEAN DEFAULT FALSE",
            "pode_atender_chat": "ALTER TABLE alunos ADD COLUMN pode_atender_chat BOOLEAN DEFAULT FALSE",
            "juros_perdoado_vencimento": "ALTER TABLE alunos ADD COLUMN juros_perdoado_vencimento VARCHAR(20)",
            "juros_perdoado_em": "ALTER TABLE alunos ADD COLUMN juros_perdoado_em TIMESTAMP",
            "juros_perdoado_por": "ALTER TABLE alunos ADD COLUMN juros_perdoado_por VARCHAR(120)",
            "gympass_acessos_dia": "ALTER TABLE alunos ADD COLUMN gympass_acessos_dia INTEGER DEFAULT 0",
            "deletado": "ALTER TABLE alunos ADD COLUMN deletado BOOLEAN DEFAULT FALSE",
            "deletado_em": "ALTER TABLE alunos ADD COLUMN deletado_em TIMESTAMP",
            "cpf_original": "ALTER TABLE alunos ADD COLUMN cpf_original VARCHAR(50)",
            "created_at": "ALTER TABLE alunos ADD COLUMN created_at TIMESTAMP",
            "updated_at": "ALTER TABLE alunos ADD COLUMN updated_at TIMESTAMP",
        }

        for col_name, cmd in expected_columns.items():
            if col_name not in cols:
                alter_cmds.append(cmd)

        if alter_cmds:
            with engine.begin() as conn:
                for cmd in alter_cmds:
                    try:
                        conn.execute(text(cmd))
                    except Exception:
                        # Se uma coluna foi criada por outro processo entre o inspect e o ALTER,
                        # não derruba o deploy.
                        pass

    # 3) Cria tabelas auxiliares ausentes em ordem segura.
    # Não usamos Base.metadata.create_all em banco parcialmente migrado para evitar
    # conflitos de índice em bancos antigos; criamos só o que estiver faltando.
    insp = inspect(engine)
    table_names = set(insp.get_table_names())
    for model in [ConfigDB, PagamentoDB, AvisoDB, AvisoLeituraDB, TreinoDB, EntradaDB, LiberacaoCatracaDB, GympassSolicitacaoDB, PreCadastroAlunoDB, PromocaoDB, PromocaoAplicacaoDB, ConversaChatDB, MensagemChatDB]:
        if model.__tablename__ not in table_names:
            try:
                model.__table__.create(bind=engine, checkfirst=True)
            except Exception:
                # Mantém o deploy vivo mesmo que alguma tabela opcional falhe;
                # rotas de manutenção retornam vazio/0 quando necessário.
                pass
            insp = inspect(engine)
            table_names = set(insp.get_table_names())

    # 4) Ajusta colunas de pagamentos, se a tabela já existia de uma versão antiga.
    insp = inspect(engine)
    if "pagamentos" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("pagamentos")}
        alter_cmds = []

        expected_columns = {
            "plano_nome": "ALTER TABLE pagamentos ADD COLUMN plano_nome VARCHAR(100)",
            "valor": "ALTER TABLE pagamentos ADD COLUMN valor FLOAT DEFAULT 0",
            "dias": "ALTER TABLE pagamentos ADD COLUMN dias INTEGER DEFAULT 30",
            "status": "ALTER TABLE pagamentos ADD COLUMN status VARCHAR(30) DEFAULT 'pendente'",
            "origem": "ALTER TABLE pagamentos ADD COLUMN origem VARCHAR(50) DEFAULT 'manual'",
            "link_pagamento": "ALTER TABLE pagamentos ADD COLUMN link_pagamento TEXT",
            "order_nsu": "ALTER TABLE pagamentos ADD COLUMN order_nsu VARCHAR(120)",
            "data_pagamento": "ALTER TABLE pagamentos ADD COLUMN data_pagamento TIMESTAMP",
            "vencimento_anterior": "ALTER TABLE pagamentos ADD COLUMN vencimento_anterior VARCHAR(30)",
            "novo_vencimento": "ALTER TABLE pagamentos ADD COLUMN novo_vencimento VARCHAR(30)",
            "reembolsado_em": "ALTER TABLE pagamentos ADD COLUMN reembolsado_em TIMESTAMP",
            "pagamento_reembolsado_id": "ALTER TABLE pagamentos ADD COLUMN pagamento_reembolsado_id INTEGER",
            "observacao": "ALTER TABLE pagamentos ADD COLUMN observacao TEXT",
            "tipo_evento": "ALTER TABLE pagamentos ADD COLUMN tipo_evento VARCHAR(80)",
            "valor_juros": "ALTER TABLE pagamentos ADD COLUMN valor_juros FLOAT DEFAULT 0",
        }

        for col_name, cmd in expected_columns.items():
            if col_name not in cols:
                alter_cmds.append(cmd)

        with engine.begin() as conn:
            for cmd in alter_cmds:
                try:
                    conn.execute(text(cmd))
                except Exception:
                    pass

            if is_postgres:
                safe_alters = [
                    "ALTER TABLE pagamentos ALTER COLUMN plano_nome TYPE VARCHAR(100)",
                    "ALTER TABLE pagamentos ALTER COLUMN status TYPE VARCHAR(30)",
                    "ALTER TABLE pagamentos ALTER COLUMN origem TYPE VARCHAR(50)",
                    "ALTER TABLE pagamentos ALTER COLUMN link_pagamento TYPE TEXT",
                    "ALTER TABLE pagamentos ALTER COLUMN order_nsu TYPE VARCHAR(120)",
                    "ALTER TABLE pagamentos ALTER COLUMN vencimento_anterior TYPE VARCHAR(30)",
                    "ALTER TABLE pagamentos ALTER COLUMN novo_vencimento TYPE VARCHAR(30)",
                    "ALTER TABLE pagamentos ALTER COLUMN observacao TYPE TEXT",
                ]
                for cmd in safe_alters:
                    try:
                        conn.execute(text(cmd))
                    except Exception:
                        pass

    # 5) Ajustes da tabela de entradas: evita erro de varchar curto em motivo/status/nome.
    insp = inspect(engine)
    if "entradas" in insp.get_table_names() and is_postgres:
        with engine.begin() as conn:
            for cmd in [
                "ALTER TABLE public.entradas ALTER COLUMN nome TYPE TEXT",
                "ALTER TABLE public.entradas ALTER COLUMN status TYPE TEXT",
                "ALTER TABLE public.entradas ALTER COLUMN motivo TYPE TEXT",
            ]:
                try:
                    conn.execute(text(cmd))
                except Exception:
                    pass

    # 6) Ajustes da tabela usada pelo agente local da catraca Henry.
    insp = inspect(engine)
    if "liberacoes_catraca" in insp.get_table_names() and is_postgres:
        with engine.begin() as conn:
            for cmd in [
                "ALTER TABLE public.liberacoes_catraca ALTER COLUMN cpf TYPE TEXT",
                "ALTER TABLE public.liberacoes_catraca ALTER COLUMN nome TYPE TEXT",
                "ALTER TABLE public.liberacoes_catraca ALTER COLUMN status TYPE TEXT",
                "ALTER TABLE public.liberacoes_catraca ALTER COLUMN sentido TYPE TEXT",
                "ALTER TABLE public.liberacoes_catraca ALTER COLUMN motivo TYPE TEXT",
                "ALTER TABLE public.liberacoes_catraca ALTER COLUMN erro TYPE TEXT",
            ]:
                try:
                    conn.execute(text(cmd))
                except Exception:
                    pass

    # 7) Ajustes para controle separado de Gympass e Total Pass.
    insp = inspect(engine)
    if "gympass_solicitacoes" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("gympass_solicitacoes")}
        with engine.begin() as conn:
            if "tipo_pass" not in cols:
                try:
                    conn.execute(text("ALTER TABLE gympass_solicitacoes ADD COLUMN tipo_pass TEXT DEFAULT 'Gympass'"))
                except Exception:
                    pass
            if is_postgres:
                for cmd in [
                    "ALTER TABLE public.gympass_solicitacoes ALTER COLUMN cpf TYPE TEXT",
                    "ALTER TABLE public.gympass_solicitacoes ALTER COLUMN nome TYPE TEXT",
                    "ALTER TABLE public.gympass_solicitacoes ALTER COLUMN status TYPE TEXT",
                    "ALTER TABLE public.gympass_solicitacoes ALTER COLUMN observacao TYPE TEXT",
                    "ALTER TABLE public.gympass_solicitacoes ALTER COLUMN tipo_pass TYPE TEXT",
                ]:
                    try:
                        conn.execute(text(cmd))
                    except Exception:
                        pass

ensure_schema_updates()

def init_database():
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())
    if not existing_tables:
        Base.metadata.create_all(bind=engine)
        return

    # Banco já existente: NÃO chamamos Base.metadata.create_all para tabelas antigas,
    # porque o PostgreSQL pode tentar recriar índices já existentes
    # (ex.: ix_treinos_aluno_id).
    # As migrações necessárias para entradas/liberacoes_catraca já foram feitas
    # em ensure_schema_updates().
    return

init_database()

app = FastAPI(title=APP_TITLE, version=APP_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------
# Models
# ----------------------
class AdminLoginBody(BaseModel):
    login: str
    senha: str

class AlunoCreate(BaseModel):
    nome: str
    telefone: Optional[str] = None
    cpf: str
    email: Optional[str] = None
    sexo: Optional[str] = None
    plano_nome: Optional[str] = None
    dias_plano: Optional[int] = None
    desconto_percentual: Optional[float] = 0.0
    desconto_valor: Optional[float] = 0.0
    premium_admin: Optional[bool] = False
    acesso_livre: Optional[bool] = False
    pode_acessar_adm: Optional[bool] = False
    data_inicio_plano: Optional[str] = None
    vencimento: Optional[str] = None
    dia_vencimento_fixo: Optional[int] = None

class AlunoAdminUpdate(BaseModel):
    nome: str
    telefone: Optional[str] = None
    cpf: str
    email: Optional[str] = None
    sexo: Optional[str] = None
    plano_nome: Optional[str] = None
    valor_plano: Optional[float] = None
    desconto_percentual: Optional[float] = None
    desconto_valor: Optional[float] = None
    vencimento: Optional[str] = None
    data_inicio_plano: Optional[str] = None
    dia_vencimento_fixo: Optional[int] = None
    status_manual: Optional[Literal["pendente", "em_dia", "atrasado", "inativo"]] = None
    premium_admin: Optional[bool] = None
    acesso_livre: Optional[bool] = None
    pode_acessar_adm: Optional[bool] = None

class AlunoSelfUpdate(BaseModel):
    nome: str
    telefone: Optional[str] = None

class FotoAlunoBody(BaseModel):
    foto_url: Optional[str] = None
    foto_base64: Optional[str] = None

class AvisoCreate(BaseModel):
    titulo: str
    mensagem: str
    imagem_base64: Optional[str] = None
    image_base64: Optional[str] = None

class AvisoLidoBody(BaseModel):
    aluno_id: int

class TreinoCreate(BaseModel):
    aluno_id: int
    categoria: Literal["A", "B", "C", "D", "E"]
    titulo: str
    descricao: Optional[str] = None
    exercicios: Optional[str] = None
    video_url: Optional[str] = None


class DescontoBody(BaseModel):
    # Novo padrão: desconto em reais. Mantemos desconto_percentual só para compatibilidade com versões antigas do app.
    desconto_valor: Optional[float] = Field(0, ge=0)
    desconto_percentual: Optional[float] = Field(None, ge=0, le=100)

class PagamentoBody(BaseModel):
    plano: Literal["atual", "mensal", "semestral", "anual", "promocional", "diaria", "gympass", "total_pass", "total pass", "totalpass"]
    valor: Optional[float] = None
    dias: Optional[int] = None
    origem: Literal["manual", "aluno_link"] = "manual"

class EntradaBody(BaseModel):
    codigo_qr: str

class PromocionalConfigBody(BaseModel):
    valor: float = Field(..., gt=0)
    dias: int = Field(..., gt=0)

class PaymentLinksBody(BaseModel):
    mensal: Optional[str] = None
    semestral: Optional[str] = None
    anual: Optional[str] = None
    promocional: Optional[str] = None

class CriarPagamentoCheckoutBody(BaseModel):
    aluno_id: int
    dias: Optional[int] = None
    valor: Optional[float] = None
    plano_nome: Optional[str] = None

class GympassResponderBody(BaseModel):
    liberado_por_id: Optional[int] = None
    liberado_por_nome: Optional[str] = None
    observacao: Optional[str] = None

class ReembolsoBody(BaseModel):
    observacao: Optional[str] = None
    usuario_admin: Optional[str] = None

class PreCadastroCreate(BaseModel):
    nome: str
    telefone: Optional[str] = None
    cpf: str

class PreCadastroAprovarBody(BaseModel):
    plano_nome: Optional[str] = "Mensal"
    dias_plano: Optional[int] = 30
    desconto_valor: Optional[float] = 0.0
    valor_final_manual: Optional[float] = None
    data_inicio_plano: Optional[str] = None
    vencimento: Optional[str] = None
    dia_vencimento_fixo: Optional[int] = None
    premium_admin: Optional[bool] = False
    acesso_livre: Optional[bool] = False
    pode_acessar_adm: Optional[bool] = False

class PromocaoCreate(BaseModel):
    nome: str
    tipo: Literal["indicacao", "novos_membros"]
    descricao: Optional[str] = None
    desconto_valor: float = Field(0, ge=0)
    ativa: Optional[bool] = True
    aluno_indicou_id: Optional[int] = None
    observacao: Optional[str] = None

class PromocaoUpdate(BaseModel):
    nome: Optional[str] = None
    tipo: Optional[Literal["indicacao", "novos_membros"]] = None
    descricao: Optional[str] = None
    desconto_valor: Optional[float] = Field(None, ge=0)
    ativa: Optional[bool] = None
    observacao: Optional[str] = None

class ValorManualBody(BaseModel):
    valor_final_manual: Optional[float] = Field(None, ge=0)
    ativo: bool = True
    observacao: Optional[str] = None


class RetirarJurosBody(BaseModel):
    usuario_admin: Optional[str] = "ADM"
    observacao: Optional[str] = "Juros retirado manualmente pelo administrador"

class ChatMensagemBody(BaseModel):
    aluno_id: Optional[int] = None
    professor_id: Optional[int] = None
    remetente_tipo: Optional[str] = None
    mensagem: str

class ProfessorChatPermissaoBody(BaseModel):
    pode_atender_chat: bool

# ----------------------
# Helpers
# ----------------------
def hoje() -> date:
    return date.today()

def hoje_str() -> str:
    return hoje().strftime("%Y-%m-%d")

def agora_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def only_digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")

def apenas_digitos(value: Optional[str]) -> str:
    return only_digits(value or "")

def validar_cpf(cpf: str) -> bool:
    cpf = only_digits(cpf)
    if len(cpf) != 11:
        return False
    if cpf == cpf[0] * 11:
        return False

    soma = sum(int(cpf[i]) * (10 - i) for i in range(9))
    dig1 = (soma * 10 % 11) % 10

    soma = sum(int(cpf[i]) * (11 - i) for i in range(10))
    dig2 = (soma * 10 % 11) % 10

    return dig1 == int(cpf[9]) and dig2 == int(cpf[10])

def parse_date_safe(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    # Aceita YYYY-MM-DD, timestamp e também DD/MM/YYYY vindo do ADM.
    candidatos = [raw[:10], raw]
    for item in candidatos:
        for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(item[:10], fmt).date()
            except Exception:
                pass
    return None

def normalizar_data_texto(value: Optional[str]) -> Optional[str]:
    data = parse_date_safe(value)
    return data.strftime("%Y-%m-%d") if data else None

def clamp_dia_vencimento(value: Optional[int]) -> Optional[int]:
    if value is None:
        return None
    try:
        dia = int(value)
    except Exception:
        return None
    return max(1, min(31, dia))

def meses_por_plano_dias(dias: Optional[int], plano_nome: Optional[str] = None) -> int:
    nome = (plano_nome or "").strip().lower()
    d = int(dias or 30)
    if plano_pass_tipo(nome) or d <= 0:
        return 0
    if "diária" in nome or "diaria" in nome or d <= 1:
        return 0
    if "anual" in nome or d >= 365:
        return 12
    if "sem" in nome or d >= 180:
        return 6
    return 1

def data_com_dia_fixo(ano: int, mes: int, dia_fixo: int) -> date:
    ultimo = monthrange(ano, mes)[1]
    return date(ano, mes, min(int(dia_fixo), ultimo))

def adicionar_meses_com_dia_fixo(base: date, meses: int, dia_fixo: int) -> date:
    total = base.month - 1 + int(meses)
    ano = base.year + total // 12
    mes = total % 12 + 1
    return data_com_dia_fixo(ano, mes, dia_fixo)

def inferir_dia_vencimento_fixo(aluno: AlunoDB) -> int:
    dia = clamp_dia_vencimento(getattr(aluno, "dia_vencimento_fixo", None))
    if dia:
        return dia
    venc = parse_date_safe(getattr(aluno, "vencimento", None))
    if venc:
        return venc.day
    inicio = parse_date_safe(getattr(aluno, "data_inicio_plano", None))
    if inicio:
        return inicio.day
    return hoje().day

def calcular_novo_vencimento_fixo(aluno: AlunoDB, dias: Optional[int], plano_nome: Optional[str] = None) -> str:
    """
    Calcula renovação sem mudar o dia fixo.
    Usa o vencimento atual como base; se estiver muito antigo, avança ciclos
    mantendo o dia fixo até regularizar o aluno em data atual/futura.
    """
    nome_plano = (plano_nome or "").strip().lower()
    if "diária" in nome_plano or "diaria" in nome_plano or int(dias or 0) <= 1:
        return hoje().strftime("%Y-%m-%d")
    if plano_pass_tipo(nome_plano):
        return None
    meses = meses_por_plano_dias(dias, plano_nome)
    dia_fixo = inferir_dia_vencimento_fixo(aluno)
    base = parse_date_safe(getattr(aluno, "vencimento", None)) or hoje()
    novo = adicionar_meses_com_dia_fixo(base, meses, dia_fixo)
    # Se o aluno ficou mais de um ciclo atrasado, regulariza para o próximo ciclo útil.
    seguranca = 0
    while novo < hoje() and seguranca < 48:
        novo = adicionar_meses_com_dia_fixo(novo, meses, dia_fixo)
        seguranca += 1
    return novo.strftime("%Y-%m-%d")

def dias_atraso(vencimento: Optional[str]) -> int:
    venc = parse_date_safe(vencimento)
    if not venc:
        return 0
    return (hoje() - venc).days

def dias_uteis_atraso(vencimento: Optional[str]) -> int:
    venc = parse_date_safe(vencimento)
    if not venc:
        return 0
    inicio = venc + timedelta(days=1)
    fim = hoje()
    if fim < inicio:
        return 0
    total = 0
    cursor = inicio
    while cursor <= fim:
        if cursor.weekday() < 5:
            total += 1
        cursor += timedelta(days=1)
    return total

def juros_atraso_aluno(aluno: AlunoDB) -> float:
    """Juros por atraso: 3 dias úteis sem juros; depois R$ 1/dia útil, máximo R$ 5.
    Acesso continua bloqueado assim que vence; esta regra altera apenas o valor cobrado.
    Se o ADM perdoar juros para o vencimento atual, retorna 0 até o aluno renovar.
    """
    if aluno_premium_admin(aluno) or aluno_acesso_livre(aluno):
        return 0.0
    plano = (getattr(aluno, "plano_nome", None) or "").strip().lower()
    if plano_pass_tipo(plano):
        return 0.0
    vencimento = getattr(aluno, "vencimento", None)
    if getattr(aluno, "juros_perdoado_vencimento", None) and str(aluno.juros_perdoado_vencimento) == str(vencimento):
        return 0.0
    uteis = dias_uteis_atraso(vencimento)
    dias_com_juros = max(0, uteis - 3)
    return round(min(dias_com_juros, 5) * 1.0, 2)


def aluno_deve_inativar_por_atraso(aluno: AlunoDB) -> bool:
    """Aluno comum vira inativo após 30 dias corridos de atraso.
    Não se aplica a Professor/Premium, Acesso Livre, Gympass ou ADM/super admin.
    """
    if not aluno:
        return False
    if aluno_premium_admin(aluno) or aluno_acesso_livre(aluno) or aluno_super_admin(aluno):
        return False
    plano = (getattr(aluno, "plano_nome", None) or "").strip().lower()
    if plano_pass_tipo(plano):
        return False
    venc = parse_date_safe(getattr(aluno, "vencimento", None))
    if not venc:
        return False
    return (hoje() - venc).days >= 30


def processar_inativacao_por_atraso(db, aluno: AlunoDB) -> bool:
    """Marca aluno comum como inativo e remove condições comerciais especiais.
    Mantém histórico de pagamentos e cria um registro/auditoria em pagamentos.
    Retorna True se mudou algo.
    """
    if not aluno_deve_inativar_por_atraso(aluno):
        return False
    if (getattr(aluno, "status_manual", "") or "").lower() == "inativo" and not beneficio_ativo_aluno(aluno):
        return False

    desconto_anterior = float(getattr(aluno, "desconto_valor", 0) or 0)
    valor_manual_anterior = float(getattr(aluno, "valor_final_manual", 0) or 0) if getattr(aluno, "valor_final_manual", None) is not None else None
    valor_personalizado_anterior = float(getattr(aluno, "valor_personalizado", 0) or 0) if getattr(aluno, "valor_personalizado", None) else None
    valor_anterior = valor_cobrado_aluno(db, aluno, aluno.plano_nome)

    base_atual = float(aluno.valor_padrao_plano or 0) or valor_base_plano_nome(db, aluno.plano_nome)
    aluno.status_manual = "inativo"
    aluno.status_cliente_raw = "Inativo automático"
    aluno.status_contrato_raw = "inativo_30_dias_atraso"
    aluno.desconto_percentual = 0.0
    aluno.desconto_valor = 0.0
    aluno.valor_personalizado = None
    aluno.valor_final_manual = None
    aluno.valor_final_manual_ativo = False
    aluno.beneficio_ativo = False
    aluno.valor_plano = base_atual
    aluno.valor_padrao_plano = base_atual
    aluno.updated_at = datetime.utcnow()

    auditoria = PagamentoDB(
        aluno_id=aluno.id,
        plano_nome=aluno.plano_nome or "Inativação",
        valor=0.0,
        dias=0,
        status="inativacao_automatica",
        origem="sistema",
        data_pagamento=datetime.utcnow(),
        vencimento_anterior=aluno.vencimento,
        novo_vencimento=aluno.vencimento,
        observacao=(
            "Aluno inativado automaticamente após 30 dias de atraso. "
            f"Condições especiais removidas. Desconto anterior: R$ {desconto_anterior:.2f}; "
            f"valor manual anterior: {valor_manual_anterior}; valor personalizado anterior: {valor_personalizado_anterior}; "
            f"valor anterior calculado: R$ {valor_anterior:.2f}."
        ),
        tipo_evento="inativacao_automatica",
        valor_juros=juros_atraso_aluno(aluno),
    )
    db.add(auditoria)
    return True

def plano_pass_tipo(plano_nome: Optional[str]) -> Optional[str]:
    nome = (plano_nome or "").strip().lower().replace("_", " ").replace("-", " ")
    if "total" in nome and "pass" in nome:
        return "Total Pass"
    if "gympass" in nome or "gym pass" in nome:
        return "Gympass"
    return None

def aluno_eh_gympass(aluno: AlunoDB) -> bool:
    return plano_pass_tipo(getattr(aluno, "plano_nome", None)) == "Gympass"

def aluno_eh_total_pass(aluno: AlunoDB) -> bool:
    return plano_pass_tipo(getattr(aluno, "plano_nome", None)) == "Total Pass"

def aluno_eh_pass(aluno: AlunoDB) -> bool:
    return plano_pass_tipo(getattr(aluno, "plano_nome", None)) is not None

def inicio_fim_dia_utc() -> tuple[datetime, datetime]:
    # O app opera no Brasil; o banco salva UTC. Para evitar dependência externa,
    # usamos a janela local do servidor como referência diária do sistema.
    inicio = datetime.combine(hoje(), datetime.min.time())
    fim = inicio + timedelta(days=1)
    return inicio, fim

def pass_usados_hoje(db, aluno_id: int, tipo_pass: Optional[str] = None) -> int:
    inicio, fim = inicio_fim_dia_utc()
    query = db.query(EntradaDB).filter(
        EntradaDB.aluno_id == aluno_id,
        EntradaDB.status == "liberado",
        EntradaDB.data_entrada >= inicio,
        EntradaDB.data_entrada < fim,
    )
    if tipo_pass:
        tipo = tipo_pass.lower()
        query = query.filter(EntradaDB.motivo.ilike(f"%{tipo}%"))
    else:
        query = query.filter(or_(EntradaDB.motivo.ilike("%gympass%"), EntradaDB.motivo.ilike("%total pass%"), EntradaDB.motivo.ilike("%total_pass%")))
    return query.count()

def gympass_usados_hoje(db, aluno_id: int) -> int:
    return pass_usados_hoje(db, aluno_id, "gympass")

def registrar_acesso_pass_automatico(db, aluno: AlunoDB, tipo_pass: str, usados_antes: int) -> tuple[LiberacaoCatracaDB, GympassSolicitacaoDB]:
    pedido = LiberacaoCatracaDB(
        aluno_id=aluno.id,
        cpf=aluno.cpf,
        nome=aluno.nome,
        status="pendente",
        segundos=5,
        sentido="ambos",
        motivo=f"{tipo_pass} — liberado automaticamente",
        atualizado_em=datetime.utcnow(),
    )
    historico = GympassSolicitacaoDB(
        aluno_id=aluno.id,
        cpf=aluno.cpf,
        nome=aluno.nome,
        status="liberado",
        usado_no_dia=usados_antes + 1,
        tipo_pass=tipo_pass,
        liberado_por_nome="Sistema",
        observacao=f"Acesso via {tipo_pass} liberado automaticamente",
        criado_em=datetime.utcnow(),
        liberado_em=datetime.utcnow(),
        atualizado_em=datetime.utcnow(),
    )
    db.add(pedido)
    db.add(historico)
    registrar_evento_entrada(db, aluno, "liberado", f"{tipo_pass} — liberado automaticamente — usado {usados_antes + 1}/2 no dia")
    return pedido, historico

def aluno_premium_admin(aluno: AlunoDB) -> bool:
    return bool(getattr(aluno, "premium_admin", False))

def aluno_acesso_livre(aluno: AlunoDB) -> bool:
    return bool(getattr(aluno, "acesso_livre", False))

def aluno_super_admin(aluno: AlunoDB) -> bool:
    cpf = only_digits(getattr(aluno, "cpf", "") or "")
    return bool(getattr(aluno, "pode_acessar_adm", False)) or cpf == "87740648191"

def aluno_sem_cobranca(aluno: AlunoDB) -> bool:
    return aluno_premium_admin(aluno) or aluno_acesso_livre(aluno) or aluno_eh_pass(aluno)

def obter_status_por_regras(aluno: AlunoDB) -> str:
    if aluno_premium_admin(aluno) or aluno_acesso_livre(aluno):
        return "em_dia"

    plano = (getattr(aluno, "plano_nome", None) or "").strip().lower()
    if plano_pass_tipo(plano):
        return "em_dia"

    venc = parse_date_safe(aluno.vencimento)
    if venc:
        faltam = (venc - hoje()).days
        # Regra 5.0.9:
        # em_dia = faltam mais de 3 dias para vencer;
        # pendente = faltam 3 dias ou menos, mas ainda não venceu;
        # atrasado = venceu e não pagou. O dia do vencimento ainda é válido.
        if faltam < 0:
            if aluno_deve_inativar_por_atraso(aluno):
                return "inativo"
            return "atrasado"
        if faltam <= 3:
            return "pendente"
        return "em_dia"

    manual = (aluno.status_manual or "").strip().lower()
    if manual in {"em_dia", "pendente", "atrasado", "inativo"}:
        return manual

    return "pendente"

def info_plano(db, plano_key: str, valor_override: Optional[float] = None, dias_override: Optional[int] = None):
    plano_key = (plano_key or "").strip().lower()
    promocional_valor = float(get_config(db, "promocional_valor", str(PROMOCIONAL_VALOR_PADRAO)))
    promocional_dias = int(get_config(db, "promocional_dias", str(PROMOCIONAL_DIAS_PADRAO)))

    tabela = {
        "mensal": {"nome": "Mensal", "valor": MENSAL_VALOR, "dias": 30},
        "semestral": {"nome": "Semestral", "valor": SEMESTRAL_VALOR, "dias": 180},
        "anual": {"nome": "Anual", "valor": ANUAL_VALOR, "dias": 365},
        "promocional": {"nome": "Promocional", "valor": promocional_valor, "dias": promocional_dias},
        "diaria": {"nome": "Diária", "valor": DIARIA_VALOR, "dias": 1},
        "diária": {"nome": "Diária", "valor": DIARIA_VALOR, "dias": 1},
        "gympass": {"nome": "Gympass", "valor": GYMPASS_VALOR, "dias": 0},
        "total_pass": {"nome": "Total Pass", "valor": TOTAL_PASS_VALOR, "dias": 0},
        "total pass": {"nome": "Total Pass", "valor": TOTAL_PASS_VALOR, "dias": 0},
        "totalpass": {"nome": "Total Pass", "valor": TOTAL_PASS_VALOR, "dias": 0},
    }
    item = tabela.get(plano_key)
    if not item:
        raise HTTPException(status_code=400, detail="Plano inválido")
    item = dict(item)
    if valor_override is not None:
        item["valor"] = float(valor_override)
    if dias_override is not None:
        item["dias"] = int(dias_override)
    return item

def get_config(db, chave: str, default: str) -> str:
    item = db.query(ConfigDB).filter(ConfigDB.chave == chave).first()
    if not item:
        item = ConfigDB(chave=chave, valor=default)
        db.add(item)
        db.commit()
        db.refresh(item)
    return item.valor

def set_config(db, chave: str, valor: str) -> str:
    item = db.query(ConfigDB).filter(ConfigDB.chave == chave).first()
    if not item:
        item = ConfigDB(chave=chave, valor=valor)
        db.add(item)
    else:
        item.valor = valor
    db.commit()
    db.refresh(item)
    return item.valor

def qrcode_base64(valor: str) -> str:
    qr = qrcode.make(valor)
    buffer = BytesIO()
    qr.save(buffer, format="PNG")
    buffer.seek(0)
    encoded = base64.b64encode(buffer.read()).decode("utf-8")
    return f"data:image/png;base64,{encoded}"

def buscar_aluno_por_id(db, aluno_id: int, incluir_deletados: bool = False) -> Optional[AlunoDB]:
    q = db.query(AlunoDB).filter(AlunoDB.id == aluno_id)
    if not incluir_deletados:
        q = q.filter(or_(AlunoDB.deletado == False, AlunoDB.deletado.is_(None)))
    return q.first()

def buscar_aluno_por_cpf(db, cpf: str, incluir_deletados: bool = False) -> Optional[AlunoDB]:
    cpf_limpo = only_digits(cpf)
    if not cpf_limpo:
        return None
    q = db.query(AlunoDB)
    if not incluir_deletados:
        q = q.filter(or_(AlunoDB.deletado == False, AlunoDB.deletado.is_(None)))
    return q.filter(AlunoDB.cpf == cpf_limpo).first()


def valor_base_plano_nome(db, plano_nome: Optional[str]) -> float:
    nome = (plano_nome or "Mensal").strip().lower()
    if "anual" in nome:
        return ANUAL_VALOR
    if "sem" in nome:
        return SEMESTRAL_VALOR
    if "diária" in nome or "diaria" in nome:
        return DIARIA_VALOR
    if plano_pass_tipo(nome):
        return 0.0
    if "promo" in nome:
        return float(get_config(db, "promocional_valor", str(PROMOCIONAL_VALOR_PADRAO)))
    return MENSAL_VALOR


def beneficio_ativo_aluno(aluno: AlunoDB) -> bool:
    return bool(aluno.beneficio_ativo) and obter_status_por_regras(aluno) != "inativo"


def valor_cobrado_aluno(db, aluno: AlunoDB, plano_nome: Optional[str] = None) -> float:
    plano_ref = plano_nome or aluno.plano_nome
    if aluno_sem_cobranca(aluno):
        return 0.0
    juros = juros_atraso_aluno(aluno)

    # Prioridade máxima: valor final manual definido pelo ADM.
    # Isso garante que ADM, aluno, relatórios e checkout usem o mesmo valor.
    if bool(getattr(aluno, "valor_final_manual_ativo", False)):
        valor_manual = float(getattr(aluno, "valor_final_manual", 0) or 0)
        if valor_manual >= 0:
            return round(valor_manual + juros, 2)

    valor_padrao = float(aluno.valor_padrao_plano or 0) or valor_base_plano_nome(db, plano_ref)
    base = float(aluno.valor_plano or 0) or valor_padrao

    # Novo padrão: desconto em reais.
    desconto_reais = float(getattr(aluno, "desconto_valor", 0) or 0)
    if desconto_reais > 0:
        return round(max(base - desconto_reais, 0.0) + juros, 2)

    # Compatibilidade com alunos antigos que já tinham valor final personalizado.
    valor_personalizado = float(aluno.valor_personalizado or 0)
    if beneficio_ativo_aluno(aluno) and valor_personalizado > 0:
        return round(valor_personalizado + juros, 2)

    # Compatibilidade com versões antigas que gravavam percentual.
    desconto = float(aluno.desconto_percentual or 0)
    desconto = max(0.0, min(100.0, desconto))
    return round(max(base * (1 - desconto / 100.0), 0.0) + juros, 2)


def desconto_percentual_real(db, aluno: AlunoDB, plano_nome: Optional[str] = None) -> float:
    plano_ref = plano_nome or aluno.plano_nome
    valor_padrao = float(aluno.valor_padrao_plano or 0) or valor_base_plano_nome(db, plano_ref)
    valor_real = valor_cobrado_aluno(db, aluno, plano_ref)
    if valor_padrao <= 0 or valor_real >= valor_padrao:
        return float(aluno.desconto_percentual or 0)
    return round(((valor_padrao - valor_real) / valor_padrao) * 100.0, 2)


def desconto_valor_real(db, aluno: AlunoDB, plano_nome: Optional[str] = None) -> float:
    plano_ref = plano_nome or aluno.plano_nome
    valor_padrao = float(aluno.valor_padrao_plano or 0) or valor_base_plano_nome(db, plano_ref)
    base = float(aluno.valor_plano or 0) or valor_padrao
    desconto_reais = float(getattr(aluno, "desconto_valor", 0) or 0)
    if desconto_reais > 0:
        return round(min(max(desconto_reais, 0.0), max(base, 0.0)), 2)
    valor_personalizado = float(aluno.valor_personalizado or 0)
    if valor_personalizado > 0 and base > valor_personalizado:
        return round(base - valor_personalizado, 2)
    desconto_pct = float(aluno.desconto_percentual or 0)
    if desconto_pct > 0:
        return round(base * (max(0.0, min(100.0, desconto_pct)) / 100.0), 2)
    return 0.0


def valor_base_sem_juros_aluno(db, aluno: AlunoDB, plano_nome: Optional[str] = None) -> float:
    plano_ref = plano_nome or aluno.plano_nome
    if aluno_sem_cobranca(aluno):
        return 0.0

    if bool(getattr(aluno, "valor_final_manual_ativo", False)):
        valor_manual = float(getattr(aluno, "valor_final_manual", 0) or 0)
        if valor_manual >= 0:
            return round(valor_manual, 2)

    valor_padrao = float(aluno.valor_padrao_plano or 0) or valor_base_plano_nome(db, plano_ref)
    base = float(aluno.valor_plano or 0) or valor_padrao
    desconto_reais = float(getattr(aluno, "desconto_valor", 0) or 0)
    if desconto_reais > 0:
        return round(max(base - desconto_reais, 0.0), 2)

    valor_personalizado = float(aluno.valor_personalizado or 0)
    if beneficio_ativo_aluno(aluno) and valor_personalizado > 0:
        return round(valor_personalizado, 2)

    desconto = float(aluno.desconto_percentual or 0)
    desconto = max(0.0, min(100.0, desconto))
    return round(max(base * (1 - desconto / 100.0), 0.0), 2)


def valor_final_aluno(db, aluno: AlunoDB) -> float:
    return valor_cobrado_aluno(db, aluno, aluno.plano_nome)


def aluno_dict(db, aluno: AlunoDB) -> dict:
    # A leitura do aluno também garante a regra automática de inativação.
    mudou_inativo = processar_inativacao_por_atraso(db, aluno)
    if mudou_inativo:
        db.commit()
        db.refresh(aluno)
    status = obter_status_por_regras(aluno)
    premium_admin = aluno_premium_admin(aluno)
    acesso_livre = aluno_acesso_livre(aluno)
    pode_acessar_adm = aluno_super_admin(aluno)
    valor_padrao = float(aluno.valor_padrao_plano or 0) or valor_base_plano_nome(db, aluno.plano_nome)
    valor_personalizado = float(aluno.valor_personalizado or 0)
    juros = juros_atraso_aluno(aluno)
    valor_base_sem_juros = valor_base_sem_juros_aluno(db, aluno)
    total_a_pagar = round(valor_base_sem_juros + juros, 2)
    beneficio_ativo = beneficio_ativo_aluno(aluno)
    venc = parse_date_safe(aluno.vencimento)
    dias_para_vencer = (venc - hoje()).days if venc else None
    dias_pendentes_restantes = max(0, int(dias_para_vencer or 0)) if status == "pendente" else 0
    return {
        "id": aluno.id,
        "nome": aluno.nome,
        "telefone": aluno.telefone,
        "cpf": aluno.cpf,
        "email": aluno.email,
        "sexo": aluno.sexo,
        "status": status,
        "status_manual": aluno.status_manual,
        "premium_admin": premium_admin,
        "adm_premium": premium_admin,
        "acesso_livre": acesso_livre,
        "pode_acessar_adm": pode_acessar_adm,
        "pode_atender_chat": bool(getattr(aluno, "pode_atender_chat", False)),
        "juros_perdoado_vencimento": getattr(aluno, "juros_perdoado_vencimento", None),
        "juros_perdoado_em": aluno.juros_perdoado_em.isoformat() if getattr(aluno, "juros_perdoado_em", None) else None,
        "dias_uteis_atraso": dias_uteis_atraso(getattr(aluno, "vencimento", None)),
        "tipo_aluno": "Professor/Premium" if premium_admin else ("Acesso Livre" if acesso_livre else (plano_pass_tipo(aluno.plano_nome) or "Aluno comum")),
        "dias_pendentes_restantes": dias_pendentes_restantes,
        "dias_para_vencer": dias_para_vencer,
        "gympass": aluno_eh_gympass(aluno),
        "total_pass": aluno_eh_total_pass(aluno),
        "pass_tipo": plano_pass_tipo(aluno.plano_nome),
        "aviso_pagamento": ("Acesso vitalício — aluno com privilégio ADM/Premium." if premium_admin else ("Acesso livre — sem mensalidade e sem vencimento." if acesso_livre else (f"{plano_pass_tipo(aluno.plano_nome)} — 2 acessos por dia, sem cobrança no app." if plano_pass_tipo(aluno.plano_nome) else ("Sua mensalidade está próxima do vencimento. Regularize para evitar bloqueio." if status == "pendente" else None)))),
        "plano_nome": aluno.plano_nome,
        "valor_plano": float(aluno.valor_plano or 0),
        "valor_padrao_plano": valor_padrao,
        "valor_personalizado": valor_personalizado if valor_personalizado > 0 else None,
        "beneficio_ativo": beneficio_ativo,
        "origem_valor": aluno.origem_valor,
        "valor_final_manual": float(getattr(aluno, "valor_final_manual", 0) or 0) if getattr(aluno, "valor_final_manual", None) is not None else None,
        "valor_final_manual_ativo": bool(getattr(aluno, "valor_final_manual_ativo", False)),
        "pre_cadastro_origem": bool(getattr(aluno, "pre_cadastro_origem", False)),
        "desconto_percentual": desconto_percentual_real(db, aluno),
        "desconto_valor": desconto_valor_real(db, aluno),
        "valor_base": valor_base_sem_juros,
        "valor_base_sem_juros": valor_base_sem_juros,
        "valor_final": total_a_pagar,
        "total_a_pagar": total_a_pagar,
        "juros_atraso": juros,
        "multa_atraso": juros,
        "vencimento": aluno.vencimento,
        "data_inicio_plano": getattr(aluno, "data_inicio_plano", None),
        "dia_vencimento_fixo": getattr(aluno, "dia_vencimento_fixo", None),
        "foto_url": aluno.foto_url,
        "foto_base64": aluno.foto_base64,
        "data_cadastro": aluno.data_cadastro,
        "status_cliente_raw": aluno.status_cliente_raw,
        "status_contrato_raw": aluno.status_contrato_raw,
    }

def calcular_progresso(total_entradas: int) -> dict:
    if total_entradas <= 10:
        return {
            "nivel": "cinza",
            "cor": "gray",
            "mensagem": "Ótimo começo. Cada treino conta.",
            "proxima_meta": 11,
        }
    if total_entradas <= 25:
        return {
            "nivel": "bronze",
            "cor": "bronze",
            "mensagem": "Muito bem. Sua constância já chama atenção.",
            "proxima_meta": 26,
        }
    if total_entradas <= 50:
        return {
            "nivel": "prata",
            "cor": "blue",
            "mensagem": "Excelente ritmo. Você está construindo resultado real.",
            "proxima_meta": 51,
        }
    if total_entradas <= 100:
        return {
            "nivel": "ouro",
            "cor": "gold",
            "mensagem": "Impressionante. Seu compromisso está em outro nível.",
            "proxima_meta": 101,
        }
    return {
        "nivel": "premium",
        "cor": "premium",
        "mensagem": "Você é elite. Sua disciplina virou identidade.",
        "proxima_meta": 200,
    }

def calcular_novo_vencimento(vencimento_atual: Optional[str], dias: int) -> str:
    # Compatibilidade com rotas antigas sem objeto aluno.
    atual = parse_date_safe(vencimento_atual)
    base = atual or hoje()
    meses = meses_por_plano_dias(dias)
    dia_fixo = (atual.day if atual else hoje().day)
    novo = adicionar_meses_com_dia_fixo(base, meses, dia_fixo)
    while novo < hoje():
        novo = adicionar_meses_com_dia_fixo(novo, meses, dia_fixo)
    return novo.strftime("%Y-%m-%d")

def pagamento_dict(p: PagamentoDB) -> dict:
    return {
        "id": p.id,
        "aluno_id": p.aluno_id,
        "plano_nome": p.plano_nome,
        "valor": float(p.valor or 0),
        "dias": int(p.dias or 0),
        "status": p.status,
        "origem": p.origem,
        "link_pagamento": p.link_pagamento,
        "order_nsu": getattr(p, "order_nsu", None),
        "data_pagamento": p.data_pagamento.isoformat() if p.data_pagamento else None,
        "vencimento_anterior": p.vencimento_anterior,
        "novo_vencimento": p.novo_vencimento,
    }

def aplicar_pagamento_aluno(db, aluno: AlunoDB, plano_nome: str, valor: float, dias: Optional[int] = None):
    plano_key = (plano_nome or "mensal").strip().lower()
    if plano_key not in {"mensal", "semestral", "anual", "promocional"}:
        nome = (plano_nome or "").strip().lower()
        if "anual" in nome:
            plano_key = "anual"
        elif "sem" in nome:
            plano_key = "semestral"
        elif "promo" in nome:
            plano_key = "promocional"
        else:
            plano_key = "mensal"

    plano_info = info_plano(db, plano_key, valor_override=valor, dias_override=dias)
    if not clamp_dia_vencimento(getattr(aluno, "dia_vencimento_fixo", None)):
        aluno.dia_vencimento_fixo = inferir_dia_vencimento_fixo(aluno)
    novo_vencimento = calcular_novo_vencimento_fixo(aluno, int(plano_info["dias"]), plano_info["nome"])

    aluno.plano_nome = plano_info["nome"]
    base_oficial_plano = valor_base_plano_nome(db, plano_info["nome"])
    aluno.valor_padrao_plano = base_oficial_plano
    aluno.valor_plano = base_oficial_plano
    # Se estava inativo, volta como aluno normal sem condição especial antiga.
    if (aluno.status_manual or "").lower() == "inativo":
        aluno.desconto_percentual = 0.0
        aluno.desconto_valor = 0.0
        aluno.valor_personalizado = None
        aluno.valor_final_manual = None
        aluno.valor_final_manual_ativo = False
    aluno.beneficio_ativo = True
    aluno.juros_perdoado_vencimento = None
    aluno.juros_perdoado_em = None
    aluno.juros_perdoado_por = None
    aluno.vencimento = novo_vencimento
    aluno.status_manual = "em_dia"
    aluno.status_cliente_raw = "Ativo"
    aluno.status_contrato_raw = "Ativo"
    aluno.updated_at = datetime.utcnow()
    return novo_vencimento

def obter_link_plano(db, plano_key: str) -> Optional[str]:
    plano_key = plano_key.strip().lower()
    link_db = get_config(db, f"link_{plano_key}", "").strip()
    if link_db:
        return link_db
    defaults = {
        "mensal": PAYMENT_LINK_MENSAL,
        "semestral": PAYMENT_LINK_SEMESTRAL,
        "anual": PAYMENT_LINK_ANUAL,
        "promocional": PAYMENT_LINK_PROMOCIONAL,
    }
    return defaults.get(plano_key, "")

# ----------------------
# Root
# ----------------------
@app.get("/")
def root():
    return {"message": "API do Coliseu Fit funcionando"}

@app.get("/health")
def health():
    return {"status": "ok", "version": APP_VERSION}

# ----------------------
# Admin
# ----------------------
@app.post("/admin/login")
def admin_login(body: AdminLoginBody):
    if body.login == ADMIN_LOGIN and body.senha == ADMIN_PASSWORD:
        return {"ok": True, "message": "Login realizado com sucesso"}
    raise HTTPException(status_code=401, detail="Login ou senha inválidos")

# ----------------------
# Config / Planos / Links
# ----------------------
@app.get("/config/planos")
def obter_config_planos():
    db = SessionLocal()
    try:
        return {
            "mensal": {"valor": MENSAL_VALOR, "dias": 30, "link": obter_link_plano(db, "mensal")},
            "semestral": {"valor": SEMESTRAL_VALOR, "dias": 180, "link": obter_link_plano(db, "semestral")},
            "anual": {"valor": ANUAL_VALOR, "dias": 365, "link": obter_link_plano(db, "anual")},
            "promocional": {
                "valor": float(get_config(db, "promocional_valor", str(PROMOCIONAL_VALOR_PADRAO))),
                "dias": int(get_config(db, "promocional_dias", str(PROMOCIONAL_DIAS_PADRAO))),
                "link": obter_link_plano(db, "promocional"),
            },
            "diaria": {"valor": DIARIA_VALOR, "dias": 1, "link": ""},
            "gympass": {"valor": GYMPASS_VALOR, "dias": 0, "link": ""},
            "total_pass": {"valor": TOTAL_PASS_VALOR, "dias": 0, "link": ""},
        }
    finally:
        db.close()

@app.put("/config/promocional")
def atualizar_promocional(body: PromocionalConfigBody):
    db = SessionLocal()
    try:
        set_config(db, "promocional_valor", str(body.valor))
        set_config(db, "promocional_dias", str(body.dias))
        return {"ok": True, "message": "Plano promocional atualizado"}
    finally:
        db.close()

@app.put("/config/payment-links")
def atualizar_payment_links(body: PaymentLinksBody):
    db = SessionLocal()
    try:
        if body.mensal is not None:
            set_config(db, "link_mensal", body.mensal.strip())
        if body.semestral is not None:
            set_config(db, "link_semestral", body.semestral.strip())
        if body.anual is not None:
            set_config(db, "link_anual", body.anual.strip())
        if body.promocional is not None:
            set_config(db, "link_promocional", body.promocional.strip())
        return {"ok": True, "message": "Links de pagamento atualizados"}
    finally:
        db.close()

# ----------------------
# Alunos
# ----------------------
@app.post("/alunos")
def criar_aluno(body: AlunoCreate = Body(...)):
    db = SessionLocal()
    try:
        payload_nome = (body.nome or "").strip()
        payload_telefone = (body.telefone or None)
        payload_cpf = (body.cpf or "")
        payload_email = (body.email or None)
        payload_sexo = (body.sexo or None)
        payload_plano = (body.plano_nome or None)
        payload_dias = (body.dias_plano or None)
        payload_desconto = float(body.desconto_percentual or 0)
        payload_desconto_valor = float(body.desconto_valor or 0)
        payload_premium_admin = bool(body.premium_admin or False)
        payload_acesso_livre = bool(getattr(body, "acesso_livre", False) or False)
        payload_pode_acessar_adm = bool(getattr(body, "pode_acessar_adm", False) or False)
        if payload_premium_admin:
            payload_acesso_livre = False
        payload_tipo_pass = plano_pass_tipo(payload_plano)
        payload_sem_cobranca = payload_premium_admin or payload_acesso_livre or bool(payload_tipo_pass)
        payload_data_inicio = normalizar_data_texto(body.data_inicio_plano)
        payload_vencimento = normalizar_data_texto(body.vencimento)
        payload_dia_fixo = clamp_dia_vencimento(body.dia_vencimento_fixo)

        if not payload_nome:
            raise HTTPException(status_code=400, detail="Nome obrigatório")

        cpf_limpo = only_digits(payload_cpf)
        if not validar_cpf(cpf_limpo):
            raise HTTPException(status_code=400, detail="CPF inválido")

        if buscar_aluno_por_cpf(db, cpf_limpo):
            raise HTTPException(status_code=400, detail="CPF já cadastrado")

        plano_normalizado = None
        valor_plano = 0.0
        if payload_plano:
            try:
                plano_info = info_plano(db, payload_plano.strip().lower())
                plano_normalizado = plano_info["nome"]
                valor_plano = float(plano_info["valor"])
                if payload_dias is None:
                    payload_dias = int(plano_info["dias"])
            except Exception:
                plano_normalizado = payload_plano
                valor_plano = 0.0
        elif payload_dias is not None:
            try:
                key = "diaria" if int(payload_dias) <= 1 else "anual" if int(payload_dias) >= 365 else "semestral" if int(payload_dias) >= 180 else "mensal"
                plano_info = info_plano(db, key)
                plano_normalizado = plano_info["nome"]
                valor_plano = float(plano_info["valor"])
            except Exception:
                pass

        aluno = AlunoDB(
    nome=payload_nome,
    telefone=payload_telefone,
    cpf=cpf_limpo,
    email=payload_email,
    sexo=payload_sexo,
    plano_nome=plano_normalizado,
    valor_plano=valor_plano,
    valor_padrao_plano=valor_plano or valor_base_plano_nome(db, plano_normalizado),
    vencimento=None if payload_sem_cobranca else payload_vencimento,
    data_inicio_plano=None if payload_sem_cobranca else (payload_data_inicio or hoje_str()),
    dia_vencimento_fixo=None if payload_sem_cobranca else (payload_dia_fixo or ((parse_date_safe(payload_vencimento) or parse_date_safe(payload_data_inicio) or hoje()).day)),
    data_cadastro=agora_str(),
    status_cliente_raw="Ativo" if payload_sem_cobranca else "pendente",
    status_contrato_raw=("ADM/Premium" if payload_premium_admin else ("Acesso Livre" if payload_acesso_livre else (payload_tipo_pass or "aguardando_pagamento"))),
    premium_admin=payload_premium_admin,
    acesso_livre=payload_acesso_livre,
    pode_acessar_adm=payload_pode_acessar_adm,
    desconto_percentual=payload_desconto,
    desconto_valor=payload_desconto_valor,
    status_manual="em_dia" if payload_sem_cobranca else "pendente",
)
        db.add(aluno)
        db.commit()
        db.refresh(aluno)
        return {"mensagem": "Aluno criado com sucesso", "aluno": aluno_dict(db, aluno)}
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.get("/alunos")
def listar_alunos(
    status: Optional[str] = Query(default=None),
    busca: Optional[str] = Query(default=None),
):
    db = SessionLocal()
    try:
        alunos = db.query(AlunoDB).filter(or_(AlunoDB.deletado == False, AlunoDB.deletado.is_(None))).order_by(AlunoDB.nome.asc()).all()
        resultado = [aluno_dict(db, a) for a in alunos]

        if status:
            status = status.strip().lower()
            resultado = [a for a in resultado if a["status"] == status]

        if busca:
            b = busca.strip().lower()
            resultado = [
                a for a in resultado
                if b in (a["nome"] or "").lower()
                or b in (a["cpf"] or "").lower()
                or b in (a["telefone"] or "").lower()
            ]

        return resultado
    finally:
        db.close()

@app.get("/aluno/{aluno_id}")
def detalhar_aluno(aluno_id: int):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        return aluno_dict(db, aluno)
    finally:
        db.close()

@app.get("/aluno/cpf/{cpf}")
def detalhar_aluno_por_cpf(cpf: str):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_cpf(db, cpf)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        return aluno_dict(db, aluno)
    finally:
        db.close()

@app.put("/alunos/{aluno_id}")
def atualizar_aluno_admin(aluno_id: int, body: AlunoAdminUpdate):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")

        novo_cpf = only_digits(body.cpf)
        if not validar_cpf(novo_cpf):
            raise HTTPException(status_code=400, detail="CPF inválido")

        outro = buscar_aluno_por_cpf(db, novo_cpf)
        if outro and outro.id != aluno.id:
            raise HTTPException(status_code=400, detail="CPF já cadastrado em outro aluno")

        aluno.nome = body.nome.strip()
        aluno.telefone = (body.telefone or "").strip() or None
        aluno.cpf = novo_cpf
        aluno.email = (body.email or "").strip() or None
        aluno.sexo = (body.sexo or "").strip() or None
        if body.plano_nome is not None:
            plano_info_tipo = plano_pass_tipo(body.plano_nome)
            aluno.plano_nome = plano_info_tipo or body.plano_nome
            if plano_info_tipo:
                aluno.status_manual = "em_dia"
                aluno.vencimento = None
                aluno.data_inicio_plano = None
                aluno.dia_vencimento_fixo = None
                aluno.valor_plano = 0.0
                aluno.valor_padrao_plano = 0.0
                aluno.desconto_valor = 0.0
                aluno.valor_personalizado = None
                aluno.valor_final_manual = None
                aluno.valor_final_manual_ativo = False
                aluno.beneficio_ativo = True
                aluno.status_cliente_raw = "Ativo"
                aluno.status_contrato_raw = plano_info_tipo
        if body.valor_plano is not None:
            aluno.valor_plano = body.valor_plano
            aluno.valor_padrao_plano = body.valor_plano
            if not aluno.valor_personalizado:
                aluno.valor_personalizado = body.valor_plano
        if body.desconto_percentual is not None:
            aluno.desconto_percentual = float(body.desconto_percentual)
        if body.desconto_valor is not None:
            base_desconto = float(aluno.valor_plano or aluno.valor_padrao_plano or valor_base_plano_nome(db, aluno.plano_nome) or 0)
            desconto_reais = max(0.0, float(body.desconto_valor or 0))
            if base_desconto > 0:
                desconto_reais = min(desconto_reais, base_desconto)
            aluno.desconto_valor = desconto_reais
            aluno.valor_personalizado = round(max(base_desconto - desconto_reais, 0.0), 2) if desconto_reais > 0 else None
            aluno.beneficio_ativo = True
        if body.data_inicio_plano is not None:
            aluno.data_inicio_plano = normalizar_data_texto(body.data_inicio_plano)
        if body.dia_vencimento_fixo is not None:
            aluno.dia_vencimento_fixo = clamp_dia_vencimento(body.dia_vencimento_fixo)
        if body.vencimento is not None:
            aluno.vencimento = normalizar_data_texto(body.vencimento)
        if body.status_manual is not None:
            aluno.status_manual = body.status_manual
        if body.premium_admin is not None:
            aluno.premium_admin = bool(body.premium_admin)
            if aluno.premium_admin:
                aluno.acesso_livre = False
                aluno.status_manual = "em_dia"
                aluno.vencimento = None
                aluno.data_inicio_plano = None
                aluno.dia_vencimento_fixo = None
                aluno.beneficio_ativo = True
                aluno.status_cliente_raw = "Ativo"
                aluno.status_contrato_raw = "ADM/Premium"
        if getattr(body, "acesso_livre", None) is not None:
            aluno.acesso_livre = bool(body.acesso_livre)
            if aluno.acesso_livre:
                aluno.premium_admin = False
                aluno.status_manual = "em_dia"
                aluno.vencimento = None
                aluno.data_inicio_plano = None
                aluno.dia_vencimento_fixo = None
                aluno.beneficio_ativo = True
                aluno.status_cliente_raw = "Ativo"
                aluno.status_contrato_raw = "Acesso Livre"
        if getattr(body, "pode_acessar_adm", None) is not None:
            aluno.pode_acessar_adm = bool(body.pode_acessar_adm)
        if not aluno.premium_admin and not aluno_acesso_livre(aluno) and not aluno_eh_pass(aluno) and not clamp_dia_vencimento(getattr(aluno, "dia_vencimento_fixo", None)):
            aluno.dia_vencimento_fixo = inferir_dia_vencimento_fixo(aluno)
        aluno.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(aluno)
        return {"ok": True, "message": "Aluno atualizado", "aluno": aluno_dict(db, aluno)}
    finally:
        db.close()


@app.put("/alunos/{aluno_id}/desconto")
def atualizar_desconto_aluno(aluno_id: int, body: DescontoBody):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")

        valor_base = float(aluno.valor_plano or aluno.valor_padrao_plano or valor_base_plano_nome(db, aluno.plano_nome) or 0)

        # Novo padrão: desconto em reais.
        if body.desconto_valor is not None:
            desconto_reais = max(0.0, float(body.desconto_valor or 0))
            if valor_base > 0:
                desconto_reais = min(desconto_reais, valor_base)
            aluno.desconto_valor = desconto_reais
            aluno.desconto_percentual = round((desconto_reais / valor_base) * 100.0, 2) if valor_base > 0 else 0
            aluno.valor_personalizado = round(max(valor_base - desconto_reais, 0.0), 2) if desconto_reais > 0 else None
            aluno.valor_padrao_plano = valor_base
            aluno.beneficio_ativo = True
        # Compatibilidade com app antigo que ainda mande percentual.
        elif body.desconto_percentual is not None:
            pct = max(0.0, min(100.0, float(body.desconto_percentual or 0)))
            aluno.desconto_percentual = pct
            desconto_reais = round(valor_base * pct / 100.0, 2) if valor_base > 0 else 0
            aluno.desconto_valor = desconto_reais
            aluno.valor_personalizado = round(max(valor_base - desconto_reais, 0.0), 2) if desconto_reais > 0 else None
            aluno.valor_padrao_plano = valor_base
            aluno.beneficio_ativo = True

        aluno.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(aluno)
        return {"ok": True, "message": "Desconto atualizado", "aluno": aluno_dict(db, aluno)}
    finally:
        db.close()

@app.put("/aluno/{aluno_id}/perfil")
def atualizar_aluno_self(aluno_id: int, body: AlunoSelfUpdate):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")

        aluno.nome = body.nome.strip()
        aluno.telefone = (body.telefone or "").strip() or None
        aluno.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(aluno)
        return {"ok": True, "message": "Perfil atualizado", "aluno": aluno_dict(db, aluno)}
    finally:
        db.close()

@app.put("/aluno/{aluno_id}/foto")
def atualizar_foto_aluno(aluno_id: int, body: FotoAlunoBody):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        aluno.foto_url = body.foto_url
        aluno.foto_base64 = body.foto_base64
        aluno.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(aluno)
        return {"ok": True, "message": "Foto atualizada", "aluno": aluno_dict(db, aluno)}
    finally:
        db.close()

@app.delete("/alunos/{aluno_id}")
def excluir_aluno(aluno_id: int):
    """
    Exclusão segura do aluno.

    Não apagamos fisicamente a linha porque existem pagamentos, acessos, avisos,
    treinos e solicitações Gympass ligados ao aluno por chave estrangeira.
    Apagar direto causa erro no PostgreSQL e também destruiria histórico.

    A solução é marcar como deletado, esconder das listas/login e liberar o CPF
    para um novo cadastro futuro.
    """
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id, incluir_deletados=True)
        if not aluno or bool(getattr(aluno, "deletado", False)):
            raise HTTPException(status_code=404, detail="Aluno não encontrado")

        cpf_atual = only_digits(aluno.cpf or "")
        aluno.cpf_original = cpf_atual or aluno.cpf
        aluno.cpf = f"excluido_{aluno.id}_{cpf_atual or 'semcpf'}"
        aluno.nome = f"{aluno.nome} (excluído)"
        aluno.status_manual = "inativo"
        aluno.status_cliente_raw = "Excluído pelo ADM"
        aluno.status_contrato_raw = "excluido"
        aluno.deletado = True
        aluno.deletado_em = datetime.utcnow()
        aluno.updated_at = datetime.utcnow()
        db.commit()
        return {"ok": True, "message": "Aluno removido da lista com segurança"}
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao remover aluno: {e}")
    finally:
        db.close()

# ----------------------
# Pagamentos
# ----------------------
@app.post("/alunos/{aluno_id}/pagamentos")
def registrar_pagamento(aluno_id: int, body: PagamentoBody):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")

        if processar_inativacao_por_atraso(db, aluno):
            db.commit()
            db.refresh(aluno)

        plano_key = (body.plano or "atual").strip().lower()
        vencimento_anterior = aluno.vencimento

        if not clamp_dia_vencimento(getattr(aluno, "dia_vencimento_fixo", None)):
            aluno.dia_vencimento_fixo = inferir_dia_vencimento_fixo(aluno)

        if plano_key == "atual":
            plano_nome = aluno.plano_nome or "Mensal"
            dias = int(body.dias or (365 if plano_nome.lower() == "anual" else 180 if plano_nome.lower() == "semestral" else 30))
            valor_final = valor_final_aluno(db, aluno)
            novo_vencimento = calcular_novo_vencimento_fixo(aluno, dias, plano_nome)
            # Mantém plano, valor base, desconto e dia fixo atuais.
        else:
            plano = info_plano(db, plano_key, None, None)
            plano_nome = plano["nome"]
            dias = int(plano["dias"])
            valor_base = float(plano["valor"])
            desconto_reais = float(getattr(aluno, "desconto_valor", 0) or 0)
            desconto_reais = min(max(desconto_reais, 0.0), max(valor_base, 0.0))
            valor_final = round(max(valor_base - desconto_reais, 0.0), 2)
            novo_vencimento = calcular_novo_vencimento_fixo(aluno, dias, plano_nome)

            aluno.plano_nome = plano_nome
            aluno.valor_padrao_plano = valor_base
            aluno.valor_plano = valor_base
            aluno.valor_personalizado = None
            aluno.beneficio_ativo = bool(desconto_reais > 0)

        juros_regularizacao = juros_atraso_aluno(aluno)
        aluno.vencimento = novo_vencimento
        aluno.status_manual = "em_dia"
        aluno.beneficio_ativo = True
        aluno.juros_perdoado_vencimento = None
        aluno.juros_perdoado_em = None
        aluno.juros_perdoado_por = None
        aluno.updated_at = datetime.utcnow()

        pagamento = PagamentoDB(
            aluno_id=aluno.id,
            plano_nome=plano_nome,
            valor=valor_final,
            dias=int(dias),
            status="pago",
            origem="manual_admin" if body.origem == "manual" else body.origem,
            data_pagamento=datetime.utcnow(),
            vencimento_anterior=vencimento_anterior,
            novo_vencimento=novo_vencimento,
            valor_juros=juros_regularizacao,
        )
        db.add(pagamento)
        db.commit()
        db.refresh(aluno)

        return {
            "ok": True,
            "message": "Pagamento regularizado manualmente pelo administrador",
            "aluno": aluno_dict(db, aluno),
            "pagamento": pagamento_dict(pagamento),
        }
    finally:
        db.close()

@app.get("/alunos/{aluno_id}/pagamentos")
def listar_pagamentos_aluno(aluno_id: int):
    db = SessionLocal()
    try:
        pagamentos = (
            db.query(PagamentoDB)
            .filter(PagamentoDB.aluno_id == aluno_id)
            .order_by(PagamentoDB.data_pagamento.desc())
            .all()
        )
        return [
            {
                "id": p.id,
                "plano_nome": p.plano_nome,
                "valor": p.valor,
                "dias": p.dias,
                "status": p.status,
                "origem": p.origem,
                "data_pagamento": p.data_pagamento.isoformat(),
                "novo_vencimento": p.novo_vencimento,
                "vencimento_anterior": p.vencimento_anterior,
                "reembolsado_em": p.reembolsado_em.isoformat() if getattr(p, "reembolsado_em", None) else None,
                "pagamento_reembolsado_id": getattr(p, "pagamento_reembolsado_id", None),
                "observacao": getattr(p, "observacao", None),
            }
            for p in pagamentos
        ]
    finally:
        db.close()

@app.get("/pagamentos/link/{aluno_id}")
def obter_link_pagamento(aluno_id: int, plano: str):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        plano_info = info_plano(db, plano)
        link = obter_link_plano(db, plano)
        valor_final = valor_cobrado_aluno(db, aluno, plano_info["nome"])
        return {
            "ok": True,
            "plano": plano_info["nome"],
            "valor": valor_final,
            "dias": plano_info["dias"],
            "handle": INFINITEPAY_HANDLE,
            "link": link,
            "message": "Link retornado com sucesso",
        }
    finally:
        db.close()



@app.get("/aluno/{aluno_id}/link-pagamento")
def obter_link_pagamento_aluno(aluno_id: int, plano: Optional[str] = None):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        plano_key = (plano or (aluno.plano_nome or "Mensal")).strip().lower()
        if plano_key == "mensal":
            plano_key = "mensal"
        elif plano_key == "semestral":
            plano_key = "semestral"
        elif plano_key == "anual":
            plano_key = "anual"
        else:
            plano_key = "promocional"
        plano_info = info_plano(db, plano_key)
        link = obter_link_plano(db, plano_key)
        valor_final = valor_cobrado_aluno(db, aluno, plano_info["nome"])
        return {
            "ok": True,
            "plano": plano_info["nome"],
            "valor": valor_final,
            "dias": plano_info["dias"],
            "handle": INFINITEPAY_HANDLE,
            "link": link,
            "message": "Link retornado com sucesso",
        }
    finally:
        db.close()

# ----------------------
# Avisos
# ----------------------
@app.post("/avisos")
def criar_aviso(body: AvisoCreate = Body(...)):
    db = SessionLocal()
    try:
        aviso = AvisoDB(
            titulo=body.titulo.strip(),
            mensagem=body.mensagem.strip(),
            imagem_base64=(body.imagem_base64 or body.image_base64),
        )
        db.add(aviso)
        db.commit()
        db.refresh(aviso)
        return {"ok": True, "message": "Aviso criado com sucesso", "aviso_id": aviso.id}
    except Exception as e:
        db.rollback()
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})
    finally:
        db.close()

@app.get("/avisos")
def listar_avisos():
    # Avisos estão em manutenção nesta versão. Se a tabela não existir ou o banco
    # estiver parcialmente migrado, retorna lista vazia para não quebrar o webapp.
    db = SessionLocal()
    try:
        avisos = db.query(AvisoDB).order_by(AvisoDB.data.desc()).all()
        return [
            {
                "id": a.id,
                "titulo": a.titulo,
                "mensagem": a.mensagem,
                "imagem_base64": a.imagem_base64,
                "data": a.data.isoformat() if a.data else None,
            }
            for a in avisos
        ]
    except Exception:
        db.rollback()
        return []
    finally:
        db.close()

@app.delete("/avisos/{aviso_id}")
def excluir_aviso(aviso_id: int):
    db = SessionLocal()
    try:
        aviso = db.query(AvisoDB).filter(AvisoDB.id == aviso_id).first()
        if not aviso:
            raise HTTPException(status_code=404, detail="Aviso não encontrado")

        # Primeiro apaga as leituras vinculadas ao aviso.
        # Sem isso o PostgreSQL pode bloquear a exclusão por causa da FK
        # avisos_leituras.aviso_id -> avisos.id.
        db.query(AvisoLeituraDB).filter(AvisoLeituraDB.aviso_id == aviso_id).delete(synchronize_session=False)
        db.delete(aviso)
        db.commit()
        return {"ok": True, "message": "Aviso excluído com sucesso"}
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        return JSONResponse(status_code=500, content={"ok": False, "error": f"Erro ao excluir aviso: {str(e)}"})
    finally:
        db.close()

@app.post("/avisos/{aviso_id}/ler")
def marcar_aviso_lido(aviso_id: int, body: AvisoLidoBody):
    db = SessionLocal()
    try:
        item = (
            db.query(AvisoLeituraDB)
            .filter(AvisoLeituraDB.aviso_id == aviso_id, AvisoLeituraDB.aluno_id == body.aluno_id)
            .first()
        )
        if not item:
            item = AvisoLeituraDB(aviso_id=aviso_id, aluno_id=body.aluno_id, lido=True)
            db.add(item)
        db.commit()
        return {"ok": True}
    finally:
        db.close()

@app.get("/alunos/{aluno_id}/avisos/nao-lidos")
def avisos_nao_lidos(aluno_id: int):
    # Avisos em manutenção: qualquer erro de tabela ausente vira 0 não lidos.
    db = SessionLocal()
    try:
        total = db.query(AvisoDB).count()
        lidos = (
            db.query(AvisoLeituraDB)
            .filter(AvisoLeituraDB.aluno_id == aluno_id, AvisoLeituraDB.lido == True)
            .count()
        )
        return {"nao_lidos": max(total - lidos, 0)}
    except Exception:
        db.rollback()
        return {"nao_lidos": 0}
    finally:
        db.close()

# ----------------------
# Treinos
# ----------------------
@app.post("/treinos")
def criar_treino(body: TreinoCreate):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, body.aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        treino = TreinoDB(
            aluno_id=body.aluno_id,
            categoria=body.categoria,
            titulo=body.titulo.strip(),
            descricao=(body.descricao or "").strip() or None,
            exercicios=(body.exercicios or "").strip() or None,
            video_url=(body.video_url or "").strip() or None,
        )
        db.add(treino)
        db.commit()
        db.refresh(treino)
        return {"ok": True, "message": "Treino criado", "treino_id": treino.id}
    finally:
        db.close()

@app.get("/alunos/{aluno_id}/treinos")
def listar_treinos(aluno_id: int):
    db = SessionLocal()
    try:
        treinos = (
            db.query(TreinoDB)
            .filter(TreinoDB.aluno_id == aluno_id)
            .order_by(TreinoDB.categoria.asc(), TreinoDB.id.desc())
            .all()
        )
        if not treinos:
            padrao = {
                "A": ["Peito — supino reto 3x10", "Ombro — desenvolvimento 3x10", "Tríceps — corda 3x12"],
                "B": ["Costas — puxada frontal 3x10", "Remada baixa 3x10", "Bíceps — rosca direta 3x12"],
                "C": ["Pernas — agachamento 3x10", "Leg press 3x12", "Panturrilha 3x15"],
                "D": ["Cardio leve 20 min", "Abdominal 3x15", "Mobilidade e alongamento"],
            }
            return [
                {
                    "id": 0,
                    "categoria": k,
                    "codigo": k,
                    "titulo": f"Treino {k}",
                    "descricao": "Treino padrão da academia.",
                    "exercicios": "\n".join(v),
                    "video_url": None,
                    "padrao": True,
                }
                for k, v in padrao.items()
            ]
        return [
            {
                "id": t.id,
                "categoria": t.categoria,
                "codigo": t.categoria,
                "titulo": t.titulo,
                "descricao": t.descricao,
                "exercicios": t.exercicios,
                "video_url": t.video_url,
            }
            for t in treinos
        ]
    finally:
        db.close()

@app.put("/treinos/{treino_id}")
def atualizar_treino(treino_id: int, body: TreinoCreate):
    db = SessionLocal()
    try:
        treino = db.query(TreinoDB).filter(TreinoDB.id == treino_id).first()
        if not treino:
            raise HTTPException(status_code=404, detail="Treino não encontrado")
        treino.categoria = body.categoria
        treino.titulo = body.titulo.strip()
        treino.descricao = (body.descricao or "").strip() or None
        treino.exercicios = (body.exercicios or "").strip() or None
        treino.video_url = (body.video_url or "").strip() or None
        db.commit()
        return {"ok": True, "message": "Treino atualizado"}
    finally:
        db.close()

@app.delete("/treinos/{treino_id}")
def excluir_treino(treino_id: int):
    db = SessionLocal()
    try:
        treino = db.query(TreinoDB).filter(TreinoDB.id == treino_id).first()
        if not treino:
            raise HTTPException(status_code=404, detail="Treino não encontrado")
        db.delete(treino)
        db.commit()
        return {"ok": True, "message": "Treino excluído"}
    finally:
        db.close()


def aluno_pode_liberar_catraca(aluno: AlunoDB) -> tuple[bool, str]:
    if not aluno:
        return False, "Aluno não encontrado"

    if aluno_premium_admin(aluno):
        return True, "Acesso liberado — aluno com privilégio ADM/Premium."
    if aluno_acesso_livre(aluno):
        return True, "Acesso livre liberado — sem mensalidade e sem timer."

    plano = (aluno.plano_nome or "").strip().lower()
    tipo_pass = plano_pass_tipo(plano)
    if tipo_pass:
        return True, f"{tipo_pass} liberado automaticamente."

    status = obter_status_por_regras(aluno)
    if status == "em_dia":
        return True, "Aluno liberado"
    if status == "pendente":
        return True, "Aluno pendente: mensalidade próxima do vencimento. Acesso liberado preventivamente."
    if status == "atrasado":
        return False, "Aluno atrasado. Regularize o pagamento."
    if status == "inativo":
        return False, "Aluno inativo. Procure a recepção."
    return False, f"Status não liberado: {status}"

def registrar_evento_entrada(db, aluno: AlunoDB, status: str, motivo: str) -> None:
    if aluno_premium_admin(aluno) and status == "liberado":
        motivo = "Acesso liberado — aluno com privilégio ADM/Premium."
    if aluno_acesso_livre(aluno) and status == "liberado":
        motivo = "Acesso livre liberado — sem mensalidade."
    tipo_pass = plano_pass_tipo(getattr(aluno, "plano_nome", None))
    if tipo_pass and status == "liberado" and "liberado automaticamente" not in (motivo or "").lower():
        motivo = f"{tipo_pass} — liberado automaticamente"

    # Evita duplicidade quando o aluno toca várias vezes no botão em poucos segundos.
    limite = datetime.utcnow() - timedelta(seconds=20)
    recente = (
        db.query(EntradaDB)
        .filter(EntradaDB.aluno_id == aluno.id, EntradaDB.status == (status or "liberado"), EntradaDB.data_entrada >= limite)
        .order_by(EntradaDB.data_entrada.desc())
        .first()
    )
    if recente:
        return

    db.add(EntradaDB(
        aluno_id=aluno.id,
        nome=aluno.nome or "Aluno",
        status=(status or "liberado"),
        motivo=(motivo or "catraca"),
    ))


def cooldown_catraca_restante(db, aluno: AlunoDB) -> int:
    if aluno_premium_admin(aluno) or aluno_acesso_livre(aluno) or aluno_eh_pass(aluno):
        return 0
    limite = datetime.utcnow() - timedelta(minutes=5)
    ultimo = (
        db.query(EntradaDB)
        .filter(EntradaDB.aluno_id == aluno.id, EntradaDB.status == "liberado", EntradaDB.data_entrada >= limite)
        .order_by(EntradaDB.data_entrada.desc())
        .first()
    )
    if not ultimo or not ultimo.data_entrada:
        return 0
    restante = 300 - int((datetime.utcnow() - ultimo.data_entrada).total_seconds())
    return max(0, restante)


CATRACA_PEDIDO_TIMEOUT_SECONDS = 12

def reabrir_pedidos_catraca_travados(db, aluno_id: Optional[int] = None) -> int:
    """
    Se alguém abriu /agente/catraca/pendente no navegador ou o agente caiu no meio,
    o pedido pode ficar preso como em_execucao. Depois de alguns segundos,
    voltamos o pedido para pendente para o agente real conseguir pegar.
    """
    limite = datetime.utcnow() - timedelta(seconds=CATRACA_PEDIDO_TIMEOUT_SECONDS)
    query = db.query(LiberacaoCatracaDB).filter(
        LiberacaoCatracaDB.status == "em_execucao",
        LiberacaoCatracaDB.atualizado_em < limite,
    )
    if aluno_id is not None:
        query = query.filter(LiberacaoCatracaDB.aluno_id == aluno_id)

    pedidos = query.all()
    for pedido in pedidos:
        pedido.status = "pendente"
        pedido.motivo = "reprocessado"
        pedido.atualizado_em = datetime.utcnow()

    if pedidos:
        db.commit()

    return len(pedidos)

# ----------------------
# Acesso / Catraca
# ----------------------
@app.get("/catraca/qr")
def obter_qr_catraca():
    return {"codigo": QR_CATRACA, "qr_image_base64": qrcode_base64(QR_CATRACA)}

@app.get("/catraca/solicitar/{aluno_id}")
@app.post("/catraca/solicitar/{aluno_id}")
def solicitar_liberacao_catraca(aluno_id: int):
    """
    Chamado pelo app do aluno.
    Se o aluno estiver em dia, cria um pedido pendente para o agente local do PC da academia.
    Não mexe diretamente no Henry; quem faz isso é o agente Windows.
    """
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")

        if processar_inativacao_por_atraso(db, aluno):
            db.commit()
            db.refresh(aluno)

        tipo_pass = plano_pass_tipo(aluno.plano_nome)
        if tipo_pass and not aluno_premium_admin(aluno):
            usados = pass_usados_hoje(db, aluno.id, tipo_pass)
            if usados >= 2:
                return {
                    "ok": False,
                    "liberado": False,
                    "pass_tipo": tipo_pass,
                    "gympass": tipo_pass == "Gympass",
                    "total_pass": tipo_pass == "Total Pass",
                    "usados_hoje": usados,
                    "mensagem": "Você já utilizou seus 2 acessos de hoje. Tente novamente amanhã.",
                }
            reabrir_pedidos_catraca_travados(db, aluno.id)
            pedido, historico = registrar_acesso_pass_automatico(db, aluno, tipo_pass, usados)
            db.commit()
            db.refresh(pedido)
            db.refresh(historico)
            return {
                "ok": True,
                "liberado": True,
                "pedido_id": pedido.id,
                "historico_id": historico.id,
                "status_pedido": pedido.status,
                "pass_tipo": tipo_pass,
                "gympass": tipo_pass == "Gympass",
                "total_pass": tipo_pass == "Total Pass",
                "usados_hoje": usados + 1,
                "mensagem": f"Acesso liberado automaticamente via {tipo_pass}. Usado {usados + 1}/2 hoje.",
                "notificacao": f"Novo acesso {tipo_pass}: {aluno.nome} entrou.",
            }

        pode, mensagem = aluno_pode_liberar_catraca(aluno)

        if pode:
            restante = cooldown_catraca_restante(db, aluno)
            if restante > 0:
                return {
                    "ok": False,
                    "liberado": False,
                    "cooldown": True,
                    "segundos_restantes": restante,
                    "mensagem": f"Aguarde {restante // 60}:{restante % 60:02d} para liberar a catraca novamente.",
                }

        if not pode:
            pedido = LiberacaoCatracaDB(
                aluno_id=aluno.id,
                cpf=aluno.cpf,
                nome=aluno.nome,
                status="negado",
                segundos=5,
                sentido="ambos",
                motivo=mensagem,
                atualizado_em=datetime.utcnow(),
            )
            db.add(pedido)
            registrar_evento_entrada(db, aluno, "bloqueado", "catraca")
            db.commit()
            db.refresh(pedido)
            return {
                "ok": False,
                "liberado": False,
                "pedido_id": pedido.id,
                "mensagem": mensagem,
            }

        # Se algum teste/navegador consumiu o pedido e ele ficou preso em execução, reabre.
        reabrir_pedidos_catraca_travados(db, aluno.id)

        # Evita acumular vários pedidos pendentes do mesmo aluno.
        existente = (
            db.query(LiberacaoCatracaDB)
            .filter(
                LiberacaoCatracaDB.aluno_id == aluno.id,
                LiberacaoCatracaDB.status.in_(["pendente", "em_execucao"]),
            )
            .order_by(LiberacaoCatracaDB.criado_em.desc())
            .first()
        )
        if existente:
            status_atual = obter_status_por_regras(aluno)
            if existente.status == "em_execucao":
                mensagem_existente = "Pedido já está em execução pelo agente. Empurre a catraca quando liberar."
            else:
                mensagem_existente = "Seu acesso foi liberado. Atenção: sua mensalidade está próxima do vencimento." if status_atual == "pendente" else "Pedido de liberação enviado. Aguarde a catraca."
            registrar_evento_entrada(db, aluno, "liberado", "premium" if aluno_premium_admin(aluno) else ("acesso_livre" if aluno_acesso_livre(aluno) else ("pendente" if obter_status_por_regras(aluno) == "pendente" else "catraca")))
            db.commit()
            return {
                "ok": True,
                "liberado": True,
                "pedido_id": existente.id,
                "status_pedido": existente.status,
                "mensagem": mensagem_existente,
            }

        pedido = LiberacaoCatracaDB(
            aluno_id=aluno.id,
            cpf=aluno.cpf,
            nome=aluno.nome,
            status="pendente",
            segundos=5,
            sentido="ambos",
            motivo="app",
            atualizado_em=datetime.utcnow(),
        )
        db.add(pedido)
        registrar_evento_entrada(db, aluno, "liberado", "premium" if aluno_premium_admin(aluno) else ("acesso_livre" if aluno_acesso_livre(aluno) else ("pendente" if obter_status_por_regras(aluno) == "pendente" else "catraca")))
        db.commit()
        db.refresh(pedido)

        return {
            "ok": True,
            "liberado": True,
            "pedido_id": pedido.id,
            "status_pedido": pedido.status,
            "mensagem": "Seu acesso foi liberado. Atenção: sua mensalidade está próxima do vencimento." if obter_status_por_regras(aluno) == "pendente" else (mensagem if aluno_premium_admin(aluno) or aluno_acesso_livre(aluno) else "Pedido enviado. Aguarde a liberação da catraca."),
            "premium_admin": aluno_premium_admin(aluno),
            "acesso_livre": aluno_acesso_livre(aluno),
            "status_aluno": obter_status_por_regras(aluno),
        }
    finally:
        db.close()


@app.get("/agente/catraca/pendente")
def agente_buscar_pedido_pendente(token: str = Query(default="")):
    token_esperado = os.getenv("AGENTE_CATRACA_TOKEN", "coliseu-agente-local-2026")
    if token != token_esperado:
        raise HTTPException(status_code=401, detail="Token inválido")

    db = SessionLocal()
    try:
        # Reabre pedidos travados antes de buscar pendentes.
        reabrir_pedidos_catraca_travados(db)

        pedido = (
            db.query(LiberacaoCatracaDB)
            .filter(LiberacaoCatracaDB.status == "pendente")
            .order_by(LiberacaoCatracaDB.criado_em.asc())
            .first()
        )

        if not pedido:
            return {"ok": True, "pedido": None}

        pedido.status = "em_execucao"
        pedido.atualizado_em = datetime.utcnow()
        db.commit()
        db.refresh(pedido)

        return {
            "ok": True,
            "pedido": {
                "id": pedido.id,
                "aluno_id": pedido.aluno_id,
                "nome": pedido.nome,
                "cpf": pedido.cpf,
                "segundos": pedido.segundos or 5,
                "sentido": pedido.sentido or "ambos",
            },
        }
    finally:
        db.close()


def confirmar_liberacao_catraca_core(pedido_id: int, sucesso: bool, erro: str, token: str):
    token_esperado = os.getenv("AGENTE_CATRACA_TOKEN", "coliseu-agente-local-2026")
    if token != token_esperado:
        raise HTTPException(status_code=401, detail="Token inválido")

    db = SessionLocal()
    try:
        pedido = db.query(LiberacaoCatracaDB).filter(LiberacaoCatracaDB.id == pedido_id).first()
        if not pedido:
            raise HTTPException(status_code=404, detail="Pedido não encontrado")

        # Confirmação blindada: nunca tenta mexer em outras tabelas aqui.
        # O objetivo principal é tirar o pedido de em_execucao/pendente e marcar como executado/erro.
        if pedido.status == "executado":
            return {"ok": True, "pedido_id": pedido.id, "status": pedido.status}

        pedido.status = "executado" if sucesso else "erro"
        pedido.erro = (erro or None)
        pedido.executado_em = datetime.utcnow() if sucesso else None
        pedido.atualizado_em = datetime.utcnow()

        db.commit()
        db.refresh(pedido)

        return {
            "ok": True,
            "pedido_id": pedido.id,
            "status": pedido.status,
            "mensagem": "Pedido confirmado com sucesso.",
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        # Retorna detalhe para aparecer no navegador/Swagger, em vez de esconder como 500 genérico.
        raise HTTPException(status_code=500, detail=f"Erro ao confirmar catraca: {type(e).__name__}: {e}")
    finally:
        db.close()


@app.post("/agente/catraca/confirmar/{pedido_id}")
def agente_confirmar_liberacao_post(
    pedido_id: int,
    sucesso: bool = Query(default=True),
    erro: str = Query(default=""),
    token: str = Query(default=""),
):
    return confirmar_liberacao_catraca_core(pedido_id, sucesso, erro, token)


@app.get("/agente/catraca/confirmar/{pedido_id}")
def agente_confirmar_liberacao_get(
    pedido_id: int,
    sucesso: bool = Query(default=True),
    erro: str = Query(default=""),
    token: str = Query(default=""),
):
    # GET facilita teste manual pelo navegador. O agente pode usar POST.
    return confirmar_liberacao_catraca_core(pedido_id, sucesso, erro, token)


@app.post("/entrada/{aluno_id}")
def registrar_entrada(aluno_id: int, body: EntradaBody = Body(...)):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")

        status_aluno = obter_status_por_regras(aluno)
        codigo_qr = (body.codigo_qr or "").strip()

        if status_aluno not in {"em_dia", "pendente"}:
            item = EntradaDB(
                aluno_id=aluno.id,
                nome=aluno.nome,
                status="bloqueado",
                motivo=status_aluno or "bloqueado",
            )
            db.add(item)
            db.commit()
            return {
                "acesso": "bloqueado",
                "mensagem": "Aluno atrasado ou inativo. Regularize sua mensalidade.",
                "ir_para_pagamento": True,
            }

        if codigo_qr != QR_CATRACA.strip():
            item = EntradaDB(
                aluno_id=aluno.id,
                nome=aluno.nome,
                status="bloqueado",
                motivo="qr inválido",
            )
            db.add(item)
            db.commit()
            return {
                "acesso": "bloqueado",
                "mensagem": "QR da catraca inválido.",
                "ir_para_pagamento": False,
            }

        tipo_pass = plano_pass_tipo(aluno.plano_nome)
        if tipo_pass and not aluno_premium_admin(aluno):
            usados = pass_usados_hoje(db, aluno.id, tipo_pass)
            if usados >= 2:
                item = EntradaDB(
                    aluno_id=aluno.id,
                    nome=aluno.nome,
                    status="bloqueado",
                    motivo=f"{tipo_pass} — limite diário atingido",
                )
                db.add(item)
                db.commit()
                return {
                    "acesso": "bloqueado",
                    "mensagem": "Você já utilizou seus 2 acessos de hoje. Tente novamente amanhã.",
                    "ir_para_pagamento": False,
                    "pass_tipo": tipo_pass,
                    "usados_hoje": usados,
                }
            registrar_acesso_pass_automatico(db, aluno, tipo_pass, usados)
            db.commit()
            total_entradas = (
                db.query(EntradaDB)
                .filter(EntradaDB.aluno_id == aluno.id, EntradaDB.status == "liberado")
                .count()
            )
            return {
                "acesso": "liberado",
                "mensagem": f"Acesso liberado automaticamente via {tipo_pass}. Usado {usados + 1}/2 hoje.",
                "pass_tipo": tipo_pass,
                "usados_hoje": usados + 1,
                "total_entradas": total_entradas,
                "progresso": calcular_progresso(total_entradas),
            }

        item = EntradaDB(
            aluno_id=aluno.id,
            nome=aluno.nome,
            status="liberado",
            motivo="autorizada",
        )
        db.add(item)
        db.commit()

        total_entradas = (
            db.query(EntradaDB)
            .filter(EntradaDB.aluno_id == aluno.id, EntradaDB.status == "liberado")
            .count()
        )

        return {
            "acesso": "liberado",
            "mensagem": "Seu acesso foi liberado. Atenção: sua mensalidade está próxima do vencimento." if status_aluno == "pendente" else "Acesso liberado. Bom treino!",
            "total_entradas": total_entradas,
            "progresso": calcular_progresso(total_entradas),
        }
    finally:
        db.close()

@app.get("/entradas")
def listar_entradas():
    db = SessionLocal()
    try:
        entradas = db.query(EntradaDB).order_by(EntradaDB.data_entrada.desc()).all()
        saida = []
        for e in entradas:
            aluno = buscar_aluno_por_id(db, e.aluno_id)
            tipo_pass = plano_pass_tipo(getattr(aluno, "plano_nome", None)) if aluno else None
            motivo = e.motivo or ""
            motivo_lower = motivo.lower()
            if "total pass" in motivo_lower or "total_pass" in motivo_lower:
                tipo_pass = "Total Pass"
            elif "gympass" in motivo_lower:
                tipo_pass = "Gympass"
            usado_no_dia = pass_usados_hoje(db, e.aluno_id, tipo_pass) if tipo_pass else None
            saida.append({
                "id": e.id,
                "aluno_id": e.aluno_id,
                "nome": e.nome,
                "cpf": getattr(aluno, "cpf", None) if aluno else None,
                "plano_nome": getattr(aluno, "plano_nome", None) if aluno else None,
                "tipo_pass": tipo_pass,
                "usado_no_dia": usado_no_dia,
                "status": e.status,
                "motivo": e.motivo,
                "observacao": (f"acesso via {tipo_pass}" if tipo_pass else e.motivo),
                "data_entrada": e.data_entrada.isoformat() if e.data_entrada else None,
            })
        return saida
    finally:
        db.close()


@app.get("/aluno/{aluno_id}/progresso")
def progresso_aluno(aluno_id: int):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        total = (
            db.query(EntradaDB)
            .filter(EntradaDB.aluno_id == aluno.id, EntradaDB.status == "liberado")
            .count()
        )
        prog = calcular_progresso(total)
        metas = [10, 25, 50, 100, 200]
        proxima = prog.get("proxima_meta", 10)
        anterior = 0
        for meta in metas:
            if total < meta:
                proxima = meta
                break
            anterior = meta
        span = max(proxima - anterior, 1)
        percent = max(0, min(100, int(((total - anterior) / span) * 100)))
        return {
            "total_entradas": total,
            "nivel": prog.get("nivel"),
            "cor": prog.get("cor"),
            "titulo": "ADM/Premium" if aluno_premium_admin(aluno) else prog.get("nivel", "Começando").title(),
            "mensagem": "Acesso vitalício com privilégio ADM/Premium." if aluno_premium_admin(aluno) else prog.get("mensagem"),
            "proxima_meta": proxima,
            "metas": metas,
            "progresso_percent": percent,
        }
    finally:
        db.close()


@app.get("/passes/entradas")
def listar_passes_entradas(tipo: Optional[str] = Query(default=None), limite: int = Query(default=150)):
    db = SessionLocal()
    try:
        query = db.query(GympassSolicitacaoDB).order_by(GympassSolicitacaoDB.criado_em.desc())
        query = query.filter(GympassSolicitacaoDB.status == "liberado")
        if tipo:
            tipo_norm = plano_pass_tipo(tipo) or tipo.strip().title()
            query = query.filter(GympassSolicitacaoDB.tipo_pass.ilike(f"%{tipo_norm}%"))
        itens = query.limit(max(1, min(limite, 500))).all()
        return [
            {
                "id": g.id,
                "aluno_id": g.aluno_id,
                "nome": g.nome,
                "cpf": g.cpf,
                "tipo_pass": getattr(g, "tipo_pass", None) or "Gympass",
                "status": g.status,
                "usado_no_dia": g.usado_no_dia,
                "observacao": g.observacao,
                "data_entrada": g.liberado_em.isoformat() if g.liberado_em else (g.criado_em.isoformat() if g.criado_em else None),
                "criado_em": g.criado_em.isoformat() if g.criado_em else None,
                "liberado_em": g.liberado_em.isoformat() if g.liberado_em else None,
            }
            for g in itens
        ]
    finally:
        db.close()

@app.get("/passes/notificacoes")
def listar_passes_notificacoes(limite: int = Query(default=20)):
    db = SessionLocal()
    try:
        itens = (
            db.query(GympassSolicitacaoDB)
            .filter(GympassSolicitacaoDB.status == "liberado")
            .order_by(GympassSolicitacaoDB.criado_em.desc())
            .limit(max(1, min(limite, 100)))
            .all()
        )
        return [
            {
                "id": g.id,
                "mensagem": f"Novo acesso {getattr(g, 'tipo_pass', None) or 'Gympass'}: {g.nome} entrou.",
                "tipo_pass": getattr(g, "tipo_pass", None) or "Gympass",
                "nome": g.nome,
                "data_entrada": g.liberado_em.isoformat() if g.liberado_em else (g.criado_em.isoformat() if g.criado_em else None),
            }
            for g in itens
        ]
    finally:
        db.close()

# ----------------------
# Gympass / Total Pass legado
# ----------------------
@app.get("/gympass/solicitacoes")
def listar_gympass_solicitacoes(status: Optional[str] = Query(default=None), limite: int = Query(default=100)):
    db = SessionLocal()
    try:
        query = db.query(GympassSolicitacaoDB).order_by(GympassSolicitacaoDB.criado_em.desc())
        if status:
            query = query.filter(GympassSolicitacaoDB.status == status.strip().lower())
        itens = query.limit(max(1, min(limite, 300))).all()
        return [
            {
                "id": g.id,
                "aluno_id": g.aluno_id,
                "nome": g.nome,
                "cpf": g.cpf,
                "status": g.status,
                "tipo_pass": getattr(g, "tipo_pass", None) or "Gympass",
                "usado_no_dia": g.usado_no_dia,
                "liberado_por_id": g.liberado_por_id,
                "liberado_por_nome": g.liberado_por_nome,
                "observacao": g.observacao,
                "criado_em": g.criado_em.isoformat() if g.criado_em else None,
                "liberado_em": g.liberado_em.isoformat() if g.liberado_em else None,
            }
            for g in itens
        ]
    finally:
        db.close()

@app.post("/gympass/solicitacoes/{solicitacao_id}/liberar")
def liberar_gympass_solicitacao(solicitacao_id: int, body: GympassResponderBody = Body(default=GympassResponderBody())):
    db = SessionLocal()
    try:
        solicitacao = db.query(GympassSolicitacaoDB).filter(GympassSolicitacaoDB.id == solicitacao_id).first()
        if not solicitacao:
            raise HTTPException(status_code=404, detail="Solicitação Gympass não encontrada")
        if solicitacao.status == "liberado":
            return {"ok": True, "message": "Solicitação já liberada"}
        if solicitacao.status == "negado":
            raise HTTPException(status_code=400, detail="Solicitação já foi negada")
        aluno = buscar_aluno_por_id(db, solicitacao.aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        solicitacao.status = "liberado"
        solicitacao.liberado_por_id = body.liberado_por_id
        solicitacao.liberado_por_nome = body.liberado_por_nome or "ADM/Professor"
        solicitacao.observacao = body.observacao or "Acesso liberado manualmente (legado)"
        solicitacao.liberado_em = datetime.utcnow()
        solicitacao.atualizado_em = datetime.utcnow()
        pedido = LiberacaoCatracaDB(
            aluno_id=aluno.id, cpf=aluno.cpf, nome=aluno.nome, status="pendente",
            segundos=5, sentido="ambos", motivo="gympass", atualizado_em=datetime.utcnow(),
        )
        db.add(pedido)
        registrar_evento_entrada(db, aluno, "liberado", "gympass")
        db.commit()
        db.refresh(pedido)
        return {"ok": True, "message": "Acesso Gympass liberado", "pedido_id": pedido.id}
    finally:
        db.close()

@app.post("/gympass/solicitacoes/{solicitacao_id}/negar")
def negar_gympass_solicitacao(solicitacao_id: int, body: GympassResponderBody = Body(default=GympassResponderBody())):
    db = SessionLocal()
    try:
        solicitacao = db.query(GympassSolicitacaoDB).filter(GympassSolicitacaoDB.id == solicitacao_id).first()
        if not solicitacao:
            raise HTTPException(status_code=404, detail="Solicitação Gympass não encontrada")
        solicitacao.status = "negado"
        solicitacao.liberado_por_id = body.liberado_por_id
        solicitacao.liberado_por_nome = body.liberado_por_nome or "ADM/Professor"
        solicitacao.observacao = body.observacao or "Solicitação Gympass negada"
        solicitacao.atualizado_em = datetime.utcnow()
        db.commit()
        return {"ok": True, "message": "Solicitação Gympass negada"}
    finally:
        db.close()

# ----------------------
# Reembolso manual
# ----------------------
@app.post("/pagamentos/reembolso/{aluno_id}")
def reembolsar_ultimo_pagamento(aluno_id: int, body: ReembolsoBody = Body(default=ReembolsoBody())):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        pagamento = (
            db.query(PagamentoDB)
            .filter(
                PagamentoDB.aluno_id == aluno.id,
                PagamentoDB.status.in_(["pago", "aprovado"]),
            )
            .order_by(PagamentoDB.data_pagamento.desc(), PagamentoDB.id.desc())
            .first()
        )
        if not pagamento:
            raise HTTPException(status_code=404, detail="Nenhum pagamento válido encontrado para reembolso")
        vencimento_atual = aluno.vencimento
        aluno.vencimento = pagamento.vencimento_anterior
        aluno.updated_at = datetime.utcnow()
        pagamento.status = "reembolsado"
        pagamento.reembolsado_em = datetime.utcnow()
        pagamento.observacao = body.observacao or "Reembolso registrado manualmente pelo administrador"
        registro = PagamentoDB(
            aluno_id=aluno.id,
            plano_nome=pagamento.plano_nome,
            valor=-abs(float(pagamento.valor or 0)),
            dias=0,
            status="reembolso",
            origem="manual_admin_reembolso",
            data_pagamento=datetime.utcnow(),
            vencimento_anterior=vencimento_atual,
            novo_vencimento=aluno.vencimento,
            pagamento_reembolsado_id=pagamento.id,
            observacao=f"Reembolso do pagamento #{pagamento.id}. {body.observacao or ''}".strip(),
        )
        db.add(registro)
        db.commit()
        db.refresh(aluno)
        return {"ok": True, "message": "Reembolso registrado", "aluno": aluno_dict(db, aluno), "pagamento_reembolsado": pagamento_dict(pagamento)}
    finally:
        db.close()

# ----------------------
# Relatórios
# ----------------------
@app.get("/relatorio/resumo")
def relatorio_resumo():
    db = SessionLocal()
    try:
        alunos = db.query(AlunoDB).filter(or_(AlunoDB.deletado == False, AlunoDB.deletado.is_(None))).all()
        lista = [aluno_dict(db, a) for a in alunos]

        em_dia = [a for a in lista if a["status"] == "em_dia"]
        atrasados = [a for a in lista if a["status"] == "atrasado"]
        inativos = [a for a in lista if a["status"] == "inativo"]
        pendentes = [a for a in lista if a["status"] == "pendente"]

        potencial_atrasados = sum(float(a.get("valor_plano") or 0) for a in atrasados)
        faturamento_real = sum(float(a.get("valor_plano") or 0) for a in em_dia)

        return {
            "total_alunos": len(lista),
            "em_dia": len(em_dia),
            "atrasados": len(atrasados),
            "inativos": len(inativos),
            "pendentes": len(pendentes),
            "faturamento_real": faturamento_real,
            "potencial_atrasados": potencial_atrasados,
        }
    finally:
        db.close()

@app.get("/relatorio/texto/{tipo}")
def relatorio_texto(tipo: Literal["ativos", "atrasados", "inativos"]):
    db = SessionLocal()
    try:
        alunos = [aluno_dict(db, a) for a in db.query(AlunoDB).filter(or_(AlunoDB.deletado == False, AlunoDB.deletado.is_(None))).order_by(AlunoDB.nome.asc()).all()]
        mapa = {
            "ativos": "em_dia",
            "atrasados": "atrasado",
            "inativos": "inativo",
        }
        status_alvo = mapa[tipo]
        filtrados = [a for a in alunos if a["status"] == status_alvo]

        linhas = [f"Relatório ColiseuFit - {tipo.upper()}", f"Gerado em: {agora_str()}", ""]
        for idx, a in enumerate(filtrados, start=1):
            linhas.append(
                f"{idx}. {a['nome']} | CPF: {a['cpf']} | Telefone: {a['telefone'] or '-'} | "
                f"Plano: {a['plano_nome'] or '-'} | Vencimento: {a['vencimento'] or '-'}"
            )
        if not filtrados:
            linhas.append("Nenhum aluno encontrado.")
        return PlainTextResponse("\n".join(linhas), media_type="text/plain; charset=utf-8")
    finally:
        db.close()


class PagamentoLinkBody(BaseModel):
    aluno_id: int
    plano: Optional[str] = None

@app.post("/pagamentos/link")
def criar_link_pagamento(body: PagamentoLinkBody):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, body.aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")

        plano_key = (body.plano or aluno.plano_nome or "mensal").strip().lower()
        mapa = {
            "mensal": "mensal",
            "semestral": "semestral",
            "anual": "anual",
            "promocional": "promocional",
        }
        plano_key = mapa.get(plano_key, "mensal")
        link = obter_link_plano(db, plano_key)

        if not link:
            # fallback para handle direto
            link = f"https://link.infinitepay.io/{INFINITEPAY_HANDLE}"

        return {
            "ok": True,
            "url": link,
            "checkout_url": link,
            "plano": plano_key,
            "aluno_id": aluno.id,
        }
    finally:
        db.close()

@app.put("/pagar/{aluno_id}")
def registrar_pagamento_alias(aluno_id: int, body: PagamentoBody):
    return registrar_pagamento(aluno_id, body)

@app.get("/aluno/{aluno_id}/treinos")
def listar_treinos_alias(aluno_id: int):
    return listar_treinos(aluno_id)

@app.put("/alunos/{aluno_id}/foto")
def atualizar_foto_aluno_alias(aluno_id: int, body: FotoAlunoBody):
    return atualizar_foto_aluno(aluno_id, body)

@app.put("/config/planos/promocional")
def atualizar_promocional_alias(valor: float = Query(...), dias: int = Query(PROMOCIONAL_DIAS_PADRAO)):
    return atualizar_promocional(PromocionalConfigBody(valor=valor, dias=dias))

@app.get("/relatorios/txt")
def relatorio_texto_completo():
    db = SessionLocal()
    try:
        alunos = [aluno_dict(db, a) for a in db.query(AlunoDB).filter(or_(AlunoDB.deletado == False, AlunoDB.deletado.is_(None))).order_by(AlunoDB.nome.asc()).all()]
        pagamentos = db.query(PagamentoDB).order_by(PagamentoDB.data_pagamento.desc()).all()

        em_dia = [a for a in alunos if a["status"] == "em_dia"]
        atrasados = [a for a in alunos if a["status"] == "atrasado"]
        inativos = [a for a in alunos if a["status"] == "inativo"]
        pendentes = [a for a in alunos if a["status"] == "pendente"]

        potencial = sum(float(a.get("valor_final") or a.get("valor_plano") or 0) for a in atrasados)

        linhas = []
        linhas.append("COLISEUFIT - RELATÓRIO GERAL")
        linhas.append("")
        linhas.append(f"Total de alunos: {len(alunos)}")
        linhas.append(f"Em dia: {len(em_dia)}")
        linhas.append(f"Atrasados: {len(atrasados)}")
        linhas.append(f"Inativos: {len(inativos)}")
        linhas.append(f"Pendentes: {len(pendentes)}")
        linhas.append(f"Potencial de ganho (somente atrasados): R$ {potencial:.2f}")
        linhas.append("")

        def bloco(titulo, lista):
            linhas.append(f"=== {titulo} ({len(lista)}) ===")
            if not lista:
                linhas.append("Nenhum registro.")
            else:
                for a in lista:
                    linhas.append(
                        f"{a['nome']} | CPF: {a['cpf']} | Telefone: {a.get('telefone') or '-'} | "
                        f"Plano: {a.get('plano_nome') or '-'} | Vencimento: {a.get('vencimento') or '-'}"
                    )
            linhas.append("")

        bloco("EM DIA", em_dia)
        bloco("ATRASADOS", atrasados)
        bloco("INATIVOS", inativos)
        bloco("PENDENTES", pendentes)

        linhas.append(f"=== PAGAMENTOS REGISTRADOS ({len(pagamentos)}) ===")
        if not pagamentos:
            linhas.append("Nenhum pagamento registrado.")
        else:
            for p in pagamentos[:300]:
                nome = p.aluno.nome if getattr(p, "aluno", None) else str(p.aluno_id)
                linhas.append(
                    f"{nome} | Plano: {p.plano_nome} | Valor: R$ {p.valor:.2f} | "
                    f"Data: {p.data_pagamento.strftime('%Y-%m-%d %H:%M')} | Novo vencimento: {p.novo_vencimento or '-'}"
                )

        return PlainTextResponse("\n".join(linhas), media_type="text/plain; charset=utf-8")
    finally:
        db.close()


# ----------------------
# Compatibilidade com Flutter antigo/aprovado
# ----------------------
@app.get("/aluno/login")
def aluno_login(cpf: str):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_cpf(db, cpf)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")

        avisos_nao_lidos_qtd = 0
        try:
            nao_lidos = db.query(AvisoLeituraDB).filter(AvisoLeituraDB.aluno_id == aluno.id).count()
            total_avisos = db.query(AvisoDB).count()
            avisos_nao_lidos_qtd = max(total_avisos - nao_lidos, 0)
        except Exception:
            db.rollback()
            avisos_nao_lidos_qtd = 0

        return {
            "ok": True,
            "aluno": aluno_dict(db, aluno),
            "avisos_nao_lidos": avisos_nao_lidos_qtd,
        }
    finally:
        db.close()

@app.get("/relatorio/planos")
def relatorio_planos():
    db = SessionLocal()
    try:
        alunos = [aluno_dict(db, a) for a in db.query(AlunoDB).filter(or_(AlunoDB.deletado == False, AlunoDB.deletado.is_(None))).all()]
        nomes = ["Mensal", "Semestral", "Anual", "Promocional", "Diária", "Gympass", "Total Pass"]
        contagem = {n: 0 for n in nomes}
        for a in alunos:
            plano = (a.get("plano_nome") or "").strip().title()
            if plano in contagem:
                contagem[plano] += 1
        return contagem
    finally:
        db.close()

@app.get("/relatorio/vendas")
def relatorio_vendas(periodo: str = "mes"):
    db = SessionLocal()
    try:
        pagamentos = db.query(PagamentoDB).order_by(PagamentoDB.data_pagamento.desc()).all()
        total = sum(float(p.valor or 0) for p in pagamentos)
        quantidade = len(pagamentos)
        return {
            "periodo": periodo,
            "total": total,
            "quantidade": quantidade,
        }
    finally:
        db.close()

@app.get("/historico")
def historico_alias():
    db = SessionLocal()
    try:
        pagamentos = db.query(PagamentoDB).order_by(PagamentoDB.data_pagamento.desc()).all()
        return [
            {
                "id": p.id,
                "aluno_id": p.aluno_id,
                "nome": p.aluno.nome if getattr(p, "aluno", None) else str(p.aluno_id),
                "plano_nome": p.plano_nome,
                "valor": float(p.valor or 0),
                "dias": int(p.dias or 0),
                "status": p.status,
                "origem": p.origem,
                "order_nsu": p.order_nsu,
                "link_pagamento": p.link_pagamento,
                "data_pagamento": p.data_pagamento.isoformat() if p.data_pagamento else None,
                "novo_vencimento": p.novo_vencimento,
                "vencimento_anterior": p.vencimento_anterior,
                "reembolsado_em": p.reembolsado_em.isoformat() if getattr(p, "reembolsado_em", None) else None,
                "pagamento_reembolsado_id": getattr(p, "pagamento_reembolsado_id", None),
                "observacao": getattr(p, "observacao", None),
            }
            for p in pagamentos
        ]
    finally:
        db.close()

@app.delete("/avisos/{aviso_id}")
def excluir_aviso(aviso_id: int):
    db = SessionLocal()
    try:
        aviso = db.query(AvisoDB).filter(AvisoDB.id == aviso_id).first()
        if not aviso:
            raise HTTPException(status_code=404, detail="Aviso não encontrado")

        # Primeiro apaga as leituras vinculadas ao aviso.
        # Sem isso o PostgreSQL pode bloquear a exclusão por causa da FK
        # avisos_leituras.aviso_id -> avisos.id.
        db.query(AvisoLeituraDB).filter(AvisoLeituraDB.aviso_id == aviso_id).delete(synchronize_session=False)
        db.delete(aviso)
        db.commit()
        return {"ok": True, "message": "Aviso excluído com sucesso"}
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        return JSONResponse(status_code=500, content={"ok": False, "error": f"Erro ao excluir aviso: {str(e)}"})
    finally:
        db.close()

@app.get("/aluno/{aluno_id}/avisos")
def avisos_aluno(aluno_id: int):
    # Avisos estão em manutenção; mantém compatibilidade do Flutter sem erro 500.
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        try:
            avisos = db.query(AvisoDB).order_by(AvisoDB.data.desc()).all()
            lidos_ids = {
                item.aviso_id for item in db.query(AvisoLeituraDB).filter(AvisoLeituraDB.aluno_id == aluno_id).all()
            }
            return {
                "avisos": [
                    {
                        "id": a.id,
                        "titulo": a.titulo,
                        "mensagem": a.mensagem,
                        "imagem_base64": a.imagem_base64,
                        "data": a.data.isoformat() if a.data else None,
                        "lido": a.id in lidos_ids,
                    }
                    for a in avisos
                ],
                "nao_lidos": sum(1 for a in avisos if a.id not in lidos_ids),
            }
        except Exception:
            db.rollback()
            return {"avisos": [], "nao_lidos": 0}
    finally:
        db.close()

@app.post("/aluno/{aluno_id}/avisos/{aviso_id}/ler")
def marcar_aviso_lido_compat(aluno_id: int, aviso_id: int):
    db = SessionLocal()
    try:
        try:
            existe = (
                db.query(AvisoLeituraDB)
                .filter(AvisoLeituraDB.aluno_id == aluno_id, AvisoLeituraDB.aviso_id == aviso_id)
                .first()
            )
            if not existe:
                db.add(AvisoLeituraDB(aluno_id=aluno_id, aviso_id=aviso_id, lido=True))
            db.commit()
        except Exception:
            db.rollback()
        return {"ok": True}
    finally:
        db.close()

@app.post("/pagamentos/criar")
def criar_pagamento_checkout_compat(body: CriarPagamentoCheckoutBody, db=Depends(get_db)):
    try:
        aluno = buscar_aluno_por_id(db, int(body.aluno_id))
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")

        if processar_inativacao_por_atraso(db, aluno):
            db.commit()
            db.refresh(aluno)

        # Segurança: aluno renova apenas o plano atual com o valor final gravado no cadastro.
        # Ignoramos valor vindo do frontend para evitar cobrança incorreta.
        juros_checkout = juros_atraso_aluno(aluno)
        valor_final = valor_final_aluno(db, aluno)
        valor_final = round(max(valor_final, 1.0), 2)

        plano_final = (aluno.plano_nome or body.plano_nome or "Mensal").strip()
        dias_final = int(body.dias) if body.dias is not None else dias_por_plano(plano_final)
        valor_centavos = int(round(valor_final * 100))
        order_nsu = f"aluno_{aluno.id}_{int(datetime.utcnow().timestamp())}"

        checkout_payload = {
            "handle": INFINITEPAY_HANDLE,
            "items": [
                {
                    "name": f"Plano {plano_final} - Coliseu Fit",
                    "description": f"Plano {plano_final} - {dias_final} dias",
                    "quantity": 1,
                    "price": valor_centavos,
                }
            ],
            "order_nsu": order_nsu,
            "redirect_url": f"{PUBLIC_BASE_URL}/pagamentos/retorno",
            "webhook_url": f"{PUBLIC_BASE_URL}/webhooks/infinitepay",
        }

        resp = requests.post(INFINITEPAY_CHECKOUT_URL, json=checkout_payload, timeout=30)

        try:
            data = resp.json()
        except Exception:
            data = {"raw": resp.text}

        if resp.status_code not in (200, 201):
            raise HTTPException(status_code=502, detail=f"InfinitePay: {data}")

        checkout_url = (
            data.get("url")
            or data.get("checkout_url")
            or data.get("link")
            or data.get("payment_url")
            or (data.get("data") or {}).get("url")
            or (data.get("data") or {}).get("checkout_url")
            or (data.get("invoice") or {}).get("url")
        )

        if not checkout_url:
            raise HTTPException(status_code=502, detail=f"Resposta inesperada da InfinitePay: {data}")

        pagamento = PagamentoDB(
            aluno_id=aluno.id,
            plano_nome=plano_final,
            valor=valor_final,
            dias=dias_final,
            status="pendente",
            origem="infinitepay",
            link_pagamento=checkout_url,
            order_nsu=order_nsu,
            data_pagamento=datetime.utcnow(),
            vencimento_anterior=aluno.vencimento,
            novo_vencimento=calcular_novo_vencimento_fixo(aluno, dias_final, plano_final),
            valor_juros=juros_checkout,
        )
        db.add(pagamento)
        db.commit()
        db.refresh(pagamento)

        return {
            "ok": True,
            "modo": "checkout_dinamico",
            "checkout_url": checkout_url,
            "order_nsu": order_nsu,
            "pagamento": pagamento_dict(pagamento),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/webhooks/infinitepay")
def webhook_infinitepay(body: Optional[dict] = Body(default=None), db=Depends(get_db)):
    """
    Webhook seguro da InfinitePay.

    Regra principal:
    - cada checkout é criado com order_nsu único;
    - esse order_nsu fica salvo na tabela pagamentos;
    - o webhook só aprova o pagamento que tiver o mesmo order_nsu;
    - se o webhook repetir, não renova o aluno duas vezes.
    """
    payload = body or {}

    def nested_get(data, *keys):
        atual = data
        for key in keys:
            if not isinstance(atual, dict):
                return None
            atual = atual.get(key)
        return atual

    order_nsu = (
        payload.get("order_nsu")
        or payload.get("orderNsu")
        or payload.get("order")
        or payload.get("order_id")
        or payload.get("external_id")
        or nested_get(payload, "data", "order_nsu")
        or nested_get(payload, "data", "orderNsu")
        or nested_get(payload, "data", "order")
        or nested_get(payload, "data", "order_id")
        or nested_get(payload, "data", "external_id")
        or nested_get(payload, "invoice", "order_nsu")
        or nested_get(payload, "invoice", "orderNsu")
        or nested_get(payload, "invoice", "order")
        or nested_get(payload, "invoice", "order_id")
        or nested_get(payload, "invoice", "external_id")
    )
    order_nsu = str(order_nsu or "").strip()

    transaction_status = str(
        payload.get("status")
        or payload.get("payment_status")
        or payload.get("transaction_status")
        or nested_get(payload, "data", "status")
        or nested_get(payload, "data", "payment_status")
        or nested_get(payload, "data", "transaction_status")
        or nested_get(payload, "invoice", "status")
        or ""
    ).strip().lower()

    event_name = str(
        payload.get("event")
        or payload.get("event_name")
        or payload.get("type")
        or nested_get(payload, "data", "event")
        or nested_get(payload, "data", "type")
        or ""
    ).strip().lower()

    if not order_nsu:
        return {
            "ok": True,
            "mensagem": "webhook recebido sem order_nsu; nenhum aluno foi alterado",
            "status": transaction_status or event_name or "desconhecido",
        }

    pagamento = (
        db.query(PagamentoDB)
        .filter(PagamentoDB.order_nsu == order_nsu)
        .first()
    )

    if not pagamento:
        return {
            "ok": True,
            "mensagem": "pagamento não encontrado para este order_nsu; nenhum aluno foi alterado",
            "order_nsu": order_nsu,
            "status": transaction_status or event_name or "desconhecido",
        }

    status_aprovado = {"paid", "approved", "completed", "success", "succeeded", "confirmed", "authorized", "captured", "paid_out"}
    evento_aprovado = {"paid", "payment.paid", "invoice.paid", "charge.paid", "checkout.paid", "transaction.paid", "transaction.approved", "payment.approved"}
    status_cancelado = {"canceled", "cancelled", "failed", "refused", "denied", "expired", "voided", "rejected"}

    # A InfinitePay pode chamar o webhook sem um campo status claro, mas com dados de transação/recibo.
    # Quando existe order_nsu + transaction_id/transaction_nsu/receipt_url/capture_method, consideramos pagamento confirmado.
    sinal_pagamento_real = bool(
        payload.get("transaction_id")
        or payload.get("transaction_nsu")
        or payload.get("receipt_url")
        or payload.get("capture_method")
        or nested_get(payload, "data", "transaction_id")
        or nested_get(payload, "data", "transaction_nsu")
        or nested_get(payload, "data", "receipt_url")
        or nested_get(payload, "data", "capture_method")
        or nested_get(payload, "transaction", "id")
        or nested_get(payload, "transaction", "nsu")
        or nested_get(payload, "transaction", "receipt_url")
    )

    aprovado = transaction_status in status_aprovado or event_name in evento_aprovado or sinal_pagamento_real
    cancelado = transaction_status in status_cancelado

    if aprovado:
        # Idempotência: webhook pode chegar mais de uma vez. Não renova duas vezes.
        if str(pagamento.status or "").lower() in {"aprovado", "pago", "paid", "approved", "completed"}:
            return {
                "ok": True,
                "mensagem": "pagamento já estava aprovado; aluno não foi renovado novamente",
                "order_nsu": order_nsu,
                "pagamento": pagamento_dict(pagamento),
            }

        aluno = buscar_aluno_por_id(db, pagamento.aluno_id)
        if not aluno:
            return {
                "ok": True,
                "mensagem": "pagamento encontrado, mas aluno não existe mais; nenhum aluno foi alterado",
                "order_nsu": order_nsu,
                "pagamento_id": pagamento.id,
            }

        pagamento.status = "aprovado"
        novo_vencimento = aplicar_pagamento_aluno(
            db,
            aluno,
            pagamento.plano_nome,
            float(pagamento.valor or 0),
            int(pagamento.dias or 30),
        )
        pagamento.novo_vencimento = novo_vencimento
        db.commit()
        db.refresh(pagamento)

        return {
            "ok": True,
            "mensagem": "pagamento aprovado e aluno atualizado para em dia",
            "order_nsu": order_nsu,
            "pagamento": pagamento_dict(pagamento),
            "aluno": aluno_dict(db, aluno),
        }

    if cancelado:
        if str(pagamento.status or "").lower() == "pendente":
            pagamento.status = "cancelado"
            db.commit()
            db.refresh(pagamento)
        return {
            "ok": True,
            "mensagem": "pagamento cancelado/recusado recebido; aluno não foi alterado",
            "order_nsu": order_nsu,
            "pagamento": pagamento_dict(pagamento),
        }

    return {
        "ok": True,
        "mensagem": "webhook recebido, mas status ainda não é aprovação",
        "order_nsu": order_nsu,
        "status": transaction_status or event_name or "desconhecido",
        "pagamento": pagamento_dict(pagamento),
    }



# ----------------------
# Juros / Chat
# ----------------------
@app.post("/pagamentos/retirar-juros/{aluno_id}")
def retirar_juros_aluno(aluno_id: int, body: RetirarJurosBody = Body(default_factory=RetirarJurosBody)):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        juros_atual = juros_atraso_aluno(aluno)
        aluno.juros_perdoado_vencimento = aluno.vencimento
        aluno.juros_perdoado_em = datetime.utcnow()
        aluno.juros_perdoado_por = body.usuario_admin or "ADM"
        aluno.updated_at = datetime.utcnow()
        registro = PagamentoDB(
            aluno_id=aluno.id,
            plano_nome=aluno.plano_nome or "Juros",
            valor=0.0,
            dias=0,
            status="juros_retirado",
            origem="manual_admin",
            data_pagamento=datetime.utcnow(),
            vencimento_anterior=aluno.vencimento,
            novo_vencimento=aluno.vencimento,
            observacao=body.observacao or "Juros retirado manualmente pelo administrador",
            tipo_evento="juros_retirado",
            valor_juros=juros_atual,
        )
        db.add(registro)
        db.commit()
        db.refresh(aluno)
        return {"ok": True, "message": "Multa retirada com sucesso", "juros_retirado": juros_atual, "aluno": aluno_dict(db, aluno)}
    finally:
        db.close()

def get_or_create_conversa(db, aluno_id: int) -> ConversaChatDB:
    conversa = db.query(ConversaChatDB).filter(ConversaChatDB.aluno_id == aluno_id).first()
    if conversa:
        return conversa
    conversa = ConversaChatDB(aluno_id=aluno_id, criada_em=datetime.utcnow(), atualizada_em=datetime.utcnow(), ultima_mensagem_em=datetime.utcnow())
    db.add(conversa)
    db.commit()
    db.refresh(conversa)
    return conversa

def conversa_dict(db, conversa: ConversaChatDB) -> dict:
    aluno = buscar_aluno_por_id(db, conversa.aluno_id, incluir_deletados=False)
    ultima = db.query(MensagemChatDB).filter(MensagemChatDB.conversa_id == conversa.id).order_by(MensagemChatDB.criada_em.desc()).first()
    return {
        "id": conversa.id,
        "aluno_id": conversa.aluno_id,
        "aluno_nome": aluno.nome if aluno else "Aluno",
        "aluno_cpf": aluno.cpf if aluno else "",
        "aluno_telefone": aluno.telefone if aluno else "",
        "ultima_mensagem": ultima.mensagem if ultima else "",
        "ultima_mensagem_em": (ultima.criada_em.isoformat() if ultima and ultima.criada_em else (conversa.ultima_mensagem_em.isoformat() if conversa.ultima_mensagem_em else None)),
        "mensagens_nao_lidas_professor": conversa.mensagens_nao_lidas_professor or 0,
        "mensagens_nao_lidas_aluno": conversa.mensagens_nao_lidas_aluno or 0,
        "status": conversa.status,
    }

def mensagem_dict(msg: MensagemChatDB) -> dict:
    return {
        "id": msg.id,
        "conversa_id": msg.conversa_id,
        "aluno_id": msg.aluno_id,
        "remetente_tipo": msg.remetente_tipo,
        "remetente_id": msg.remetente_id,
        "remetente_nome": msg.remetente_nome,
        "mensagem": msg.mensagem,
        "criada_em": msg.criada_em.isoformat() if msg.criada_em else None,
        "lida_em": msg.lida_em.isoformat() if msg.lida_em else None,
        "status": msg.status,
    }

def validar_professor_chat(db, professor_id: int) -> AlunoDB:
    prof = buscar_aluno_por_id(db, professor_id)
    if not prof or not aluno_premium_admin(prof) or not bool(getattr(prof, "pode_atender_chat", False)):
        raise HTTPException(status_code=403, detail="Professor sem permissão para atender chat")
    return prof

@app.get("/chat/minha-conversa")
def chat_minha_conversa(aluno_id: int = Query(...)):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        conversa = get_or_create_conversa(db, aluno_id)
        return conversa_dict(db, conversa)
    finally:
        db.close()

@app.get("/chat/minha-conversa/mensagens")
def chat_minhas_mensagens(aluno_id: int = Query(...)):
    db = SessionLocal()
    try:
        conversa = get_or_create_conversa(db, aluno_id)
        mensagens = db.query(MensagemChatDB).filter(MensagemChatDB.conversa_id == conversa.id).order_by(MensagemChatDB.criada_em.asc()).all()
        return [mensagem_dict(m) for m in mensagens]
    finally:
        db.close()

@app.post("/chat/minha-conversa/mensagens")
def chat_enviar_aluno(body: ChatMensagemBody = Body(...)):
    db = SessionLocal()
    try:
        aluno_id = int(body.aluno_id or 0)
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        msg_txt = (body.mensagem or "").strip()
        if not msg_txt:
            raise HTTPException(status_code=400, detail="Mensagem vazia")
        conversa = get_or_create_conversa(db, aluno_id)
        msg = MensagemChatDB(conversa_id=conversa.id, aluno_id=aluno_id, remetente_tipo="aluno", remetente_id=aluno_id, remetente_nome=aluno.nome, mensagem=msg_txt, criada_em=datetime.utcnow())
        conversa.atualizada_em = datetime.utcnow()
        conversa.ultima_mensagem_em = msg.criada_em
        conversa.mensagens_nao_lidas_professor = int(conversa.mensagens_nao_lidas_professor or 0) + 1
        db.add(msg)
        db.commit()
        db.refresh(msg)
        return {"ok": True, "mensagem": mensagem_dict(msg), "conversa": conversa_dict(db, conversa)}
    finally:
        db.close()

@app.post("/chat/minha-conversa/marcar-lidas")
def chat_aluno_marcar_lidas(aluno_id: int = Query(...)):
    db = SessionLocal()
    try:
        conversa = get_or_create_conversa(db, aluno_id)
        now = datetime.utcnow()
        db.query(MensagemChatDB).filter(MensagemChatDB.conversa_id == conversa.id, MensagemChatDB.remetente_tipo.in_(["professor", "adm"]), MensagemChatDB.lida_em.is_(None)).update({MensagemChatDB.lida_em: now}, synchronize_session=False)
        conversa.mensagens_nao_lidas_aluno = 0
        conversa.atualizada_em = now
        db.commit()
        return {"ok": True}
    finally:
        db.close()

@app.get("/chat/conversas")
def chat_conversas(professor_id: int = Query(...)):
    db = SessionLocal()
    try:
        validar_professor_chat(db, professor_id)
        conversas = db.query(ConversaChatDB).order_by(ConversaChatDB.ultima_mensagem_em.desc().nullslast(), ConversaChatDB.atualizada_em.desc()).all()
        return [conversa_dict(db, c) for c in conversas]
    finally:
        db.close()

@app.get("/chat/conversas/{conversa_id}/mensagens")
def chat_conversa_mensagens(conversa_id: int, professor_id: int = Query(...)):
    db = SessionLocal()
    try:
        validar_professor_chat(db, professor_id)
        conversa = db.query(ConversaChatDB).filter(ConversaChatDB.id == conversa_id).first()
        if not conversa:
            raise HTTPException(status_code=404, detail="Conversa não encontrada")
        mensagens = db.query(MensagemChatDB).filter(MensagemChatDB.conversa_id == conversa_id).order_by(MensagemChatDB.criada_em.asc()).all()
        return {"conversa": conversa_dict(db, conversa), "mensagens": [mensagem_dict(m) for m in mensagens]}
    finally:
        db.close()

@app.post("/chat/conversas/{conversa_id}/mensagens")
def chat_professor_responder(conversa_id: int, body: ChatMensagemBody = Body(...)):
    db = SessionLocal()
    try:
        professor_id = int(body.professor_id or body.remetente_id or 0)
        prof = validar_professor_chat(db, professor_id)
        conversa = db.query(ConversaChatDB).filter(ConversaChatDB.id == conversa_id).first()
        if not conversa:
            raise HTTPException(status_code=404, detail="Conversa não encontrada")
        msg_txt = (body.mensagem or "").strip()
        if not msg_txt:
            raise HTTPException(status_code=400, detail="Mensagem vazia")
        msg = MensagemChatDB(conversa_id=conversa_id, aluno_id=conversa.aluno_id, remetente_tipo="professor", remetente_id=professor_id, remetente_nome=prof.nome, mensagem=msg_txt, criada_em=datetime.utcnow())
        conversa.atualizada_em = datetime.utcnow()
        conversa.ultima_mensagem_em = msg.criada_em
        conversa.mensagens_nao_lidas_aluno = int(conversa.mensagens_nao_lidas_aluno or 0) + 1
        db.add(msg)
        db.commit()
        db.refresh(msg)
        return {"ok": True, "mensagem": mensagem_dict(msg), "conversa": conversa_dict(db, conversa)}
    finally:
        db.close()

@app.post("/chat/conversas/{conversa_id}/marcar-lidas")
def chat_professor_marcar_lidas(conversa_id: int, professor_id: int = Query(...)):
    db = SessionLocal()
    try:
        validar_professor_chat(db, professor_id)
        conversa = db.query(ConversaChatDB).filter(ConversaChatDB.id == conversa_id).first()
        if not conversa:
            raise HTTPException(status_code=404, detail="Conversa não encontrada")
        now = datetime.utcnow()
        db.query(MensagemChatDB).filter(MensagemChatDB.conversa_id == conversa_id, MensagemChatDB.remetente_tipo == "aluno", MensagemChatDB.lida_em.is_(None)).update({MensagemChatDB.lida_em: now}, synchronize_session=False)
        conversa.mensagens_nao_lidas_professor = 0
        conversa.atualizada_em = now
        db.commit()
        return {"ok": True}
    finally:
        db.close()

@app.get("/admin/professores-chat")
def admin_professores_chat():
    db = SessionLocal()
    try:
        professores = db.query(AlunoDB).filter(AlunoDB.premium_admin == True, or_(AlunoDB.deletado == False, AlunoDB.deletado.is_(None))).order_by(AlunoDB.nome.asc()).all()
        return [aluno_dict(db, p) for p in professores]
    finally:
        db.close()

@app.patch("/admin/professores-chat/{professor_id}")
def admin_alterar_professor_chat(professor_id: int, body: ProfessorChatPermissaoBody = Body(...)):
    db = SessionLocal()
    try:
        prof = buscar_aluno_por_id(db, professor_id)
        if not prof or not aluno_premium_admin(prof):
            raise HTTPException(status_code=404, detail="Professor/Premium não encontrado")
        prof.pode_atender_chat = bool(body.pode_atender_chat)
        prof.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(prof)
        return {"ok": True, "professor": aluno_dict(db, prof)}
    finally:
        db.close()

@app.get("/pagamentos/retorno")
def retorno_pagamento_infinitepay(
    order_nsu: Optional[str] = Query(default=None),
    transaction_id: Optional[str] = Query(default=None),
    transaction_nsu: Optional[str] = Query(default=None),
    receipt_url: Optional[str] = Query(default=None),
    capture_method: Optional[str] = Query(default=None),
):
    """Fallback de retorno da InfinitePay.
    Se o cliente voltar para o backend com order_nsu e dados de transação, aprova o pagamento.
    Isso complementa o webhook POST e evita deixar aluno pendente quando a InfinitePay não envia status claro.
    """
    if not order_nsu:
        return RedirectResponse(url=FRONTEND_URL)

    db = SessionLocal()
    try:
        pagamento = db.query(PagamentoDB).filter(PagamentoDB.order_nsu == str(order_nsu).strip()).first()
        if pagamento and str(pagamento.status or "").lower() not in {"aprovado", "pago", "paid", "approved", "completed"}:
            aluno = buscar_aluno_por_id(db, pagamento.aluno_id)
            if aluno:
                pagamento.status = "aprovado"
                novo_vencimento = aplicar_pagamento_aluno(
                    db,
                    aluno,
                    pagamento.plano_nome,
                    float(pagamento.valor or 0),
                    int(pagamento.dias or 30),
                )
                pagamento.novo_vencimento = novo_vencimento
                db.commit()
        return RedirectResponse(url=FRONTEND_URL)
    except Exception:
        db.rollback()
        return RedirectResponse(url=FRONTEND_URL)
    finally:
        db.close()


# ----------------------
# Pré-cadastro / Sou novo aqui
# ----------------------
@app.post("/pre-cadastros")
def criar_pre_cadastro(body: PreCadastroCreate):
    db = SessionLocal()
    try:
        cpf = only_digits(body.cpf)
        if len(cpf) != 11:
            raise HTTPException(status_code=400, detail="CPF inválido")
        if db.query(AlunoDB).filter(or_(AlunoDB.deletado == False, AlunoDB.deletado.is_(None)), AlunoDB.cpf == cpf).first():
            raise HTTPException(status_code=400, detail="CPF já cadastrado como aluno")
        existente = db.query(PreCadastroAlunoDB).filter(PreCadastroAlunoDB.cpf == cpf, PreCadastroAlunoDB.status == "aguardando_aprovacao").first()
        if existente:
            raise HTTPException(status_code=400, detail="Já existe um cadastro aguardando aprovação para este CPF")
        item = PreCadastroAlunoDB(nome=body.nome.strip(), telefone=(body.telefone or "").strip(), cpf=cpf, status="aguardando_aprovacao")
        db.add(item)
        db.commit()
        db.refresh(item)
        return {"ok": True, "mensagem": "Cadastro enviado com sucesso. Aguarde a academia validar seu acesso.", "id": item.id}
    finally:
        db.close()

@app.get("/pre-cadastros")
def listar_pre_cadastros(status: Optional[str] = Query(default="aguardando_aprovacao")):
    db = SessionLocal()
    try:
        query = db.query(PreCadastroAlunoDB).order_by(PreCadastroAlunoDB.criado_em.desc())
        if status:
            query = query.filter(PreCadastroAlunoDB.status == status)
        return [
            {
                "id": p.id, "nome": p.nome, "telefone": p.telefone, "cpf": p.cpf, "status": p.status,
                "observacao": p.observacao, "criado_em": p.criado_em.isoformat() if p.criado_em else None,
                "aprovado_em": p.aprovado_em.isoformat() if p.aprovado_em else None,
                "recusado_em": p.recusado_em.isoformat() if p.recusado_em else None,
            } for p in query.all()
        ]
    finally:
        db.close()

@app.post("/pre-cadastros/{pre_id}/aprovar")
def aprovar_pre_cadastro(pre_id: int, body: PreCadastroAprovarBody):
    db = SessionLocal()
    try:
        pre = db.query(PreCadastroAlunoDB).filter(PreCadastroAlunoDB.id == pre_id).first()
        if not pre:
            raise HTTPException(status_code=404, detail="Pré-cadastro não encontrado")
        if db.query(AlunoDB).filter(or_(AlunoDB.deletado == False, AlunoDB.deletado.is_(None)), AlunoDB.cpf == pre.cpf).first():
            raise HTTPException(status_code=400, detail="CPF já cadastrado como aluno")
        plano = info_plano(db, (body.plano_nome or "Mensal").lower().replace("á", "a"), dias_override=body.dias_plano) if body.plano_nome else info_plano(db, "mensal")
        body_premium = bool(getattr(body, "premium_admin", False))
        body_acesso_livre = bool(getattr(body, "acesso_livre", False)) and not body_premium
        body_sem_cobranca = body_premium or body_acesso_livre
        vencimento = normalizar_data_texto(body.vencimento)
        inicio = normalizar_data_texto(body.data_inicio_plano) or hoje_str()
        dia_fixo = clamp_dia_vencimento(body.dia_vencimento_fixo) or (parse_date_safe(vencimento).day if parse_date_safe(vencimento) else parse_date_safe(inicio).day)
        aluno = AlunoDB(
            nome=pre.nome, telefone=pre.telefone, cpf=pre.cpf, plano_nome=plano["nome"],
            valor_plano=float(plano["valor"]), valor_padrao_plano=float(plano["valor"]),
            desconto_valor=max(float(body.desconto_valor or 0), 0.0),
            valor_final_manual=float(body.valor_final_manual) if body.valor_final_manual is not None else None,
            valor_final_manual_ativo=body.valor_final_manual is not None,
            data_inicio_plano=None if body_sem_cobranca else inicio, vencimento=None if body_sem_cobranca else vencimento, dia_vencimento_fixo=None if body_sem_cobranca else dia_fixo,
            premium_admin=body_premium, acesso_livre=body_acesso_livre, pode_acessar_adm=bool(getattr(body, "pode_acessar_adm", False)),
            status_manual="em_dia",
            data_cadastro=agora_str(), status_cliente_raw="Ativo", status_contrato_raw="Ativo",
            pre_cadastro_origem=True, aprovado_em=datetime.utcnow(), created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        )
        db.add(aluno)
        pre.status = "aprovado"
        pre.aprovado_em = datetime.utcnow()
        db.commit()
        db.refresh(aluno)
        return {"ok": True, "aluno": aluno_dict(db, aluno)}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

@app.post("/pre-cadastros/{pre_id}/recusar")
def recusar_pre_cadastro(pre_id: int, observacao: Optional[str] = Body(default=None, embed=True)):
    db = SessionLocal()
    try:
        pre = db.query(PreCadastroAlunoDB).filter(PreCadastroAlunoDB.id == pre_id).first()
        if not pre:
            raise HTTPException(status_code=404, detail="Pré-cadastro não encontrado")
        pre.status = "recusado"
        pre.observacao = observacao
        pre.recusado_em = datetime.utcnow()
        db.commit()
        return {"ok": True}
    finally:
        db.close()


@app.post("/aluno/{aluno_id}/acesso-adm")
def validar_acesso_adm_aluno(aluno_id: int):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        if not aluno_super_admin(aluno):
            raise HTTPException(status_code=403, detail="Este aluno não tem permissão para acessar o ADM")
        return {"ok": True, "aluno": aluno_dict(db, aluno), "adm": True}
    finally:
        db.close()

# ----------------------
# Promoções e valor manual
# ----------------------
@app.get("/promocoes")
def listar_promocoes():
    db = SessionLocal()
    try:
        promocoes = db.query(PromocaoDB).order_by(PromocaoDB.criado_em.desc()).all()
        saida = []
        for p in promocoes:
            aplicacoes = db.query(PromocaoAplicacaoDB).filter(PromocaoAplicacaoDB.promocao_id == p.id).all()
            saida.append({
                "id": p.id, "nome": p.nome, "tipo": p.tipo, "descricao": p.descricao,
                "desconto_valor": p.desconto_valor, "ativa": p.ativa, "observacao": p.observacao,
                "criado_em": p.criado_em.isoformat() if p.criado_em else None,
                "alunos_vinculados": [
                    {"aluno_id": a.aluno_id, "nome": a.aluno.nome if a.aluno else None, "valor_desconto": a.valor_desconto, "criado_em": a.criado_em.isoformat() if a.criado_em else None}
                    for a in aplicacoes
                ]
            })
        return saida
    finally:
        db.close()

@app.post("/promocoes")
def criar_promocao(body: PromocaoCreate):
    db = SessionLocal()
    try:
        promo = PromocaoDB(
            nome=body.nome.strip(), tipo=body.tipo, descricao=(body.descricao or "").strip() or None,
            desconto_valor=max(float(body.desconto_valor or 0), 0.0), ativa=bool(body.ativa), observacao=body.observacao,
        )
        db.add(promo)
        db.flush()
        if body.tipo == "indicacao" and body.aluno_indicou_id:
            aluno = buscar_aluno_por_id(db, body.aluno_indicou_id)
            if not aluno:
                raise HTTPException(status_code=404, detail="Aluno indicador não encontrado")
            desconto_atual = float(getattr(aluno, "desconto_valor", 0) or 0)
            novo_desconto = desconto_atual + promo.desconto_valor
            base = float(aluno.valor_plano or 0) or valor_base_plano_nome(db, aluno.plano_nome)
            aluno.desconto_valor = round(min(novo_desconto, max(base, 0.0)), 2)
            aluno.origem_valor = "promocao_indicacao"
            aluno.updated_at = datetime.utcnow()
            db.add(PromocaoAplicacaoDB(promocao_id=promo.id, aluno_id=aluno.id, valor_desconto=promo.desconto_valor, observacao="Desconto por indicação aplicado automaticamente"))
        db.commit()
        db.refresh(promo)
        return {"ok": True, "promocao_id": promo.id}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

@app.put("/promocoes/{promocao_id}")
def atualizar_promocao(promocao_id: int, body: PromocaoUpdate):
    db = SessionLocal()
    try:
        promo = db.query(PromocaoDB).filter(PromocaoDB.id == promocao_id).first()
        if not promo:
            raise HTTPException(status_code=404, detail="Promoção não encontrada")
        if body.nome is not None:
            nome = body.nome.strip()
            if not nome:
                raise HTTPException(status_code=400, detail="Nome da promoção é obrigatório")
            promo.nome = nome
        if body.tipo is not None:
            promo.tipo = body.tipo
        if body.descricao is not None:
            promo.descricao = body.descricao.strip() or None
        if body.desconto_valor is not None:
            promo.desconto_valor = round(max(float(body.desconto_valor or 0), 0.0), 2)
        if body.ativa is not None:
            promo.ativa = bool(body.ativa)
        if body.observacao is not None:
            promo.observacao = body.observacao.strip() or None
        promo.atualizado_em = datetime.utcnow()
        db.commit()
        return {"ok": True, "promocao_id": promo.id}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

@app.delete("/promocoes/{promocao_id}")
def excluir_promocao(promocao_id: int):
    db = SessionLocal()
    try:
        promo = db.query(PromocaoDB).filter(PromocaoDB.id == promocao_id).first()
        if not promo:
            raise HTTPException(status_code=404, detail="Promoção não encontrada")
        # Não desfaz descontos já aplicados em alunos, para não alterar valores combinados sem conferência.
        db.query(PromocaoAplicacaoDB).filter(PromocaoAplicacaoDB.promocao_id == promocao_id).delete(synchronize_session=False)
        db.delete(promo)
        db.commit()
        return {"ok": True, "mensagem": "Promoção excluída. Descontos já aplicados em alunos foram preservados."}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

@app.put("/promocoes/{promocao_id}/status")
def alterar_status_promocao(promocao_id: int, ativa: bool = Body(..., embed=True)):
    db = SessionLocal()
    try:
        promo = db.query(PromocaoDB).filter(PromocaoDB.id == promocao_id).first()
        if not promo:
            raise HTTPException(status_code=404, detail="Promoção não encontrada")
        promo.ativa = bool(ativa)
        promo.atualizado_em = datetime.utcnow()
        db.commit()
        return {"ok": True}
    finally:
        db.close()

@app.put("/alunos/{aluno_id}/valor-manual")
def atualizar_valor_manual(aluno_id: int, body: ValorManualBody):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        if not body.ativo or body.valor_final_manual is None:
            aluno.valor_final_manual = None
            aluno.valor_final_manual_ativo = False
            aluno.origem_valor = "valor_manual_removido"
        else:
            aluno.valor_final_manual = round(max(float(body.valor_final_manual), 0.0), 2)
            aluno.valor_final_manual_ativo = True
            aluno.origem_valor = "valor_final_manual_admin"
        aluno.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(aluno)
        return aluno_dict(db, aluno)
    finally:
        db.close()


@app.post("/pagamentos/{pagamento_id}/aprovar-demo")
def aprovar_pagamento_demo(pagamento_id: int):
    return {"ok": True, "mensagem": "Modo demo desativado. Use o link real para pagar."}
# deploy render atualizado v5.1.2