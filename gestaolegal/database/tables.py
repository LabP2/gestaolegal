import hashlib

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
)

from sqlalchemy.dialects.mysql import VARCHAR, LONGTEXT, MEDIUMTEXT

metadata = MetaData()

# Unidade padrão (Belo Horizonte), a mesma que a migration atribui aos
# registros herdados. Serve a quem precisa nomear a unidade inicial — o vínculo
# do primeiro usuário e a migration —, NÃO como default de coluna: `coluna_unidade`
# teve o `default=UNIDADE_PADRAO_ID` removido na Fase A, depois que os services
# passaram a gravar a unidade ativa. Sem ele, INSERT sem unidade estoura o NOT NULL
# na hora, em vez de gravar calado em Belo Horizonte um registro de Nova Lima.
UNIDADE_PADRAO_ID = 1


def coluna_unidade() -> Column:
    return Column(
        "unidade_id",
        Integer,
        nullable=False,
        index=True,
    )


# Tenant = um NPJ (Núcleo de Prática Jurídica). A DAJ/UFMG é o tenant 1, que a
# migration de tenants cria e ao qual os registros existentes vão pertencer.
# Como UNIDADE_PADRAO_ID, nomeia o tenant inicial; NÃO é default de coluna.
TENANT_PADRAO_ID = 1

# Únicas tabelas sem `tenant_id`. Todas as outras pertencem a um tenant
# (plano: docs/plano-multitenant.md, §3). Testes estruturais e a guarda de
# execução leem esta lista; não há outro lugar que defina exceções.
TABELAS_GLOBAIS = frozenset({"tenants", "plataforma_admins"})


def coluna_tenant() -> Column:
    # Sem default, de propósito: quem preenche é o repositório (ou a guarda),
    # sempre a partir do tenant do contexto. Esquecer deve quebrar na hora.
    return Column(
        "tenant_id",
        Integer,
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
    )


# FKs compostas (multitenant, M3). Entre duas tabelas de tenant, a FK inclui o
# tenant: `(tenant_id, x_id) -> pai(tenant_id, id)`. Assim o banco recusa ligar
# um caso do NPJ A a um usuário, atendido ou unidade do NPJ B, mesmo que o
# código erre. O alvo precisa de `UNIQUE (tenant_id, id)`: `unica_tenant_id`.
# Colunas de id sem FK declarada (criadopor, notificacao.id_caso...) ficam de
# fora; quem cuida delas é o service.
LIMITE_NOME_MYSQL = 64


def nome_unica_tenant_id(tabela: str) -> str:
    return f"uq_{tabela}_tenant_id_id"


def nome_fk_tenant(tabela: str, coluna: str) -> str:
    nome = f"fkt_{tabela}_{coluna}"
    if len(nome) <= LIMITE_NOME_MYSQL:
        return nome
    # Nomes longos (tabelas de ligação legadas) são encurtados de forma
    # determinística; a migration M3 guarda o resultado literal.
    resumo = hashlib.sha1(nome.encode()).hexdigest()[:8]
    return f"{nome[: LIMITE_NOME_MYSQL - 9]}_{resumo}"


def unica_tenant_id(tabela: str) -> UniqueConstraint:
    return UniqueConstraint("tenant_id", "id", name=nome_unica_tenant_id(tabela))


def fk_tenant(
    tabela: str, coluna: str, alvo: str, ondelete: str | None = None
) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["tenant_id", coluna],
        [f"{alvo}.tenant_id", f"{alvo}.id"],
        name=nome_fk_tenant(tabela, coluna),
        ondelete=ondelete,
    )


# Administradores da plataforma: identidade separada de `usuarios`, com login
# próprio. Não pertencem a nenhum tenant e não leem dados dos tenants.
plataforma_admins = Table(
    "plataforma_admins",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("nome", String(60), nullable=False),
    Column("email", String(80), nullable=False, unique=True),
    Column("senha", String(60), nullable=False),  # hash bcrypt
    Column("ativo", Boolean, nullable=False, default=True),
    Column("criado_em", DateTime, nullable=False),
    Column("ultimo_login_em", DateTime, nullable=True),
)

tenants = Table(
    "tenants",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("nome", String(150), nullable=False),
    Column("sigla", String(20), nullable=False, unique=True),
    # Identificador para CLI e scripts (`--tenant daj-ufmg`). Não aparece em
    # URL e não muda depois de criado.
    Column("slug", String(40), nullable=False, unique=True),
    Column("instituicao", String(150), nullable=True),
    # False = login recusado e rotinas agendadas pulam o tenant.
    Column("ativo", Boolean, nullable=False, default=True),
    Column("criado_em", DateTime, nullable=False),
    Column("id_criado_por", Integer, ForeignKey("plataforma_admins.id"), nullable=True),
    # Captura de publicações do DJEN para o NPJ (docs/plano-djen.md, §3.2).
    # Começa desligada; só o admin da plataforma liga.
    # Só server_default: um INSERT que não cite a coluna (seed numa revisão
    # anterior, scripts) continua válido.
    Column("djen_ativo", Boolean, nullable=False, server_default="0"),
)

enderecos = Table(
    "enderecos",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("logradouro", String(100), nullable=False),
    Column("numero", String(8), nullable=False),
    Column("complemento", String(100), nullable=True),
    Column("bairro", String(100), nullable=False),
    Column("cep", String(9), nullable=False),
    Column("cidade", String(100), nullable=False),
    Column("estado", String(100), nullable=False),
    coluna_tenant(),
    unica_tenant_id("enderecos"),
)

