# Processos sem caso e busca por parte no DJEN

Objetivo: permitir que a Procuradoria da UFMG acompanhe os processos em que a
universidade (ou outra parte que ela acompanha) é parte, sem abrir caso e sem
triagem socioeconômica. Decisão do responsável em 09/11/2026: **processo sem
caso** e **assistido sem triagem**.

Contexto: hoje `processos.id_caso` é obrigatório, o processo herda unidade e
permissões do caso, e as partes vêm de `casos_atendidos`. O DJEN cria evento no
caso ao vincular uma publicação.

## 1. Modelo (migration — revisão humana)

Uma migration, com `down_revision` no head atual do worktree. Conferir
`alembic -c migrations/alembic.ini heads` antes e depois.

| Tabela | Mudança |
|---|---|
| `processos` | `id_caso` passa a aceitar nulo. Nova `unidade_id` (`coluna_unidade()`, NOT NULL), preenchida na migration a partir do caso. Processo de caso grava a unidade do caso; processo sem caso grava a unidade ativa. |
| `processo_partes` (nova) | `id`, `id_processo`, `id_atendido`, `polo` (`ativo` \| `passivo` \| `outro`, nulo permitido), `tenant_id`. Única por (`tenant_id`, `id_processo`, `id_atendido`). Usada sobretudo no processo sem caso; no processo de caso as partes continuam vindo do caso. |
| `atendidos` | Nova `sem_triagem` (Boolean, server_default 0). Atendido com `sem_triagem=1` conta como assistido (`is_assistido`) sem ter linha em `assistidos`. As colunas de dados pessoais hoje NOT NULL (`data_nascimento`, `cpf`, `celular`, `email`, `estado_civil`, `como_conheceu`, `procurou_outro_local`, `pj_constituida`) passam a aceitar nulo **no banco**. O cadastro normal continua exigindo tudo pela validação de entrada; só o cadastro simplificado aceita vazio. |
| `atendido_nomes` (nova) | `id`, `id_atendido`, `nome` (String 150), `tenant_id`. Única por (`tenant_id`, `id_atendido`, `nome`). Variações do nome para a busca no DJEN e para o filtro da lista. |

Tudo com `coluna_tenant()`, `unica_tenant_id` e `fk_tenant`, como as demais.

## 2. Regras

- **Cadastro simplificado da parte**: nome (obrigatório), CPF ou CNPJ (opcional),
  observação, unidade ativa. Marca `sem_triagem=1`. Na ficha do atendido aparece
  "Assistido sem triagem"; fazer a triagem depois segue o fluxo normal e mantém
  o atendido.
- **Processo sem caso**: mesmos campos do processo, mais ao menos uma parte
  (atendido existente ou cadastrado na hora). `id_caso` nulo, `unidade_id` da
  unidade ativa. O número segue as regras atuais de `numero_cnj` e
  `djen_pendente` (não mexer em `normalizar_cnj`: outro agente está corrigindo).
- **Visibilidade**: lista e processos sem caso seguem a unidade ativa.
  `admin`, `prof`, `orient` e `colab_proj` veem e cadastram processos sem caso;
  `estag_direito` e `colab_ext` veem na lista só os processos dos casos que já
  podem ver hoje e nunca os sem caso. Mesma régua da gestão do DJEN, se ela
  existir como constante; senão, criar uma constante e citar aqui.
- **DJEN**: a rotina já casa publicação com processo por `numero_cnj`. Com
  processo sem caso, a publicação fica `vinculada` com `id_processo` preenchido
  e `id_caso` nulo, **sem criar evento** (evento exige caso). Todo ponto de
  `djen_service.py` que faz `self.casos.find_by_id(processo.id_caso...)` precisa
  tratar o caso ausente.

## 3. API (contrato — revisão humana)

