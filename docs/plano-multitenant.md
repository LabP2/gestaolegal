# Plano: multitenancy (um tenant por NPJ)

Base: `master` em `b8f2f8d`, branch `feat/multitenant`. Este documento é só o
planejamento. Nada foi implementado nem migrado.

## 0. Resumo

O objetivo é atender vários Núcleos de Prática Jurídica (NPJs) no mesmo
servidor e no mesmo banco. Cada NPJ é um **tenant**, e cada tenant tem as suas
**unidades**. A DAJ/UFMG passa a ser o tenant 1, com Belo Horizonte e Nova Lima.

Recomendação: **esquema compartilhado, com `tenant_id` NOT NULL em todas as
tabelas de negócio**, e a imposição em quatro camadas independentes:

1. Coluna e integridade no banco: `coluna_tenant()` e FKs compostas
   `(tenant_id, x_id)`, para que um registro não possa apontar para um pai de
   outro tenant.
2. Filtro explícito no repositório, com um helper único em `BaseRepository`.
3. Uma **guarda de execução** que inspeciona cada statement Core antes de ele ir
   ao banco e **recusa** o que toca tabela de tenant sem o critério do tenant
   ativo.
4. Testes estruturais (varredura do `metadata`) e testes de vazamento entre dois
   tenants em todas as rotas.

Para o usuário, a multitenancy é **transparente**: todos os NPJs usam o mesmo
endereço, e o login pelo e-mail já leva cada pessoa ao seu NPJ. Para isso, o
e-mail é único em toda a plataforma (decisões em §14).