usuarios = Table(
    "usuarios",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("email", String(80), nullable=False, unique=True),
    Column("senha", String(60), nullable=False),
    Column("urole", String(50), nullable=False),
    Column("nome", String(60), nullable=False),
    Column("sexo", String(60), nullable=False),
    Column("rg", String(18), nullable=False),
    Column("cpf", String(14), nullable=False),
    Column("profissao", String(45), nullable=False),
    Column("estado_civil", String(45), nullable=False),
    Column("nascimento", Date, nullable=False),
    Column("telefone", String(18), nullable=True),
    Column("celular", String(18), nullable=False),
    Column("oab", String(30), nullable=True),
    Column("obs", Text, nullable=True),
    Column("data_entrada", Date, nullable=False),
    Column("data_saida", Date, nullable=True),
    Column("criado", DateTime, nullable=False),
    Column("modificado", DateTime, nullable=True),
    Column("criadopor", Integer, nullable=False),
    Column("matricula", String(45), nullable=True),
    Column("modificadopor", Integer, nullable=True),
    Column("bolsista", Boolean, nullable=False),
    Column("tipo_bolsa", String(50), nullable=True),
    Column("horario_atendimento", String(30), nullable=True),
    Column("suplente", String(30), nullable=True),
    Column("ferias", String(150), nullable=True),
    Column("status", Boolean, nullable=False),
    Column("cert_atuacao_DAJ", String(3), nullable=False),
    Column("inicio_bolsa", DateTime, nullable=True),
    Column("fim_bolsa", DateTime, nullable=True),
    Column("endereco_id", Integer, nullable=True),
    Column("chave_recuperacao", Boolean, nullable=True, default=False),
    coluna_tenant(),
    unica_tenant_id("usuarios"),
    fk_tenant("usuarios", "endereco_id", "enderecos"),
)

atendidos = Table(
    "atendidos",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("nome", String(80), nullable=False),
    # Os dados pessoais abaixo aceitam nulo só no banco, por causa do cadastro
    # simplificado da parte (docs/plano-processos-avulsos.md, §1). O cadastro
    # normal continua exigindo tudo pela validação de entrada.
    Column("data_nascimento", Date, nullable=True),
    Column("cpf", String(14), nullable=True),
    Column("cnpj", String(18), nullable=True),
    Column("endereco_id", Integer, nullable=True),
    Column("telefone", String(18), nullable=True),
    Column("celular", String(18), nullable=True),
    Column("email", String(80), nullable=True),
    Column("estado_civil", String(80), nullable=True),
    Column("como_conheceu", String(80), nullable=True),
    Column("indicacao_orgao", String(80), nullable=True),
    Column("procurou_outro_local", String(80), nullable=True),
    Column("procurou_qual_local", String(80), nullable=True),
    Column("obs", Text, nullable=True),
    Column("pj_constituida", String(80), nullable=True),
    Column("repres_legal", Boolean, nullable=True),
    Column("nome_repres_legal", String(80), nullable=True),
    Column("cpf_repres_legal", String(14), nullable=True),
    Column("contato_repres_legal", String(18), nullable=True),
    Column("rg_repres_legal", String(50), nullable=True),
    Column("nascimento_repres_legal", Date, nullable=True),
    Column("pretende_constituir_pj", String(80), nullable=True),
    Column("status", Integer, nullable=False),
    # Parte cadastrada sem triagem socioeconômica (processo sem caso): conta
    # como assistido sem ter linha em `assistidos`.
    Column("sem_triagem", Boolean, nullable=False, server_default="0"),
    coluna_unidade(),
    coluna_tenant(),
    unica_tenant_id("atendidos"),
    fk_tenant("atendidos", "endereco_id", "enderecos"),
    fk_tenant("atendidos", "unidade_id", "unidades"),
)

assistidos = Table(
    "assistidos",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("id_atendido", Integer, nullable=True),
    Column("sexo", String(1), nullable=False),
    Column("profissao", String(80), nullable=False),
    Column("raca", String(20), nullable=False),
    Column("rg", String(50), nullable=False),
    Column("grau_instrucao", String(100), nullable=False),
    Column("salario", Numeric(10, 2), nullable=False),
    Column("beneficio", String(30), nullable=False),
    Column("qual_beneficio", String(30), nullable=True),
    Column("contribui_inss", String(20), nullable=False),
    Column("qtd_pessoas_moradia", Integer, nullable=False),
    Column("renda_familiar", Numeric(10, 2), nullable=False),
    Column("participacao_renda", String(100), nullable=False),
    Column("tipo_moradia", String(100), nullable=False),
    Column("possui_outros_imoveis", Boolean, nullable=False),
    Column("quantos_imoveis", Integer, nullable=True),
    Column("possui_veiculos", Boolean, nullable=False),
    Column("possui_veiculos_obs", String(100), nullable=True),
    Column("quantos_veiculos", Integer, nullable=True),
    Column("ano_veiculo", String(5), nullable=True),
    Column("doenca_grave_familia", String(20), nullable=False),
    Column("pessoa_doente", String(50), nullable=True),
    Column("pessoa_doente_obs", String(100), nullable=True),
    Column("gastos_medicacao", Numeric(10, 2), nullable=True),
    Column("obs", String(1000), nullable=True),
    coluna_tenant(),
    unica_tenant_id("assistidos"),
    fk_tenant("assistidos", "id_atendido", "atendidos"),
)