- `GET /api/processos`: lista paginada. Filtros: `parte` (nome do atendido do
  caso, das partes do processo ou de `atendido_nomes`; `ilike`), `numero`,
  `distribuicao_de` / `distribuicao_ate`, `status` (ativo/inativo/todos),
  `com_caso` (sim/não/todos). Cada item traz id, número, espécie, vara, data de
  distribuição, status, id do caso (ou nulo), nomes das partes e total de
  publicações do DJEN.
- `POST /api/processos`: processo sem caso com partes.
- `GET/PUT/DELETE /api/processos/<id>`: detalhe, edição e exclusão lógica,
  também para processo de caso (respeitando as permissões do caso).
- `POST /api/atendidos/simplificado`: cadastro simplificado.
- `GET/POST/DELETE /api/atendidos/<id>/nomes`: variações do nome.
- `GET /api/djen/busca-parte?nome=&de=&ate=&tribunal=`: consulta direta à API do
  DJEN por `nomeParte`, **sem gravar nada**. Período máximo de 30 dias. Cada
  resultado diz se a publicação já está no banco e se o número bate com um
  processo cadastrado.
- `POST /api/djen/busca-parte/importar`: grava as publicações escolhidas;
  vincula ao processo existente pelo número, ou cria o processo sem caso com a
  parte informada e vincula.

Rotas novas entram em `test_tenant_vazamento.py` e na lista de permissões.

## 4. Telas

- **Menu "Processos"** → `/processos`: tabela com filtros (nome da parte,
  número, distribuição de/até, status, com/sem caso); cada linha com link e
  ícone de olho para o detalhe; botão "Novo processo sem caso".
- `/processos/novo`: formulário do processo + partes (busca de atendido ou
  "cadastrar parte sem triagem" num diálogo).
- `/processos/[id]`: detalhe do processo, com o card de publicações do DJEN
  igual ao da tela do caso. Se tiver caso, link para o caso.
- **Ficha do atendido**: seção "Nomes para o DJEN" (adicionar e remover) e
  selo "Sem triagem".
- `/djen/busca-parte`: nome livre ou escolher atendido (preenche com o nome e as
  variações), período, tribunal opcional; resultados em lista com caixa de
  seleção; "Importar selecionadas" pede, para número sem processo, a parte do
  novo processo sem caso.

## 5. Fora do escopo

- Captura automática por nome da parte (homônimos; ver `docs/plano-djen.md`).
- Eventos e prazos em processo sem caso.
- Criar um NPJ separado para a Procuradoria: é configuração na plataforma, não
  código.

## Decisões tomadas na implementação

Pontos em que a especificação não cabia no código como está, ou deixava a
escolha em aberto. Valeu a solução mais simples e coerente com o restante do
sistema.

**Modelo e migration** (`f1a2b3c4d5e6`, sobre `d3e4f5a6b7c8`)

- `processos.unidade_id` é obrigatória (`coluna_unidade()`) e é preenchida na
  migration com a unidade do caso. O processo de caso continua herdando a
  unidade do caso no `create`/`update`. O processo sem caso recebe a unidade
  ativa.
- As oito colunas de `atendidos` que o cadastro simplificado deixa vazias
  passaram a aceitar nulo no banco. O MODIFY repete o tipo, o charset e a
  collation lidos do `information_schema`, para não converter as colunas latin1.
  O cadastro normal continua exigindo tudo pela validação de entrada.
- O downgrade se recusa a rodar (RuntimeError) se já existe processo sem caso,
  parte sem triagem ou atendido com algum desses campos vazio. Voltar a NOT
  NULL exigiria apagar ou inventar dados.
- `sem_triagem` usa só `server_default` (sem default Python), e `inserir` do
  `scripts/seed_database.py` ignora as colunas que ainda não existem. Assim, o
  seed continua rodando em revisões anteriores, como faz o teste de migration.

**Regras**

- As rotas de atendido ficaram em `/api/atendido/...` (singular, blueprint
  existente): `POST /api/atendido/simplificado` e `/api/atendido/<id>/nomes`.
- Quem vê e cadastra processo sem caso (`PAPEIS_SEM_CASO`): `admin`, `prof`,
  `orient` e `colab_proj`, a mesma régua da unidade do DJEN.