O pedido do usuário ("toda entidade herda de uma base com tenant e toda consulta
força o tenant") é o caminho certo, mas precisa ser adaptado: o código não tem
entidades ORM. A "base" vira o helper de coluna, e o "forçar" vira a guarda.

> **Mudança de rumo em relação a `docs/unidades.md` §1.** Aquele documento
> descartou o nível de tenant ("instância/banco separado por instituição") por
> causa do risco de vazamento a cada query esquecida. Este plano reverte a
> decisão, por pedido explícito. O risco apontado lá continua real e é o motivo
> das camadas 3 e 4: o esquecimento precisa quebrar um teste, e não depender de
> revisão.

## 1. Levantamento (em `b8f2f8d`)

| Item | Número | Onde |
|---|---|---|
| Tabelas em `metadata` | **28** | `gestaolegal/database/tables.py` |
| Tabelas com `unidade_id` (raízes) | 11 | `coluna_unidade()`, `tables.py:28` |
| `ForeignKey(...)` declaradas | 43 | `tables.py` |
| `unique=True` de coluna única | 6 | `tables.py:54, 234, 332, 466, 467, 486` |
| Modelo de acesso | **só Core** (`Table()` + `select/insert/update`) | nenhuma classe mapeada, nenhum `session.query`, nenhum `DeclarativeBase` |
| Repositories | 21 arquivos (+ `repository.py`) | `gestaolegal/repositories/` |
| `session.execute(...)` | 173 | 21 arquivos (20 repositories + `plantao_service.py`) |
| `select(` / `insert(` / `update(`+`delete(` | 105 / 29 / ~157 | repositories, services e controllers |
| SQL cru `text()` no app | **0** | só em `scripts/reset_demo_database.py`, `tests/api/conftest.py` (26) e um teste de migration |
| Queries fora de repository | 3 | `plantao_service.py:117, 389, 450` |
| Leituras de `get_unidade_ativa()` | 51 | 12 services |
| Rotas | 106 | 16 controllers |
| Testes | ~510 funções | `tests/` (29 arquivos em `tests/api/`) |
| Migrations / head atual | 22 / `e2f3a4b5c6d7` (head único) | `migrations/versions/` |

Duas conclusões. **Por ser só Core e sem `text()`, uma guarda de execução é
viável:** todo statement é uma árvore SQLAlchemy inspecionável. Um protótipo de
25 linhas com `sqlalchemy.sql.util.find_tables` e `visitors.iterate` detectou
corretamente a falta de critério em SELECT simples, em JOIN, em subquery, em
alias e em UPDATE. E `with_loader_criteria`/`do_orm_execute` com critério
automático **não se aplicam**: eles atuam sobre entidades mapeadas, e aqui não
há nenhuma.

## 2. Mecanismo de imposição: alternativas

| Opção | Isolamento | Custo aqui | Problemas |
|---|---|---|---|
| **A. Banco por tenant** (um database MySQL por NPJ, mesmo servidor) | Forte: query esquecida não vaza | Roteamento de engine por request, `migrate` em laço por banco, banco de controle para `tenants` | Criar tenant pela interface exige `CREATE DATABASE` + Alembic em tempo de execução (o usuário da app precisaria de privilégio de DDL). N bancos para migrar: um que falhe deixa versões divergentes. Backup e monitoramento multiplicados. Contraria o pedido. |
| **B. Schema por tenant** | No MySQL schema = database, igual à A | | |
| **C. Row-Level Security** | Seria o ideal | | **MySQL 8 não tem.** Views com `DEFINER` + variável de sessão é um arremedo frágil e não protege INSERT/UPDATE. |
| **D. `tenant_id` + filtro manual** (o padrão atual de unidade) | Depende de disciplina | Baixo | É exatamente onde o filtro de unidade falha (§4.2) |
| **E. `tenant_id` + filtro reescrito automaticamente** (injetar `WHERE` em todo statement) | Bom em SELECT simples | Médio | Reescrever cegamente quebra semântica: critério no `WHERE` para o lado nulo de um `OUTER JOIN` vira INNER JOIN e some linha calada. É "mágica" difícil de auditar. |
| **F. `tenant_id` + filtro explícito + guarda que _verifica_ e recusa** | Bom, e a falha é ruidosa | Médio | A guarda não prova que o critério está num ramo `AND` (um `or_(tenant_id == 1, id == 5)` passaria). Mitigado pela regra de que o critério vem sempre do helper e fica no nível de topo. |

**Recomendação: F**, com as FKs compostas como garantia no banco e a guarda
**preenchendo** `tenant_id` em INSERT (o valor vem de um contexto obrigatório,
então não é um default calado; ver §2.3). A opção A é a alternativa séria. Ela
passa a valer a pena se algum NPJ exigir por contrato a separação física dos
dados (LGPD: cada universidade é controladora dos dados dos seus atendidos) ou
backup e restauração por instituição. Registrado como decisão D1.

### 2.1 Camada 1: coluna e integridade

```python
# tables.py
def coluna_tenant() -> Column:
    return Column("tenant_id", Integer, ForeignKey("tenants.id"),
                  nullable=False, index=True)          # sem default, como coluna_unidade
```

- Entra em **todas** as 28 tabelas atuais (§3). As tabelas globais são listadas
  num único lugar (`TABELAS_GLOBAIS = {"tenants", "plataforma_admins"}`), que o
  teste estrutural e a guarda leem.
- **FKs compostas.** Cada tabela-pai ganha `UNIQUE (tenant_id, id)`. Cada FK
  entre tabelas de tenant vira `FOREIGN KEY (tenant_id, x_id) REFERENCES
  pai (tenant_id, id)`. Exemplo: `casos.id_orientador` passa a referenciar
  `usuarios(tenant_id, id)`, e `casos.unidade_id` passa a referenciar
  `unidades(tenant_id, id)`. É a única garantia que o MySQL dá sem RLS: o banco
  recusa vincular um caso do tenant A a um usuário, atendido ou unidade do
  tenant B, mesmo que o service erre. Com isso desaparece a classe de bug
  "tabela de ligação entre duas raízes" descrita em `docs/unidades.md` §5.1.
  Colunas de id sem FK declarada (`usuarios.criadopor`/`modificadopor`,
  `notificacao.id_caso`/`id_referencia`) ficam de fora. O service cuida delas.

### 2.2 Camada 2: filtro explícito no repositório

`BaseRepository` (`repositories/repository.py:62`) ganha:

```python
def escopo(self, stmt, *tabelas):           # where tabela.c.tenant_id == tenant ativo
def valores(self, data) -> dict:            # acrescenta tenant_id em INSERT
```

O parâmetro de tenant **não** é opcional nem passado pelo service. O
repositório lê o tenant de `RequestContext.get_tenant()`, que levanta exceção se
não houver tenant. Isso inverte o padrão de unidade, em que o repositório recebe
`unidade_id: int | None = None` e "esquecer" significa "sem filtro"
(`atendido_repository.py:34`, `caso_repository.py:25`,
`relatorio_repository.py:28`). `UPDATE` e `DELETE` por id passam a filtrar pelo
tenant também (hoje `caso_repository.py:70-76` atualiza só por `id`).

### 2.3 Camada 3: guarda de execução

Um listener `before_execute` (com `retval=True`) no `Engine` de
`database/session.py`. Ele cobre o `Session` e também as conexões diretas dos
scripts, com a função `instalar_guarda(engine)` reutilizável.

- **SELECT/UPDATE/DELETE**: `find_tables(stmt, include_joins, include_aliases,
  include_selects, include_crud)` dá as tabelas tocadas. Para cada tabela de
  tenant (resolvendo aliases), a guarda exige um `BinaryExpression`
  `tabela.c.tenant_id == <bind>` cujo valor seja o tenant ativo. Se faltar, ou
  se o valor divergir, levanta `TenantLeakError`. A guarda também recusa
  `TextClause` sobre o engine do app. O app hoje não tem nenhuma, e a regra
  impede que apareça.
- **INSERT**: se `tenant_id` não veio nos valores, preenche com o tenant ativo.
  Se veio diferente do ativo, recusa. `insert().values([...])` em lote
  (`notificacao_repository.create_many`) é verificado linha a linha.
- **Sem tenant ativo**: recusa sempre. A única saída é o context manager
  explícito `sem_tenant(motivo)`, que é registrado em log. Ele serve à
  plataforma (CRUD de `tenants`), às migrations (que não usam o engine do app) e
  ao reset de demo.
- Em produção a guarda **também recusa**, e não só registra em log. Um 500 é
  melhor que um vazamento. O custo de inspecionar a árvore é desprezível perto
  do round-trip ao MySQL. Medir no PR da guarda (D6).

**Como ficou no PR 3** (`gestaolegal/database/guarda_tenant.py`):

- INSERT sem `tenant_id` é **recusado**, e não preenchido: `valores()` já
  preenche, e um INSERT sem tenant indica código que não passou por ele.
- A travessia não usa `find_tables`, que devolve a tabela base de um alias como
  se estivesse no FROM. Cada alias precisa do seu próprio critério; o da tabela
  base não o cobre. Comparar `tenant_id` com outra coluna não conta.
- Sem contexto, a guarda recusa também as tabelas globais. Com tenant ativo,
  tabelas globais (`tenants`) podem ser lidas.
- Os testes instalam a guarda com `permitir_texto=True`, porque as fixtures
  gravam com `text()`. O acesso direto das fixtures em Core fica dentro de
  `sem_tenant("teste: ...")`.
- Medido: de 12 µs (SELECT por id) a 50 µs (casos com dois outer joins e
  EXISTS) por statement.
- Os scripts (`seed_database`, `importar_unidade`) usam engine próprio e ainda
  não instalam a guarda (PR 9).

### 2.4 Camada 4: testes estruturais e de vazamento

Ver §10.

## 3. Modelo de dados

### 3.1 Tabelas novas (globais, sem `tenant_id`)

**`tenants`**

| coluna | tipo | obs |
|---|---|---|
| id | int PK | 1 = DAJ/UFMG |
| nome | varchar(150) | "Divisão de Assistência Judiciária" |
| sigla | varchar(20) unique | "DAJ" |
| slug | varchar(40) unique | `[a-z0-9-]`, identificador para CLI e scripts (`--tenant daj-ufmg`); não aparece em URL; imutável depois de criado |
| instituicao | varchar(150) | "Faculdade de Direito da UFMG" |
| ativo | bool not null default true | inativo: login recusado, rotina do DJEN pula |
| criado_em | datetime not null | |
| id_criado_por | FK `plataforma_admins.id` null | |

**`plataforma_admins`**: id, nome, email unique, senha (bcrypt), ativo,
criado_em, ultimo_login_em. A tabela fica separada de `usuarios` de propósito
(§6).

`alembic_version` fica como está: não está no `metadata` e a guarda não a vê.

### 3.2 Quem recebe `tenant_id`: todas as 28

Não há tabela de lookup no banco (os domínios ficam em constantes no código), e
nenhuma tabela atual é global de verdade. Os casos que parecem exceção:

| Tabela | Decisão | Por quê |
|---|---|---|
| tabelas de ligação (`casos_atendidos`, `atendido_xOrientacaoJuridica`, `assistenciasJudiciarias_xOrientacao_juridica`, `usuarios_unidades`) | recebem | sem a coluna não há FK composta, e elas são o ponto cego já identificado na unidade |
| filhas sem unidade (`processos`, `historicos`, `arquivosCaso`, `arquivosEvento`, `assistidos`, `assistidos_pessoa_juridica`, `enderecos`) | recebem | **diferença deliberada em relação à unidade**: lá a filha herda pelo pai. Aqui, ter a coluna dispensa a "guarda do pai" para isolar tenants |
| `arquivos`, `documentos_roteiro` | recebem | eram "compartilhados entre unidades", mas são de cada NPJ |
| `notificacao` | recebe | os avisos gerais (`id_usu_notificar IS NULL`, `notificacao_repository.py:21-24`) chegariam a orientadores de **todos** os NPJs |
| `password_reset_tokens` | recebe | o usuário é do tenant; `token_hash` continua UNIQUE global (256 bits aleatórios) |
| `unidades` | recebe | cada NPJ tem as suas |

### 3.3 Unicidades que viram compostas

| Hoje | Depois | Atenção |
|---|---|---|
| `usuarios.email` UNIQUE (`tables.py:54`) | **mantém global** | o e-mail identifica o tenant no login (D2/D3). Quem atua em dois NPJs usa um e-mail diferente em cada um |
| `processos.numero` UNIQUE (`:234`) | `(tenant_id, numero)` | `_tratar_numero_duplicado` (`processo_repository.py:21-35`) casa o nome da chave `numero` por regex. **Renomear a constraint quebra a tradução para 400 e devolve 500.** Ajustar regex e teste no mesmo PR |
| `assistencias_judiciarias.email` (`:332`) | `(tenant_id, email)` | a importação de Nova Lima já rodou em produção, então os dados atuais já respeitam a unicidade; M2 só a estende com o tenant (D12) |
| `unidades.nome`, `unidades.sigla` (`:466-467`) | `(tenant_id, nome)`, `(tenant_id, sigla)` | a checagem prévia em `unidade_repository.py:47` precisa do tenant |
| `password_reset_tokens.token_hash` (`:486`) | mantém global | |
| `plataforma_admins.email` | global, na própria tabela | é outra identidade, com login próprio: pode repetir um e-mail de `usuarios` |
| *(nova)* `UNIQUE (tenant_id, id)` em toda tabela-pai | alvo das FKs compostas | |
| unicidades lógicas no código (senha da fila por unidade e dia, plantão singleton por unidade) | já são por unidade, e unidade ⊂ tenant | nada a mudar |

## 4. Tenant e unidade

### 4.1 Como convivem

```
tenant (NPJ) ──< unidades ──< registros raiz (unidade_id)
     │                  └──< usuarios_unidades >── usuarios (do tenant)
     └── tenant_id em TODA tabela
```

- **Tenant é fronteira de segurança, e unidade é fronteira de navegação.** O
  tenant isola: nada atravessa, nem para o admin do NPJ. A unidade organiza: o
  admin vê todas as do seu tenant, e um atendido de BH pode estar num caso de NL
  (`docs/unidades.md`, decisão 3).
- `X-Unidade-Id` continua como está (`api_decorators.py:20-42`). Como
  `user.unidades` passa a vir de `usuarios_unidades` filtrado pelo tenant, a
  checagem `unidade_id in user.unidades` já recusa a unidade de outro tenant, e
  a FK composta `(tenant_id, unidade_id)` garante o mesmo no banco.
- O que se reaproveita do padrão de unidade: o helper de coluna sem default
  (`tables.py:28`), o ContextVar em `RequestContext` (`request_context.py:6`),
  o decorator que resolve o contexto antes da rota (`api_decorators.py:57-100`),
  a migration em três passos (nula → preenche → NOT NULL, `b7c1d2e3f4a5`) e o
  `--check` e o relatório do `importar_unidade.py`.
- `UNIDADE_PADRAO_ID = 1` (`tables.py:25`, usado em `usuario_service.py:414`)
  deixa de fazer sentido como constante global. Cada tenant nasce com a sua
  unidade inicial (§6.3), e o `create_admin` recebe a unidade explicitamente.

### 4.2 Onde o filtro de unidade falha ou é esquecido hoje (lições)

| Achado | Onde | Lição para o tenant |
|---|---|---|
| Filtro é parâmetro **opcional** do repositório; omitir = sem filtro | `atendido_repository.py:34`, `caso_repository.py:25`, `relatorio_repository.py:28-170` | tenant nunca é parâmetro; o repositório lê do contexto e a guarda verifica |
| `UPDATE`/`DELETE` só por `id` | `caso_repository.py:70-76` e equivalentes | escrita também leva o critério; a guarda checa UPDATE/DELETE |
| Guarda do pai feita no **controller**: `ProcessoService.update`/`soft_delete` (`processo_service.py:156-180`) não validam o caso; dependem de `caso_controller.py:232/254` chamar `validate_processo_for_caso` antes | | com `tenant_id` em `processos`, a guarda de tenant não depende da ordem das chamadas |
| Busca global devolve usuários sem filtro | `search_controller.py:58` → `UsuarioService.search` | para unidade foi decisão de produto; para tenant seria vazamento. A coluna em `usuarios` resolve |
| Avisos gerais de notificação visíveis a todos | `notificacao_repository.py:21-24` | idem |
| Queries fora do repository | `plantao_service.py:117, 389, 450` | a guarda cobre, e o lint (§10) aponta |
| Tabela de ligação entre duas raízes sem coluna | `assistenciasJudiciarias_xOrientacao_juridica` | coluna + FK composta nas duas pontas |
| Default de coluna mascarava esquecimento | histórico em `docs/unidades.md` §5.1 | `coluna_tenant()` sem default; quem preenche é a guarda, e só com contexto |

## 5. Resolução do tenant por requisição

**Decisão: um só endereço para todos os NPJs. O tenant sai do e-mail no login e,
depois dele, do JWT, que é a única autoridade.** O usuário não escolhe nem vê o
tenant: ele já cai no seu NPJ (D3).

1. **No login** (`POST /api/auth/login`), `UsuarioService.authenticate(email,
   senha)` busca o usuário pelo e-mail, que é único em toda a plataforma (§3.3).
   Essa é **a única leitura de `usuarios` sem tenant** feita durante uma
   requisição: roda em `sem_tenant("login")`, devolve o `tenant_id` do usuário e
   fica numa lista explícita da guarda. Em seguida a senha é conferida, e o
   tenant precisa estar ativo. Usuário inexistente, senha errada e tenant
   inativo devolvem a mesma resposta genérica de login inválido.
   `JWTAuth.generate_token` (`jwt_auth.py:13-25`) passa a incluir `tenant_id` e
   `aud="tenant"`.
2. **Em cada request autenticado**, o `@authenticated` lê `tenant_id` do token,
   confere que o tenant está ativo e grava em `RequestContext.set_tenant()`
   **antes** de carregar o usuário (`jwt_auth.py:42-53` faz `find_by_id`, que já
   passa pela guarda). Não há cabeçalho de tenant: o cliente não tem como pedir
   outro tenant. Token antigo sem `tenant_id` é recusado: no deploy todo mundo
   faz login de novo, e o token já expira em 12 h.
3. **Rotas públicas antes do login** (`/forgot-password`, `/reset-password*`):
   - a busca do e-mail (`password_reset_service.py:44`) também roda em
     `sem_tenant`, está na lista da guarda e grava o token já com o `tenant_id`
     do usuário;
   - ao usar o token, o tenant vem da linha do token;
   - `FRONTEND_URL` continua um endereço só;
   - `/needs-setup` sai junto com o setup-admin (D4).
4. **Unicidade do e-mail entre NPJs.** Ao criar ou editar um usuário, a checagem
   de e-mail repetido olha a plataforma inteira (em `sem_tenant`, devolvendo
   só sim ou não). A mensagem é genérica ("e-mail já está em uso"), sem dizer em
   qual NPJ.
5. **Tela de login** genérica, sem o nome do NPJ. Depois do login, o nome e a
   sigla do tenant aparecem no cabeçalho, vindos de `/api/auth/me` ou de um
   campo novo no token.
6. **Sem request** (scripts, seed, reset, CLI e rotina do DJEN):
   `with contexto_tenant(tenant_id):` define e restaura o ContextVar. Laço
   padrão:
   ```python
   for t in TenantService().ativos():          # dentro de sem_tenant()
       with contexto_tenant(t.id):
           ...                                  # a unidade continua explícita
   ```
   `RequestContext.clear()` (`handlers.py:11`) passa a limpar o tenant também.

Descartados: subdomínio por NPJ e prefixo de caminho. Os dois exigiriam
DNS/certificado ou reescrever as rotas do SvelteKit, e o usuário pediu que o
tenant fosse invisível.

## 6. Administrador da plataforma

### 6.1 Papel e autenticação

- **É um papel separado, que não entra em `urole`.** O `admin` de hoje continua
  sendo o administrador do NPJ, limitado ao seu tenant. O administrador da
  plataforma fica em `plataforma_admins`, faz login em `POST
  /api/plataforma/auth/login` e recebe um JWT com `aud="plataforma"` e sem
  `tenant_id`. Um decorator `@plataforma_admin` recusa token de tenant, e o
  `@authenticated` recusa token de plataforma. O `aud` já evita que um token
  sirva no lugar do outro, e a tabela separada evita que um `UPDATE usuarios SET
  urole=...` crie um superusuário.
- **O administrador da plataforma não lê dados dos tenants** (sem
  impersonação). Ele só vê `tenants` e contagens agregadas no futuro. Suporte
  dentro de um NPJ passa por uma conta de admin criada lá, que fica visível ao
  NPJ (D5).
- **Bootstrap**: o comando `flask plataforma criar-admin --email ...`, rodado no
  host com `docker compose run --rm api`. O `/api/auth/setup-admin`
  (`auth_controller.py:56`) com `ADMIN_SETUP_TOKEN` deixa de criar usuário em
  banco vazio, porque "banco sem usuários" não existe mais por tenant. Proposta:
  remover a rota e a tela `web/src/routes/setup-admin` (D4).

### 6.2 API

| Método | Rota | Ação |
|---|---|---|
| POST | `/api/plataforma/auth/login` | login |
| GET | `/api/plataforma/tenants` | lista (filtros `ativo`, `q`) |
| POST | `/api/plataforma/tenants` | cria tenant + unidade inicial + primeiro admin (§6.3) |
| GET | `/api/plataforma/tenants/<id>` | detalhe |
| PUT | `/api/plataforma/tenants/<id>` | nome, sigla, instituição (slug imutável) |
| PATCH | `/api/plataforma/tenants/<id>/ativo` | ativa/desativa (sem DELETE) |

Todas as rotas da plataforma rodam em `sem_tenant("plataforma")`, exceto o
passo de criação dos registros iniciais, que roda em `contexto_tenant(novo.id)`.

### 6.3 Criar um tenant cria, na mesma transação

1. a linha em `tenants`;
2. a **unidade inicial** (nome e sigla informados no formulário, ex.: "Sede"/"SD");
3. o **primeiro admin do NPJ** (nome e e-mail, que não pode existir em nenhum
   outro NPJ). Reaproveita
   `UsuarioService.create_admin` (`usuario_service.py:361`), que passa a receber
   tenant e unidade, e o vincula à unidade inicial;
4. um token de definição de senha (infraestrutura de `password_reset_service`)
   e o link exibido **na tela da plataforma**, para o administrador repassar. O
   envio automático por e-mail fica para depois: e-mail real a terceiros é item
   de "Não altere sem decisão explícita" no `CLAUDE.md` e já tem pendência própria
   (convite, `docs/known_issues.md`).

Não cria: roteiros, assistências judiciárias ou arquivos gerais. O NPJ começa
vazio.

### 6.4 Front

- Grupo de rotas `web/src/routes/(plataforma)/plataforma/...`, com layout
  próprio, cookie próprio (`plataforma_token`) e telas de login, lista, criação
  e edição de tenants. Servido em `/plataforma`, no mesmo endereço do
  sistema.
- O `api-client.ts` não muda o envio de cabeçalhos: continua só com o
  `X-Unidade-Id` (`:57`). O nome do NPJ aparece no cabeçalho do sistema depois
  do login.
- Tipos novos em `web/src/lib/types/tenant.ts`. Muda o contrato consumido pelo
  front (revisão humana).
- Marca fixa "DAJ/UFMG" no front (`app-footer.svelte`, `termos-de-uso`,
  formulários) passa a vir do tenant. Fica em PR separado e não bloqueia.

## 7. Migração dos dados existentes

O tenant inicial é **id 1, slug `daj-ufmg`, "DAJ/UFMG"**, e recebe todos os
registros atuais. Volume de produção pequeno (milhares de linhas por tabela;
ver `docs/unidades.md` §2). Cada `ALTER` leva segundos, mas a reconstrução das
FKs trava a escrita da tabela enquanto roda, então a aplicação é numa janela
com a API parada.

Ordem, em **três migrations encadeadas** (uma por PR, cada uma com `downgrade`):

| # | Migration | Conteúdo |
|---|---|---|
| M1 | `tenants` | cria `tenants` e `plataforma_admins`; insere o tenant 1 |
| M2 | `tenant_id` | em cada uma das 28 tabelas: `add_column` nula → `UPDATE ... SET tenant_id = 1` → `NOT NULL` + FK `tenants.id` + índice. Troca as unicidades de §3.3 por compostas |
| M3 | FKs compostas | `UNIQUE (tenant_id, id)` nos pais; `drop_constraint` de cada FK simples e `create_foreign_key` composta. Gerada a partir do `metadata`, com a lista conferida à mão no PR |

- A migration usa a **lista literal** das tabelas, como `TABELAS_RAIZ` em
  `b7c1d2e3f4a5_unidades.py`, e nunca o `metadata` vivo: tabela criada depois
  não pode mudar uma migration antiga.
- **FKs sem nome.** Várias FKs da baseline `ed1b0a0a61a6` foram criadas sem nome
  explícito. Os nomes reais no MySQL de produção (`casos_ibfk_N`) precisam ser
  lidos por `inspect()` dentro da migration, nunca assumidos. Ensaiar M3 contra
  uma cópia local (`scripts/producao_para_local.sh`, que só lê a produção, e
  rodar isso é decisão humana) antes de QA.
- **Rollback.** `downgrade` de M3 → M2 → M1 desfaz na ordem inversa. O
  `downgrade` de M2 **recusa** se existir `tenant_id <> 1`: com um segundo NPJ
  dentro, voltar significaria misturar dados (mesmo critério de recusa da
  `e2f3a4b5c6d7`). Antes de rodar em produção: dump completo e imagem anterior
  da API marcada.
- **Dois heads.** O DJEN (`feat/djen`) também vai criar migration. Antes de cada
  PR: `alembic -c migrations/alembic.ini heads` com um head só, e o DJEN faz
  rebase sobre M3. Migration exige revisão humana, e os testes (SQLite +
  `create_all`) **não** pegam dois heads nem erro de DDL do MySQL. Acrescentar
  ao `make test` um teste que carrega o `ScriptDirectory` e exige
  `len(get_heads()) == 1` (estende a verificação; não afrouxa nada).
- **Nova Lima já foi importada e roda em produção** (D7). M2 marca tudo, BH e
  NL, como tenant 1. O `importar_unidade.py` só ganha `--tenant` quando houver
  uma nova importação.

## 8. Arquivos privados

Proposta: `PRIVATE_FILES_ROOT/<tenant_id>/<categoria>/<ref>`
(`private_file_storage.py:57`, `categoria_dir`).

- Usar o **id**, não o slug: o id é o que as FKs usam e não depende de texto.
- `caminho`/`link_arquivo` continuam relativos à categoria, então **o banco não
  muda**. Só o diretório base passa a incluir o tenant do contexto.
- Os arquivos existentes vão para `<raiz>/1/` com um script de uma vez (um
  `rename` dentro do mesmo volume, instantâneo), com `--check` e relatório no
  estilo de `migrar_arquivos_privados.py`. Fica sem fallback permanente para o
  layout antigo: fallback é exatamente o caminho por onde um tenant leria a
  pasta de outro.
- A validação de subida (`PRIVATE_FILES_ROOT` fora de `static_folder`)
  continua igual.

## 9. Scripts, seed, reset e testes de base

| Item | Muda |
|---|---|
| `scripts/seed_database.py` | `--tenant SLUG` (padrão `daj-ufmg`); cria o tenant se faltar e roda dentro de `contexto_tenant`. Hoje escolhe unidades por `ativa` (`:97-103`): passa a filtrar pelo tenant. Semeia também um segundo tenant `npj-demo`, com e-mails próprios (`admin@npjdemo.br`, `orient@npjdemo.br`, `estag_direito@npjdemo.br`, `colab_ext@npjdemo.br`, mesma senha padrão), para demonstrar o isolamento (D11) |
| `scripts/reset_demo_database.py` | Hoje faz `DROP DATABASE` (`:61-62`), o que apagaria **todos os tenants**. O `--check` passa a recusar se `tenants` tiver slug fora de `DEMO_TENANT_SLUGS`. Reset de um tenant só (DELETE por `tenant_id` em ordem topológica) fica fora deste plano. Executar continua exigindo autorização explícita |
| `scripts/importar_unidade.py` | Nova Lima já foi importada; o script só precisa mudar numa próxima importação: `--tenant SLUG` obrigatório, `--sigla` dentro do tenant, INSERT com `tenant_id`. Até lá, a salvaguarda "tabela não coberta pelo `PLANO`" recusa rodar depois de M2, o que basta |
| `scripts/migrar_arquivos_privados.py` | destino com `<tenant_id>/` |
| `scripts/seed_local.py` (esteira Helton, via API) | sem mudança: o tenant vem do login |
| `tests/api/conftest.py` | `ensure_tenants()` (tenants 1 e 2) antes de `ensure_unidades()` (`:117`); unidades 1 e 2 no tenant 1, unidade 3 no tenant 2; os 26 `text(...)` de INSERT passam `tenant_id`; fixtures de header (`:376, 392, 416, 490`) passam a gerar token com `tenant_id`; nova fixture `headers_outro_tenant` |
| CLI | `flask plataforma criar-admin`, `flask tenant listar` |

## 10. Testes

**Estruturais** (`tests/database/test_tenant_schema.py`, rodando sobre o
`metadata`):
- toda tabela fora de `TABELAS_GLOBAIS` tem `tenant_id` NOT NULL, indexada, com
  FK para `tenants`;
- toda UNIQUE de tabela de tenant inclui `tenant_id` (lista explícita de
  exceções: `password_reset_tokens.token_hash`);
- toda FK entre tabelas de tenant é composta com `tenant_id`;
- um único head de Alembic.

**Guarda** (`tests/api/test_tenant_guard.py`): SELECT sem critério, critério de
outro tenant, JOIN com o lado direito sem critério, alias, subquery, UPDATE e
DELETE sem critério, INSERT que preenche o tenant, INSERT com tenant
divergente, `text()` recusado, execução sem contexto recusada e `sem_tenant`
liberado.

**Lint** (teste que lê o código): nenhuma ocorrência de `text(` nem de
`session.execute` em `gestaolegal/` fora de `repositories/`, exceto uma lista
explícita (hoje, `plantao_service.py`).

**Vazamento entre tenants** (`tests/api/test_tenant_isolamento.py`), a peça
central:
1. A fixture cria os tenants A e B, cada um com uma unidade, um admin com
   e-mail próprio, e um conjunto completo de dados: atendido, assistido, caso,
   processo, evento, lembrete, orientação, assistência, fila, plantão, presença,
   arquivo, notificação geral e roteiro. Todo texto de B leva a marca
   `VAZOU-B-<tabela>`.
2. O teste varre `app.url_map` (106 rotas). Para cada rota GET, chama com o
   token de A, substituindo os `<int:...>` pelos ids de B. Espera **404 ou lista
   vazia**, e **nenhuma resposta pode conter `VAZOU-B`**. Para PUT, PATCH e
   DELETE com ids de B, espera 404, e os dados de B ficam iguais depois.
3. Uma rota nova sem caso de teste falha o teste: a lista de rotas cobertas é
   comparada ao `url_map`, como a salvaguarda do `PLANO` em `importar_unidade.py`.
4. Login: o e-mail de A devolve token com o tenant de A, e o de B, com o de B.
   Criar em B um usuário com o e-mail de A dá 400, com mensagem que não cita A.
   Tenant inativo dá a mesma resposta de login inválido. Token sem `tenant_id`
   dá 401. Token de plataforma numa rota de tenant dá 401, e o inverso também.
   As únicas consultas `sem_tenant` durante uma requisição são as do login e as
   da recuperação de senha (teste sobre a lista da guarda).
5. FK composta: o INSERT direto de um caso de A apontando para um usuário de B
   falha com `IntegrityError`. O conftest **não** liga `PRAGMA foreign_keys`
   hoje, e o SQLite ignora FKs sem ele. Ligar só neste teste, numa engine
   própria: ligar no conftest inteiro pode quebrar fixtures que gravam linhas
   órfãs, e isso é uma mudança separada.

Os ~510 testes atuais continuam verdes com o tenant 1 implícito nas fixtures.
Nenhuma asserção existente é removida.

## 11. Impacto no DJEN (`/mnt/dados/gestaolegal-djen/docs/plano-djen.md`)

- `djen_oabs`, `djen_comunicacoes` e `djen_sincronizacoes` recebem
  `coluna_tenant()`, e as FKs para `casos`, `processos`, `usuarios` e
  `unidades` são compostas.
- Unicidades: `djen_oabs (numero_oab, uf_oab)` → `(tenant_id, numero_oab,
  uf_oab)`. `djen_comunicacoes.id_djen` UNIQUE → `(tenant_id, id_djen)`: um
  professor com OAB cadastrada em dois NPJs recebe a mesma publicação nos dois.
  `eventos.id_djen_comunicacao` pode continuar UNIQUE (aponta para o id local).
- `processos.numero_cnj` é casado **dentro do tenant**.
- Rotina `flask djen sincronizar`: laço de §5, item 6, um tenant de cada vez e
  pulando os inativos. `djen_sincronizacoes` é por tenant, e a falha de um não
  interrompe os outros. Opção `--tenant SLUG` para rodar um só.
- A migration do DJEN nasce depois de M3, com head único.

## 12. Fases e PRs

| PR | Conteúdo | Revisão humana |
|---|---|---|
| 1 | `tenants`, `plataforma_admins`, `coluna_tenant()`, `TABELAS_GLOBAIS`, `RequestContext.get_tenant/set_tenant`, `contexto_tenant`/`sem_tenant`; **M1** | migration |
| 2 | `tenant_id` nas 28 tabelas, unicidades compostas, `BaseRepository.escopo/valores` aplicados nos 21 repositories, conftest com tenants, regex de `processos.numero`; **M2**; testes estruturais (exceto FK composta) | migration, filtro |
| 3 | Guarda de execução + testes da guarda + lint; liga a guarda em todos os testes | |
| 4 | JWT com `tenant_id`/`aud`; login e recuperação de senha resolvendo o tenant pelo e-mail; checagem de e-mail único na plataforma; nome do NPJ no cabeçalho; remoção de `/setup-admin` e `/needs-setup` | contrato API/front, permissões |
| 5 | **M3** (FKs compostas) + teste estrutural de FK + teste de `IntegrityError` | migration |
| 6 | Testes de vazamento varrendo `url_map` (podem começar no PR 4 e endurecer aqui) | |
| 7 | Plataforma: login, CRUD de tenants, criação com unidade + admin + link de senha, CLI `criar-admin`, telas `(plataforma)` | contrato, permissões |
| 8 | Arquivos privados por tenant + script de movimentação | |
| 9 | Scripts: seed com dois tenants, `--check` do reset | |
| 10 | Implantação: ensaio M1–M3 em cópia local, QA, janela de produção | **gate humano** (produção/QA) |
| — | DJEN começa aqui | |

PRs 1–3 podem ir para o `master` sem mudar o comportamento visível: só existe o
tenant 1, e o login continua igual até o PR 4.

**Fases futuras (fora deste plano):** limites por tenant (usuários, casos,
processos e armazenamento), com cobrança da cota nos services de criação;
branding por tenant (logo, termos de uso, rodapé); exportação e exclusão de um
tenant inteiro (pedido LGPD do controlador); reset de demo por tenant; e-mail de
convite automático; auditoria das ações do administrador da plataforma; 2FA
para a plataforma.

## 13. Riscos

| Risco | Mitigação |
|---|---|
| Query que escapa da guarda (`OR` com o critério, critério só num ramo do `CASE`) | helper único, revisão, teste de vazamento por rota |
| Guarda recusando uma query legítima em produção (500) | rodar toda a suíte com a guarda ligada desde o PR 3; ensaio em QA com uso real |
| M3 falhando no MySQL por nome de FK ou dado órfão | ler nomes com `inspect()`; checar órfãos antes e abortar com relatório; ensaio em cópia |
| Dois heads com o DJEN | ordem fixa (multitenant antes); teste de head único no `make test` |
| `reset_demo` apagando um tenant real | `--check` com lista de slugs permitidos; continua exigindo autorização |
| Consulta de login sem tenant virar porta de vazamento | é só a busca por e-mail, numa lista fechada da guarda, coberta por teste; devolve só id e tenant |
| Desempenho dos índices | `tenant_id` lidera os índices compostos novos; volume atual pequeno |

## 14. Decisões (tomadas em 2026-11-07)

| # | Questão | Decisão |
|---|---|---|
| D1 | Esquema compartilhado ou banco por tenant? | **Compartilhado**, com `tenant_id` em todas as tabelas. Reavaliar se algum NPJ exigir separação física por contrato |
| D2 | Mesma pessoa em mais de um NPJ? | **Contas separadas.** Como o e-mail é único na plataforma (D3), quem atua em dois NPJs usa um e-mail diferente em cada |
| D3 | Como o tenant é escolhido? | **Mesmo endereço para todos, multitenancy invisível.** O tenant sai do e-mail no login, que é único em toda a plataforma, e depois vem só do JWT (§5) |
| D4 | `/api/auth/setup-admin` e `ADMIN_SETUP_TOKEN` | **Remover.** Bootstrap por `flask plataforma criar-admin`; o primeiro admin do NPJ é criado pela plataforma |
| D5 | Admin da plataforma entra num tenant? | **Não** nesta fase. Suporte por uma conta de admin criada no NPJ, visível a ele |
| D6 | A guarda recusa ou só registra em produção? | **Recusa** (500 é melhor que vazamento); medir o custo no PR 3 |
| D7 | Importação de Nova Lima | **Já executada e em produção.** M2 marca BH e NL como tenant 1 |
| D8 | FKs compostas | **Todas** as FKs entre tabelas de tenant, em PR próprio (M3) |
| D9 | Arquivos privados | **`<raiz>/<tenant_id>/<categoria>`**, movendo os atuais para `1/`, sem fallback |
| D10 | Acesso do primeiro admin do NPJ | **Link de definição de senha na tela da plataforma.** Convite por e-mail fica para depois |
| D11 | Seed de demo | **Dois tenants:** `daj-ufmg` com as contas atuais e `npj-demo` com e-mails `@npjdemo.br` |
| D12 | `assistencias_judiciarias.email` | **Único por tenant.** Com Nova Lima já importada, não há colisão pendente |