# O vínculo com assistidos delimita a unidade; não há unidade independente da PJ.
assistidos_pessoa_juridica = Table(
    "assistidos_pessoa_juridica",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("id_assistido", Integer, nullable=True),
    Column("enquadramento", String(100), nullable=False),
    Column("especificacao_enquadramento", String(200), nullable=True),
    Column("socios", String(1000), nullable=True),
    Column("situacao_receita", String(100), nullable=True),
    Column("sede_bh", Boolean, nullable=True),
    Column("regiao_sede_bh", String(50), nullable=True),
    Column("regiao_sede_outros", String(100), nullable=True),
    Column("area_atuacao", String(50), nullable=True),
    Column("negocio_nascente", Boolean, nullable=True),
    Column("orgao_registro", String(100), nullable=True),
    Column("faturamento_anual", Numeric(10, 2), nullable=True),
    Column("ultimo_balanco_neg", String(50), nullable=True),
    Column("resultado_econ_neg", String(50), nullable=True),
    Column("tem_funcionarios", String(20), nullable=True),
    Column("qtd_funcionarios", String(7), nullable=True),
    coluna_tenant(),
    fk_tenant("assistidos_pessoa_juridica", "id_assistido", "assistidos"),
)

orientacao_juridica = Table(
    "orientacao_juridica",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("area_direito", String(50), nullable=False),
    Column("sub_area", String(50), nullable=True),
    Column("descricao", Text, nullable=False),
    Column("data_criacao", DateTime, nullable=True),
    Column("status", Integer, nullable=False),
    Column("id_usuario", Integer, nullable=True),
    coluna_unidade(),
    coluna_tenant(),
    unica_tenant_id("orientacao_juridica"),
    fk_tenant("orientacao_juridica", "id_usuario", "usuarios"),
    fk_tenant("orientacao_juridica", "unidade_id", "unidades"),
)

atendido_xOrientacaoJuridica = Table(
    "atendido_xOrientacaoJuridica",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "id_orientacaoJuridica",
        Integer,
        nullable=True,
    ),
    Column("id_atendido", Integer, nullable=True),
    coluna_tenant(),
    fk_tenant(
        "atendido_xOrientacaoJuridica", "id_orientacaoJuridica", "orientacao_juridica"
    ),
    fk_tenant("atendido_xOrientacaoJuridica", "id_atendido", "atendidos"),
)

casos = Table(
    "casos",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("id_usuario_responsavel", Integer, nullable=False),
    Column("area_direito", String(50), nullable=False),
    Column("sub_area", String(50), nullable=True),
    Column("id_orientador", Integer, nullable=True),
    Column("id_estagiario", Integer, nullable=True),
    Column("id_colaborador", Integer, nullable=True),
    Column("data_criacao", DateTime, nullable=False),
    Column("id_criado_por", Integer, nullable=False),
    Column("data_modificacao", DateTime, nullable=True),
    Column("id_modificado_por", Integer, nullable=True),
    Column("situacao_deferimento", String(50), nullable=False),
    Column("justif_indeferimento", String(280), nullable=True),
    Column("status", Boolean, nullable=False),
    Column("descricao", Text, nullable=True),
    Column("numero_ultimo_processo", Integer, nullable=True),
    coluna_unidade(),
    coluna_tenant(),
    unica_tenant_id("casos"),
    fk_tenant("casos", "id_usuario_responsavel", "usuarios"),
    fk_tenant("casos", "id_orientador", "usuarios"),
    fk_tenant("casos", "id_estagiario", "usuarios"),
    fk_tenant("casos", "id_colaborador", "usuarios"),
    fk_tenant("casos", "id_criado_por", "usuarios"),
    fk_tenant("casos", "id_modificado_por", "usuarios"),
    fk_tenant("casos", "unidade_id", "unidades"),
)

casos_atendidos = Table(
    "casos_atendidos",
    metadata,
    Column("id_caso", Integer, nullable=True),
    Column("id_atendido", Integer, nullable=True),
    coluna_tenant(),
    fk_tenant("casos_atendidos", "id_caso", "casos"),
    fk_tenant("casos_atendidos", "id_atendido", "atendidos"),
)

processos = Table(
    "processos",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("especie", String(25), nullable=False),
    Column("numero", String(25), nullable=True),
    Column("identificacao", Text, nullable=True),
    Column("vara", String(200), nullable=True),
    Column("link", String(1000), nullable=True),
    Column("probabilidade", String(25), nullable=True),
    Column("posicao_assistido", String(25), nullable=True),
    Column("valor_causa_inicial", Numeric(15, 2, asdecimal=False), nullable=True),
    Column("valor_causa_atual", Numeric(15, 2, asdecimal=False), nullable=True),
    Column("data_distribuicao", Date, nullable=True),
    Column("data_transito_em_julgado", Date, nullable=True),
    Column("obs", Text, nullable=True),
    # Nulo no processo sem caso (docs/plano-processos-avulsos.md), cujas
    # partes ficam em `processo_partes`.
    Column("id_caso", Integer, nullable=True),
    Column("status", Boolean, nullable=False),
    Column("id_criado_por", Integer, nullable=False),
    # DJEN: só os 20 dígitos de `numero`, quando tiver exatamente 20 (padrão
    # CNJ). É por ele que as publicações são casadas com o processo.
    Column("numero_cnj", String(20), nullable=True),
    # Processo cadastrado ou com número alterado: a rotina busca o histórico.
    Column("djen_pendente", Boolean, nullable=False, server_default="0"),
    Column("djen_consultado_em", DateTime, nullable=True),
    # Processo de caso grava a unidade do caso; sem caso, a unidade ativa.
    coluna_unidade(),
    coluna_tenant(),
    unica_tenant_id("processos"),
    Index("ix_processos_tenant_numero_cnj", "tenant_id", "numero_cnj"),
    fk_tenant("processos", "id_caso", "casos"),
    fk_tenant("processos", "id_criado_por", "usuarios"),
    fk_tenant("processos", "unidade_id", "unidades"),
    # Mesmo número pode existir em NPJs diferentes. O nome é lido por
    # _tratar_numero_duplicado (processo_repository.py) para responder 400.
    UniqueConstraint("tenant_id", "numero", name="uq_processos_tenant_numero"),
)