- `estag_direito` e `colab_ext` usam a régua do DJEN. Na lista e no detalhe,
  veem só processos de casos em que participam (nunca processo sem caso); fora
  disso a resposta é 404.
- Inativar: processo de caso, só `admin` (como antes); processo sem caso,
  `PAPEIS_SEM_CASO`. A edição por `PUT /api/processos/<id>` vale para quem
  enxerga o processo. O caso do processo não muda por essa rota, e as partes só
  se editam no processo sem caso.
- `is_assistido` passou a considerar também `sem_triagem`, para a parte poder
  entrar em caso. `create_assistido` (a triagem completa) limpa `sem_triagem`.
- Documento no cadastro simplificado: CPF com 11 dígitos ou CNPJ com 14,
  gravados com máscara. Qualquer outra quantidade dá 400.

**DJEN**

- Publicação de processo sem caso: o vínculo usa `id_caso` nulo, a unidade vem
  do processo e nenhum evento é criado. O casamento por número considera só os
  processos da unidade ativa (vínculo manual e busca de processo).
- Mensagem de publicação já vinculada: "A publicação já está vinculada a um
  processo" (antes dizia "caso").
- A lista de publicações aceita o filtro `processo_id`, usado pelo card da
  tela do processo.
- Busca por parte (`GET /api/djen/busca-parte`) e importação (`POST
  .../importar`) ficam com `PAPEIS_GESTAO` (`admin`, `prof`, `orient`), como os
  demais comandos do DJEN. Limites: período de até 30 dias, até 5 nomes, no
  máximo 10 páginas por nome (o resultado indica `truncado`) e até 100
  publicações por importação. A busca não grava nada.
- A importação refaz a consulta no DJEN e grava a partir dela. O conteúdo das
  publicações nunca vem do corpo da requisição. Para cada número sem processo
  na unidade:
  - cria um processo sem caso, com espécie "Outros", vara e identificação
    tiradas do DJEN (passadas por `para_latin1`) e `djen_pendente`;
  - usa uma única parte (`id_atendido`) para todos os processos criados;
  - sem essa parte, a importação falha com 400;
  - tudo numa só transação.

**Testes ajustados**

- `tests/database/test_tenant_schema.py`: a contagem de tabelas passou de 31
  para 33 (as duas tabelas novas).
- `tests/database/test_multitenant_mysql.py::test_migration_djen` agora sobe
  até a revisão do DJEN (`d3e4f5a6b7c8`), e não até `head`. O downgrade dele
  passaria pela migration nova. A migration nova tem teste próprio
  (`test_migration_processos_avulsos`).

**Front**

- `ProcessoForm` ganhou os props opcionais `salvar` (envio próprio, para
  `/api/processos`) e `extra` (seção de partes). O comportamento na tela do caso
  não mudou.
- A lista `/processos` usa o tipo local `PaginaProcessos`, que é a paginação
  plana devolvida pela API.
- O vínculo manual de publicação (`vincular-publicacao.svelte`) continua
  oferecendo só processos de caso. Para chegar a um processo sem caso, use a
  importação da busca por parte ou o casamento automático por número.

## Banco de exemplos

Decisões do responsável em 09/11/2026: guardar também as publicações **não
pertinentes**, com texto, por 2 anos, e usar os vínculos e descartes da rotina
e da caixa "Sem caso" como exemplos. Finalidade, retenção e acesso em
`docs/plano-djen.md`, §8.1.

**Modelo** (migration `b3c4d5e6f7a8`, sobre `f1a2b3c4d5e6`)

- Tabela nova `djen_exemplos`, separada de `djen_comunicacoes` para não poluir
  listas, caixa "Sem caso" e contagens. Uma linha por (`tenant_id`, `id_djen`),
  com `coluna_tenant()`, `unica_tenant_id` e FK composta para o usuário que
  rotulou. Sem `unidade_id`: o banco é do NPJ, não da unidade.