eventos = Table(
    "eventos",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("id_caso", Integer, nullable=False),
    Column("num_evento", Integer, nullable=True),
    Column("tipo", String(50), nullable=False),
    Column("descricao", Text, nullable=True),
    Column("arquivo", String(300), nullable=True),
    Column("data_evento", Date, nullable=False),
    Column("data_criacao", DateTime, nullable=False),
    # Nulo só em evento criado pela rotina do DJEN (origem='djen'), que roda
    # sem usuário. Um usuário "sistema" foi descartado (docs/plano-djen.md §3).
    Column("id_criado_por", Integer, nullable=True),
    Column("id_usuario_responsavel", Integer, nullable=True),
    Column("status", Boolean, nullable=False),
    # manual | djen. O evento do DJEN tem tipo, data e descrição travados.
    Column("origem", String(10), nullable=False, server_default="manual"),
    # Publicação de origem; no máximo um evento por publicação.
    Column("id_djen_comunicacao", Integer, nullable=True),
    coluna_unidade(),
    coluna_tenant(),
    unica_tenant_id("eventos"),
    UniqueConstraint(
        "tenant_id", "id_djen_comunicacao", name="uq_eventos_tenant_djen_comunicacao"
    ),
    fk_tenant("eventos", "id_caso", "casos"),
    fk_tenant("eventos", "id_criado_por", "usuarios"),
    fk_tenant("eventos", "id_usuario_responsavel", "usuarios"),
    fk_tenant("eventos", "unidade_id", "unidades"),
    fk_tenant("eventos", "id_djen_comunicacao", "djen_comunicacoes"),
)

# Relação 1:N, preservando a tabela e os IDs das instalações legadas.
arquivos_evento = Table(
    "arquivosEvento",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("id_evento", Integer, nullable=True),
    Column("id_caso", Integer, nullable=True),
    Column(
        "link_arquivo",
        String(300).with_variant(
            VARCHAR(300, charset="utf8mb4", collation="utf8mb4_0900_ai_ci"), "mysql"
        ),
        nullable=True,
    ),
    Column("indisponivel_origem", Boolean, nullable=False, server_default="0"),
    coluna_tenant(),
    fk_tenant("arquivosEvento", "id_evento", "eventos", ondelete="CASCADE"),
    fk_tenant("arquivosEvento", "id_caso", "casos", ondelete="CASCADE"),
)


arquivos_caso = Table(
    "arquivosCaso",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("link_arquivo", String(300), nullable=True),
    Column("id_caso", Integer, nullable=True),
    Column("indisponivel_origem", Boolean, nullable=False, server_default="0"),
    coluna_tenant(),
    # CASCADE vem da baseline (ed1b0a0a61a6) e existe em produção.
    fk_tenant("arquivosCaso", "id_caso", "casos", ondelete="CASCADE"),
)

arquivos = Table(
    "arquivos",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("titulo", String(150), nullable=False),
    Column("descricao", Text, nullable=True),
    Column("nome", Text, nullable=False),
    # Colunas abaixo são nulas em registros herdados da v2.
    Column("caminho", String(300), nullable=True),
    Column("data_criacao", DateTime, nullable=True),
    Column("id_criado_por", Integer, nullable=True),
    coluna_tenant(),
    fk_tenant("arquivos", "id_criado_por", "usuarios"),
)

notificacao = Table(
    "notificacao",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("id_executor_acao", Integer, nullable=True),
    # Nulo = aviso geral (abertura do plantão), visto por orientadores e estagiários.
    Column("id_usu_notificar", Integer, nullable=True),
    Column("acao", String(200), nullable=False),
    Column("data", Date, nullable=False),
    # Colunas abaixo não existiam na v2 (nulas em registros herdados).
    Column(
        "tipo", String(30), nullable=True
    ),  # caso | evento | lembrete | plantao | djen
    Column("id_caso", Integer, nullable=True),
    Column("id_referencia", Integer, nullable=True),  # id do evento ou lembrete
    # Resumo do conteúdo do aviso (cliente do caso, descrição do lembrete etc.).
    Column("detalhe", String(300), nullable=True),
    Column("lida", Boolean, nullable=False, default=False),
    Column("data_criacao", DateTime, nullable=True),
    # Preenchida = notificação arquivada (some da lista padrão).
    Column("data_arquivamento", DateTime, nullable=True),
    coluna_tenant(),
    fk_tenant("notificacao", "id_executor_acao", "usuarios"),
    fk_tenant("notificacao", "id_usu_notificar", "usuarios"),
)

assistencias_judiciarias = Table(
    "assistencias_judiciarias",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("nome", String(150), nullable=False),
    Column("regiao", String(80), nullable=False),
    Column("areas_atendidas", String(1000), nullable=False),
    Column("endereco_id", Integer, nullable=True),
    Column("telefone", String(18), nullable=False),
    Column("email", String(80), nullable=False),
    Column("status", Integer, nullable=False),
    coluna_unidade(),
    coluna_tenant(),
    unica_tenant_id("assistencias_judiciarias"),
    fk_tenant("assistencias_judiciarias", "endereco_id", "enderecos"),
    fk_tenant("assistencias_judiciarias", "unidade_id", "unidades"),
    UniqueConstraint("tenant_id", "email", name="uq_assistencias_tenant_email"),
)

assistenciasJudiciarias_xOrientacao_juridica = Table(
    "assistenciasJudiciarias_xOrientacao_juridica",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "id_orientacaoJuridica",
        Integer,
        nullable=True,
    ),
    Column(
        "id_assistenciaJudiciaria",
        Integer,
        nullable=True,
    ),
    coluna_tenant(),
    fk_tenant(
        "assistenciasJudiciarias_xOrientacao_juridica",
        "id_orientacaoJuridica",
        "orientacao_juridica",
    ),
    fk_tenant(
        "assistenciasJudiciarias_xOrientacao_juridica",
        "id_assistenciaJudiciaria",
        "assistencias_judiciarias",
    ),
)

lembretes = Table(
    "lembretes",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("num_lembrete", Integer, nullable=True),
    Column("id_do_criador", Integer, nullable=False),
    Column("id_caso", Integer, nullable=False),
    Column("id_usuario", Integer, nullable=False),
    Column("data_criacao", DateTime, nullable=False),
    Column("data_lembrete", DateTime, nullable=False),
    Column("descricao", Text, nullable=False),
    Column("status", Boolean, nullable=False),
    coluna_unidade(),
    coluna_tenant(),
    fk_tenant("lembretes", "id_do_criador", "usuarios"),
    fk_tenant("lembretes", "id_caso", "casos"),
    fk_tenant("lembretes", "id_usuario", "usuarios"),
    fk_tenant("lembretes", "unidade_id", "unidades"),
)

historicos = Table(
    "historicos",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("id_usuario", Integer, nullable=False),
    Column("id_caso", Integer, nullable=False),
    Column("data", DateTime, nullable=False),
    Column("acao", String(50), nullable=True),
    Column("descricao", String(500), nullable=True),
    coluna_tenant(),
    fk_tenant("historicos", "id_usuario", "usuarios"),
    fk_tenant("historicos", "id_caso", "casos"),
)

documentos_roteiro = Table(
    "documentos_roteiro",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("area_direito", String(50), nullable=False),
    Column("link", String(1000), nullable=True),
    coluna_tenant(),
)

fila_atendimentos = Table(
    "fila_atendimentos",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("psicologia", Integer, nullable=False),
    Column("prioridade", Integer, nullable=False),
    Column("data_criacao", DateTime, nullable=False),
    Column(
        "senha",
        String(10).with_variant(
            VARCHAR(10, charset="utf8mb4", collation="utf8mb4_0900_ai_ci"), "mysql"
        ),
        nullable=False,
    ),
    Column("status", Integer, nullable=False),
    Column("id_atendido", Integer, nullable=False),
    Column("data_saida", DateTime, nullable=True),
    coluna_unidade(),
    coluna_tenant(),
    fk_tenant("fila_atendimentos", "id_atendido", "atendidos"),
    fk_tenant("fila_atendimentos", "unidade_id", "unidades"),
)

# Tabelas do plantão. Criadas pela migration baseline ed1b0a0a61a6 e declaradas
# aqui para ficarem visíveis à aplicação, ao metadata.create_all dos testes e ao
# autogenerate do Alembic. O schema espelha o baseline coluna a coluna.
dias_plantao = Table(
    "dias_plantao",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("data", Date, nullable=True),
    Column("plantao_id", Integer, nullable=False, index=True),
    # False = dia removido da configuração (soft delete)
    Column("status", Boolean, nullable=False, default=True),
    coluna_unidade(),
    coluna_tenant(),
    fk_tenant("dias_plantao", "plantao_id", "plantao"),
    fk_tenant("dias_plantao", "unidade_id", "unidades"),
)

plantao = Table(
    "plantao",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("data_abertura", DateTime, nullable=True),
    Column("data_fechamento", DateTime, nullable=True),
    Column("nome", String(150), nullable=False, default="Escala de plantão"),
    Column("legado", Boolean, nullable=False, default=False),
    Column("cancelado", Boolean, nullable=False, default=False),
    Column("historico", Text().with_variant(LONGTEXT(), "mysql"), nullable=True),
    coluna_unidade(),
    coluna_tenant(),
    unica_tenant_id("plantao"),
    fk_tenant("plantao", "unidade_id", "unidades"),
)

dias_marcados_plantao = Table(
    "dias_marcados_plantao",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("data_marcada", Date, nullable=True),
    Column("plantao_id", Integer, nullable=False, index=True),
    # aberto | confirmar | divergencia | ausencia
    Column("confirmacao", String(15), nullable=False, default="aberto"),
    # True = marcação ativa; False = apagada pelo usuário (soft delete)
    Column("status", Boolean, nullable=False, default=True),
    Column("id_usuario", Integer, nullable=True),
    coluna_unidade(),
    coluna_tenant(),
    fk_tenant("dias_marcados_plantao", "plantao_id", "plantao"),
    fk_tenant("dias_marcados_plantao", "id_usuario", "usuarios"),
    fk_tenant("dias_marcados_plantao", "unidade_id", "unidades"),
)

registro_entrada = Table(
    "registro_entrada",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("data_entrada", DateTime, nullable=False),
    # NOT NULL no schema legado: enquanto o registro está em curso grava-se o
    # provisório 23:59:59 do dia da entrada, sobrescrito na saída.
    Column("data_saida", DateTime, nullable=False),
    # True = em curso (entrada sem saída); False = fechado
    Column("status", Boolean, nullable=False, default=True),
    # aberto | confirmar | divergencia | ausencia
    Column("confirmacao", String(15), nullable=False, default="aberto"),
    Column("id_usuario", Integer, nullable=True),
    coluna_unidade(),
    coluna_tenant(),
    fk_tenant("registro_entrada", "id_usuario", "usuarios"),
    fk_tenant("registro_entrada", "unidade_id", "unidades"),
)