- Criada em utf8mb4 explícito (`mysql_charset`/`mysql_collate`), e não no
  latin1 das tabelas legadas: o texto vai sem `para_latin1`. O texto é o mesmo
  `djen_html.texto_plano` que as publicações gravam.
- O downgrade só apaga a tabela.

**Regras de rótulo** (upsert por `id_djen`, `DJENService._rotular`)

- Rótulo explícito (`pertinente`/`nao_pertinente`) sempre sobrescreve, e vale
  o mais recente: atualiza origem, quem rotulou, `rotulado_em`, texto e
  metadados, e zera `texto_apagado_em` (o prazo de 2 anos recomeça). O
  `termo_busca` só muda quando a nova origem traz um.
- `nao_revisada` só entra quando não há exemplo; nunca rebaixa nem renova.
- Busca por parte: "Importar selecionadas" grava as escolhidas como
  `pertinente` (`busca_parte`); `POST /api/djen/busca-parte/nao-pertinentes`
  (mesmo corpo, limites e papéis do importar, `PAPEIS_GESTAO`; reconsulta o
  DJEN) grava como `nao_pertinente` e não cria publicação nem processo. Nos
  dois, os demais itens da mesma consulta ainda sem exemplo entram como
  `nao_revisada`. O `termo_busca` é o primeiro nome da busca que trouxe a
  publicação.
- O vínculo feito pela importação não grava um segundo exemplo "automático":
  `registrar(..., exemplo=False)`.
- Rotina e caixa: todo vínculo passa por `_vincular`, que grava `pertinente`
  com origem `vinculo_manual` (com quem vinculou) ou `vinculo_automatico` (sem
  usuário). Isso inclui o casamento por número do botão "Buscar publicações
  agora" do processo. Descartar grava `nao_pertinente` (`descarte`); vincular
  uma descartada volta a `pertinente` (`vinculo_manual`). Tudo na mesma
  transação da ação.
- `GET /api/djen/busca-parte` devolve `rotulo` em cada item (ou nulo). A
  consulta não grava nada.

**Retenção** (`_aplicar_retencao`, fim de cada execução da rotina, por NPJ)

- `nao_revisada` com `criado_em` há mais de `DJEN_RETENCAO_DIAS` (90): apagada.
- Rotuladas com `rotulado_em` há mais de `DJEN_EXEMPLOS_RETENCAO_DIAS` (nova,
  padrão 730, em `.env.example`): `texto_plano` e `destinatarios` viram NULL e
  `texto_apagado_em` é preenchido.

**Acesso e exportação** (`PAPEIS_EXEMPLOS = ("admin",)`)

- `GET /api/djen/exemplos/resumo`: total, contagem por rótulo e por origem,
  quantos ainda têm texto e os dois prazos.
- `GET /api/djen/exemplos/exportar`: download `djen-exemplos-AAAA-MM-DD.jsonl`
  (`application/x-ndjson`), um exemplo por linha, só os rotulados;
  `incluir_nao_revisadas=1` inclui as não revisadas. Sem quem rotulou, sem ids
  internos.

**Front**

- `/djen/busca-parte`: botão "Marcar como não pertinentes (N)" ao lado de
  "Importar selecionadas", com a mesma seleção e os mesmos lotes de 100; selo
  "Pertinente"/"Não pertinente" por item. Item não pertinente continua
  marcável (não está no sistema), para importar se mudar de ideia.
- `/djen`: para o admin, o cartão "Banco de exemplos"
  (`lib/components/djen/banco-exemplos.svelte`), com as contagens e
  "Exportar (JSONL)".

**Testes ajustados**

- `tests/database/test_tenant_schema.py`: 33 → 34 tabelas.
- `tests/database/test_multitenant_mysql.py::test_migration_processos_avulsos`
  agora vai só até `f1a2b3c4d5e6`; a nova migration tem
  `test_migration_djen_exemplos`.
- `tests/api/djen_fixtures.py::limpar_djen` também limpa `djen_exemplos`.