unidades = Table(
    "unidades",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("nome", String(60), nullable=False),
    Column("sigla", String(10), nullable=False),
    # False = unidade desativada (some do seletor, mantém o histórico)
    Column("ativa", Boolean, nullable=False, default=True),
    Column("criado", DateTime, nullable=False),
    coluna_tenant(),
    unica_tenant_id("unidades"),
    UniqueConstraint("tenant_id", "nome", name="uq_unidades_tenant_nome"),
    UniqueConstraint("tenant_id", "sigla", name="uq_unidades_tenant_sigla"),
)

usuarios_unidades = Table(
    "usuarios_unidades",
    metadata,
    Column("usuario_id", Integer, primary_key=True),
    Column("unidade_id", Integer, primary_key=True),
    coluna_tenant(),
    fk_tenant("usuarios_unidades", "usuario_id", "usuarios"),
    fk_tenant("usuarios_unidades", "unidade_id", "unidades"),
)

password_reset_tokens = Table(
    "password_reset_tokens",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("usuario_id", Integer, nullable=False),
    # Só o hash do token é guardado: o valor em claro existe apenas no e-mail.
    Column("token_hash", String(64), nullable=False, unique=True),
    Column("expira_em", DateTime, nullable=False),
    # Preenchida = token já consumido (uso único).
    Column("usado_em", DateTime, nullable=True),
    Column("criado_em", DateTime, nullable=False),
    coluna_tenant(),
    fk_tenant("password_reset_tokens", "usuario_id", "usuarios"),
)


# --- DJEN (docs/plano-djen.md, §3) -------------------------------------------

TEXTO_LONGO = Text().with_variant(MEDIUMTEXT(), "mysql")

# Publicações capturadas do Diário de Justiça Eletrônico Nacional. Uma OAB
# cadastrada em dois NPJs recebe a mesma publicação nos dois, como registros
# separados: a unicidade do `id_djen` é por tenant.
# Acervo canônico: conteúdo único por NPJ, independente das decisões.
djen_publicacoes = Table(
    "djen_publicacoes",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("id_djen", BigInteger, nullable=False),  # `id` da API
    Column("hash", String(100), nullable=True),  # link da certidão
    Column("numero_processo", String(20), nullable=False),
    Column("numero_processo_mascara", String(30), nullable=True),
    Column("data_disponibilizacao", Date, nullable=False),
    Column("sigla_tribunal", String(30), nullable=True),
    Column("nome_orgao", String(300), nullable=True),
    Column("tipo_comunicacao", String(100), nullable=True),
    Column("tipo_documento", String(100), nullable=True),
    Column("nome_classe", String(300), nullable=True),
    # Original da API: conteúdo de terceiros, nunca vai cru para o front.
    Column("texto_html", TEXTO_LONGO, nullable=True),
    Column("texto_plano", TEXTO_LONGO, nullable=True),
    Column("link", String(1000), nullable=True),
    Column("destinatarios", JSON, nullable=True),
    Column("advogados", JSON, nullable=True),
    # False = publicação cancelada no DJEN.
    Column("ativo", Boolean, nullable=False, default=True, server_default="1"),
    Column("motivo_cancelamento", Text, nullable=True),
    Column("capturada_em", DateTime, nullable=False),
    Column("atualizada_em", DateTime, nullable=True),
    coluna_tenant(),
    unica_tenant_id("djen_publicacoes"),
    UniqueConstraint("tenant_id", "id_djen", name="uq_djen_publicacoes_tenant_djen"),
    Index(
        "ix_djen_publicacoes_tenant_data", "tenant_id", "data_disponibilizacao", "id"
    ),
    Index("ix_djen_publicacoes_tenant_numero", "tenant_id", "numero_processo", "id"),
    mysql_charset="utf8mb4",
    mysql_collate="utf8mb4_0900_ai_ci",
)

djen_comunicacoes = Table(
    "djen_comunicacoes",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("id_publicacao", Integer, nullable=False),
    Column("id_processo", Integer, nullable=True),
    Column("id_caso", Integer, nullable=True),
    Column("situacao", String(12), nullable=False),
    Column("data_situacao", DateTime, nullable=True),
    Column("oab_origem", String(12), nullable=True),
    Column("id_vinculado_por", Integer, nullable=True),
    coluna_unidade(),
    coluna_tenant(),
    unica_tenant_id("djen_comunicacoes"),
    UniqueConstraint(
        "tenant_id", "id_publicacao", name="uq_djen_comunicacoes_publicacao"
    ),
    Index("ix_djen_comunicacoes_tenant_situacao", "tenant_id", "situacao"),
    fk_tenant("djen_comunicacoes", "id_publicacao", "djen_publicacoes"),
    fk_tenant("djen_comunicacoes", "id_processo", "processos"),
    fk_tenant("djen_comunicacoes", "id_caso", "casos"),
    fk_tenant("djen_comunicacoes", "id_vinculado_por", "usuarios"),
    fk_tenant("djen_comunicacoes", "unidade_id", "unidades"),
)

ROTULOS_CLASSIFICACAO = ("relevante", "irrelevante", "nao_classificado")
djen_classificacoes = Table(
    "djen_classificacoes",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("id_publicacao", Integer, nullable=False),
    Column("rotulo", String(20), nullable=False),
    Column("origem", String(30), nullable=False),
    Column("id_rotulado_por", Integer, nullable=True),
    Column("rotulado_em", DateTime, nullable=True),
    coluna_tenant(),
    UniqueConstraint(
        "tenant_id", "id_publicacao", name="uq_djen_classificacoes_publicacao"
    ),
    CheckConstraint(
        "rotulo IN ('relevante', 'irrelevante', 'nao_classificado')",
        name="ck_djen_classificacao_rotulo",
    ),
    Index(
        "ix_djen_classificacoes_tenant_rotulo", "tenant_id", "rotulo", "id_publicacao"
    ),
    fk_tenant("djen_classificacoes", "id_publicacao", "djen_publicacoes"),
    fk_tenant("djen_classificacoes", "id_rotulado_por", "usuarios"),
)

djen_classificacao_historico = Table(
    "djen_classificacao_historico",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("id_publicacao", Integer, nullable=False),
    Column("rotulo_anterior", String(20), nullable=False),
    Column("rotulo", String(20), nullable=False),
    Column("origem", String(30), nullable=False),
    Column("id_rotulado_por", Integer, nullable=True),
    Column("rotulado_em", DateTime, nullable=False),
    coluna_tenant(),
    Index("ix_djen_historico_publicacao", "tenant_id", "id_publicacao", "id"),
    fk_tenant("djen_classificacao_historico", "id_publicacao", "djen_publicacoes"),
    fk_tenant("djen_classificacao_historico", "id_rotulado_por", "usuarios"),
)

# Origem e acesso permanentes: independem da retenção dos logs.
djen_publicacao_unidades = Table(
    "djen_publicacao_unidades", metadata,
    Column("id", Integer, primary_key=True),
    Column("id_publicacao", Integer, nullable=False),
    Column("origem", String(20), nullable=False),
    coluna_unidade(), coluna_tenant(),
    UniqueConstraint("tenant_id", "id_publicacao", "unidade_id", "origem", name="uq_djen_pub_unidade_origem"),
    fk_tenant("djen_publicacao_unidades", "id_publicacao", "djen_publicacoes"),
    fk_tenant("djen_publicacao_unidades", "unidade_id", "unidades"),
)

djen_monitoramentos = Table(
    "djen_monitoramentos", metadata,
    Column("id", Integer, primary_key=True),
    Column("tipo", String(15), nullable=False),
    Column("valor", String(150), nullable=False),
    Column("tribunais", JSON, nullable=False),
    Column("ativo", Boolean, nullable=False, server_default="1"),
    Column("removido", Boolean, nullable=False, server_default="0"),
    Column("automatico", Boolean, nullable=False, server_default="0"),
    Column("criado_em", DateTime, nullable=False),
    Column("ultimo_sucesso", Date, nullable=True),
    coluna_unidade(), coluna_tenant(),
    UniqueConstraint("tenant_id", "unidade_id", "tipo", "valor", name="uq_djen_monitor_unidade_item"),
    fk_tenant("djen_monitoramentos", "unidade_id", "unidades"),
    CheckConstraint("tipo IN ('oab', 'parte', 'processo')", name="ck_djen_monitor_tipo"),
)

djen_consultas = Table(
    "djen_consultas",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("origem", String(20), nullable=False),
    Column("parametros", JSON, nullable=False),
    Column("inicio", DateTime, nullable=False),
    Column("fim", DateTime, nullable=True),
    Column("status", String(15), nullable=False),
    Column("id_executor", Integer, nullable=True),
    Column("modo", String(15), nullable=False, server_default="manual"),
    Column("execucao_id", Integer, nullable=True),
    Column("encontradas", Integer, nullable=False, server_default="0"),
    Column("novas", Integer, nullable=False, server_default="0"),
    Column("mensagem", Text, nullable=True),
    coluna_unidade(),
    coluna_tenant(),
    Index("ix_djen_consultas_tenant_inicio", "tenant_id", "inicio"),
    unica_tenant_id("djen_consultas"),
    fk_tenant("djen_consultas", "unidade_id", "unidades"),
    fk_tenant("djen_consultas", "id_executor", "usuarios"),
)

djen_consulta_resultados = Table(
    "djen_consulta_resultados",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("id_consulta", Integer, nullable=False),
    Column("id_publicacao", Integer, nullable=False),
    coluna_tenant(),
    UniqueConstraint(
        "tenant_id", "id_consulta", "id_publicacao", name="uq_djen_consulta_resultado"
    ),
    Index("ix_djen_resultado_publicacao", "tenant_id", "id_publicacao"),
    fk_tenant("djen_consulta_resultados", "id_consulta", "djen_consultas"),
    fk_tenant("djen_consulta_resultados", "id_publicacao", "djen_publicacoes"),
)

# Uma linha por execução da rotina, por NPJ. A tela mostra a última.
djen_sincronizacoes = Table(
    "djen_sincronizacoes",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("inicio", DateTime, nullable=False),
    Column("fim", DateTime, nullable=True),
    Column("status", String(10), nullable=False),  # ok | parcial | erro
    Column("parametros", JSON, nullable=True),
    Column("novas", Integer, nullable=False, default=0),
    Column("atualizadas", Integer, nullable=False, default=0),
    Column("vinculadas", Integer, nullable=False, default=0),
    Column("mensagem", Text, nullable=True),
    coluna_tenant(),
)

# OABs monitoradas pela rotina (plano, §3), mantidas pelo admin do NPJ. A
# unidade é a das publicações que chegarem por ela sem casar com um processo.
djen_oabs = Table(
    "djen_oabs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("numero_oab", String(10), nullable=False),  # só dígitos
    Column("uf_oab", String(2), nullable=False),
    Column("id_usuario", Integer, nullable=True),  # dono da OAB, se usuário
    Column("ativo", Boolean, nullable=False, server_default="1"),
    Column("criado_em", DateTime, nullable=False),
    Column("id_criado_por", Integer, nullable=True),
    coluna_unidade(),
    coluna_tenant(),
    UniqueConstraint(
        "tenant_id", "numero_oab", "uf_oab", name="uq_djen_oabs_tenant_oab"
    ),
    fk_tenant("djen_oabs", "id_usuario", "usuarios"),
    fk_tenant("djen_oabs", "id_criado_por", "usuarios"),
    fk_tenant("djen_oabs", "unidade_id", "unidades"),
)


# Partes do processo sem caso (docs/plano-processos-avulsos.md, §1). No
# processo de caso, as partes continuam vindo de `casos_atendidos`.
processo_partes = Table(
    "processo_partes",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("id_processo", Integer, nullable=False),
    Column("id_atendido", Integer, nullable=False),
    Column("polo", String(10), nullable=True),  # ativo | passivo | outro
    coluna_tenant(),
    UniqueConstraint(
        "tenant_id",
        "id_processo",
        "id_atendido",
        name="uq_processo_partes_tenant_parte",
    ),
    fk_tenant("processo_partes", "id_processo", "processos"),
    fk_tenant("processo_partes", "id_atendido", "atendidos"),
)

# Variações do nome do atendido, para a busca por parte no DJEN e para o
# filtro de parte da lista de processos.
atendido_nomes = Table(
    "atendido_nomes",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("id_atendido", Integer, nullable=False),
    Column("nome", String(150), nullable=False),
    coluna_tenant(),
    UniqueConstraint(
        "tenant_id", "id_atendido", "nome", name="uq_atendido_nomes_tenant_nome"
    ),
    fk_tenant("atendido_nomes", "id_atendido", "atendidos"),
)


djen_contextos = Table(
    'djen_contextos', metadata,
    Column('id', Integer, primary_key=True),
    Column('nome', String(150), nullable=False),
    Column('nomes', JSON, nullable=False),
    Column('tribunais', JSON, nullable=False),
    Column('criado_em', DateTime, nullable=False),
    Column('treino_status', String(20), nullable=False, server_default='ocioso'),
    Column('treino_token', String(36)),
    Column('treino_erro', String(500)),
    Column('treino_solicitado_em', DateTime),
    Column('treino_iniciado_em', DateTime),
    Column('treino_finalizado_em', DateTime),
    coluna_unidade(), coluna_tenant(),
    unica_tenant_id('djen_contextos'),
    fk_tenant('djen_contextos', 'unidade_id', 'unidades'),
)
djen_modelos = Table(
    'djen_modelos', metadata,
    Column('id', Integer, primary_key=True),
    Column('contexto_id', Integer, nullable=False),
    Column('criado_em', DateTime, nullable=False),
    Column('artefato', JSON, nullable=False),
    Column('metricas', JSON, nullable=False),
    coluna_tenant(), unica_tenant_id('djen_modelos'),
    fk_tenant('djen_modelos', 'contexto_id', 'djen_contextos'),
)
djen_publicacao_contextos = Table(
    'djen_publicacao_contextos', metadata,
    Column('id', Integer, primary_key=True),
    Column('id_publicacao', Integer, nullable=False),
    Column('contexto_id', Integer, nullable=False),
    Column('rotulo', String(20), nullable=False),
    Column('origem', String(30), nullable=False),
    Column('id_rotulado_por', Integer, nullable=True),
    Column('rotulado_em', DateTime, nullable=True),
    Column('modelo_id', Integer, nullable=True),
    Column('sugestao', String(20), nullable=True),
    Column('probabilidade', String(24), nullable=True),
    coluna_tenant(), unica_tenant_id('djen_publicacao_contextos'),
    UniqueConstraint('tenant_id', 'id_publicacao', 'contexto_id', name='uq_djen_pub_contexto'),
    Index('ix_djen_contexto_rotulo', 'tenant_id', 'contexto_id', 'rotulo'),
    CheckConstraint("rotulo IN ('relevante','irrelevante','nao_classificado')", name='ck_djen_ctx_rotulo'),
    fk_tenant('djen_publicacao_contextos', 'id_publicacao', 'djen_publicacoes'),
    fk_tenant('djen_publicacao_contextos', 'contexto_id', 'djen_contextos'),
    fk_tenant('djen_publicacao_contextos', 'id_rotulado_por', 'usuarios'),
    fk_tenant('djen_publicacao_contextos', 'modelo_id', 'djen_modelos'),
)
djen_contexto_historico = Table(
    'djen_contexto_historico', metadata,
    Column('id', Integer, primary_key=True),
    Column('relacao_id', Integer, nullable=False),
    Column('rotulo_anterior', String(20), nullable=False),
    Column('rotulo', String(20), nullable=False),
    Column('origem', String(30), nullable=False),
    Column('id_rotulado_por', Integer, nullable=True),
    Column('rotulado_em', DateTime, nullable=False),
    Column('modelo_id', Integer, nullable=True),
    Column('sugestao', String(20), nullable=True),
    coluna_tenant(),
    fk_tenant('djen_contexto_historico', 'relacao_id', 'djen_publicacao_contextos'),
    fk_tenant('djen_contexto_historico', 'id_rotulado_por', 'usuarios'),
    fk_tenant('djen_contexto_historico', 'modelo_id', 'djen_modelos'),
)
