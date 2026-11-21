## Monitoramento unificado — implementação de 17/11/2026

Esta seção substitui horários, limites de processos e retenção descritos no histórico abaixo.

- Menu Monitoramento: OAB, Nome da Parte, Número do Processo e Logs de varredura.
- Busca avulsa e monitoramento são independentes; nomes exigem tribunais ao cadastrar.
- Todas as capturas, manuais ou automáticas, vinculam publicações a um único processo ativo do NPJ pelo CNJ. Isso inclui publicações reencontradas após cadastrar o processo. Casamento por nome/OAB não basta: o vínculo sempre usa o CNJ.
- Vínculos e descartes anteriores são preservados; a classificação humana não é sobrescrita. Sem processo correspondente, a publicação permanece para importação manual.
- Processo com caso gera evento e notificações; processo sem caso recebe o vínculo sem evento. Reconsultas não duplicam eventos.
- OAB/processo consultam todos os tribunais na rotina; manual permite período e tribunais.
- Na rotina, processo é consultado só por `numeroProcesso`, sem datas: a API devolve o histórico inteiro na mesma requisição que uma janela custaria. OAB e parte continuam em janelas de até 30 dias, que é limite nosso, não da API (20/11/2026).
- Todos os dias às 04h (hoje + 6 dias), 10h e 16h (hoje + 2 dias), America/Sao_Paulo.
- Processos ativos entram automaticamente. Pausa/remoção por item preserva o acervo.
- Admin vê o NPJ; demais gestores veem suas unidades. Consulta compartilhada por item/tribunal.
- Logs por 90 dias configuráveis. Associação publicação/unidade/origem é permanente.
- Migração 19e72ac50bd8 preserva consultas e transfere acessos antes de permitir a limpeza.
- Worker Docker dedicado; DJEN_SYNC_ENABLED continua sendo a chave explícita do ambiente.
- Sem caso fica como aba de Publicações. Busca por parte mantém a interface existente na aba correspondente.

# Plano — integração com o DJEN (Comunica PJe)

## Atualização implementada — acervo e classificação (2026-11-16)

Implementação local na branch `feat/multitenant`. Esta seção substitui as
regras antigas de retenção, exemplos e atualização automática de pendências
nas seções históricas abaixo. Nenhuma implantação em produção foi realizada.

- `djen_publicacoes`: conteúdo canônico, único por `(tenant_id, id_djen)`.
- `djen_comunicacoes`: situação operacional e vínculos; referencia o acervo,
  sem duplicar texto e metadados.
- `djen_classificacoes`: relevante, irrelevante ou não classificado; uma por
  publicação e NPJ, com origem, autor e data.
- `djen_classificacao_historico`: decisões anteriores, preservadas.
- `djen_consultas` e `djen_consulta_resultados`: origem, parâmetros, unidade,
  executor e resultado das capturas, com associação às publicações.

Cada página recebida de consultas por nome, OAB ou processo é persistida antes
da próxima chamada externa. Falhas posteriores não apagam páginas anteriores.
O limite de páginas é registrado como captura parcial. Consultas repetidas
atualizam os dados da fonte e vinculam pendências quando há um único processo
ativo com o mesmo CNJ. A regra vale para todas as origens, manuais ou automáticas,
inclusive para publicações reencontradas após cadastrar o processo. Não apaga
rótulos humanos, não reabre descartes e não duplica vínculos ou eventos.
Cancelamentos da fonte continuam sendo atualizados.

A tela `/djen` mostra o acervo para os perfis de gestão (admin, prof, orient),
com filtros e seleção. Importar usa o conteúdo salvo, cria os vínculos e marca
como relevante. Descartar marca como irrelevante na mesma transação. Um lote
com item inválido é recusado integralmente. Publicações já vinculadas não são
descartadas. Os demais perfis mantêm a leitura operacional restrita já existente.

A tela `/djen/classificacao` abre em não classificado, permite leitura do texto,
consulta ao histórico e classificação individual ou em lote. Ela não altera
vínculos. Classificar como irrelevante uma publicação já importada também não
remove o vínculo; é uma decisão de treino separada. A importação explícita
posterior pode torná-la relevante novamente, com histórico.

Nenhuma ausência de seleção equivale a avaliação negativa. Não há exclusão
automática por idade ou falta de classificação. A exportação JSONL usa somente
rótulos explícitos por padrão e é lida em lotes de 500, transmitida em streaming
com o tenant autenticado restaurado por chunk. A inclusão de não classificados
é opcional e eles não são exemplos negativos.

O acervo é por NPJ; o acesso exige uma consulta de origem ou comunicação na
unidade ativa. Todas as associações possuem FKs compostas por tenant. Índices
cobrem identificação externa, data, processo, rótulo e associações de consulta.
Elasticsearch e a futura busca FULLTEXT não fazem parte desta entrega.

A revisão experimental `b3c4d5e6f7a8` foi refeita, sem conversão de dados da
tabela antiga `djen_exemplos`. Ela recria comunicações e cria o acervo. Eventos
existentes são preservados, retirando apenas a referência à comunicação
experimental. O downgrade também é descartável. Em um banco local que já tinha
a versão anterior dessa revisão, é necessário remover `djen_exemplos`, voltar
apenas o marcador para `f1a2b3c4d5e6` e reaplicar a revisão, após backup. Não
executar esse procedimento como atualização genérica de ambientes publicados.

## Planejamento histórico

## Resultado esperado

O sistema captura do Diário de Justiça Eletrônico Nacional (DJEN) as
publicações dos processos de cada NPJ (tenant) e:

1. mostra todas elas num menu **DJEN**, com filtros e uma caixa de
   publicações ainda sem caso;
2. cria um **evento** no caso do processo, marcado como vindo do DJEN para
   não se confundir com os eventos cadastrados à mão;
3. **notifica** orientador, estagiário e colaborador do caso de que saiu
   publicação nova.

Fora do escopo desta primeira entrega:
- movimentações processuais que não são publicadas (DataJud);
- cálculo de prazo;
- envio de e-mail.

Esses três itens estão na fase 4.

## 1. O que a API oferece (testado em 2026-11-06)

`GET https://comunicaapi.pje.jus.br/api/v1/comunicacao?<filtros>`

- Pública: não pede autenticação. CORS liberado (`*`). Não há documentação
  oficial de contrato nem compromisso de disponibilidade; tratar como
  instável.
- Limite de taxa: `x-ratelimit-limit: 20`. O contador voltou ao máximo em
  menos de um minuto. O cliente precisa ler `x-ratelimit-remaining` e esperar
  quando chegar perto de zero.
- `cache-control: max-age=120`. Repetir a mesma consulta em menos de dois
  minutos não traz nada novo.

| Filtro | Exemplo testado | Resultado |
|---|---|---|
| `numeroProcesso` (20 dígitos, sem máscara) | `10064304820268130471` | Histórico completo do processo, sem precisar de datas |
| `numeroOab` + `ufOab` + período | `108825`/`MG`, 01–06/11 | 162 publicações |
| `nomeParte` + período | "Universidade Federal de Minas Gerais", 1 mês | 560, com muito ruído |
| `siglaTribunal` + período | `TJMG`, 1 dia | `count` para em 10000 |

- Datas: `dataDisponibilizacaoInicio` e `dataDisponibilizacaoFim`, no formato
  `AAAA-MM-DD`.
- Paginação: `pagina` e `itensPorPagina`. O teste aceitou 500 por página, mas
  o cliente deve paginar mesmo assim.
- Certidão: `GET /api/v1/comunicacao/{hash}/certidao` devolve um PDF.

Campos de cada item que vamos usar:

| Campo | Uso |
|---|---|
| `id` | Chave de deduplicação (`id_djen`) |
| `hash` | Link da certidão |
| `data_disponibilizacao` | Data do evento |
| `siglaTribunal`, `nomeOrgao`, `idOrgao` | Tribunal e vara |
| `tipoComunicacao`, `tipoDocumento` | Tipo do evento (Intimação, Edital, Lista de distribuição…) |
| `numero_processo`, `numeroprocessocommascara` | Casamento com `processos` |
| `nomeClasse`, `codigoClasse` | Exibição |
| `texto` | Conteúdo integral, **em HTML com entidades** |
| `link` | Documento no sistema do tribunal |
| `destinatarios[]` (`nome`, `polo` A/P) | Exibição e busca |
| `destinatarioadvogados[].advogado` (`nome`, `numero_oab`, `uf_oab`) | Saber por qual OAB a publicação chegou |
| `ativo`, `status`, `motivo_cancelamento`, `data_cancelamento` | Publicação cancelada |

## 2. Estratégia de captura

**Por OAB (rotina diária).** Para cada OAB monitorada, buscar a janela dos
últimos 3 dias e casar cada publicação pelo número do processo. Repetir 3
dias de janela cobre execuções que falharam e publicações que chegaram
atrasadas. Como a gravação é idempotente pelo `id_djen`, buscar de novo não
duplica nada. São poucas requisições: uma por OAB por página.

**Por número do processo (histórico).** Usado quando um processo é cadastrado
ou tem o número alterado, e pelo botão "Buscar publicações agora" na tela do
processo.
- O cadastro não chama a API na hora: só marca o processo como pendente
  (`djen_pendente`).
- A rotina atende até N processos pendentes por execução, respeitando o
  limite de taxa.
- O botão faz uma única requisição, sem esperar a rotina.

**Por nome da parte: não entra na captura automática.** Tem homônimos e muito
ruído, e traria dados de pessoas sem relação com a DAJ. Se fizer falta, vira
uma busca manual na fase 4, sem gravar nada.

Buscar processo por processo todos os dias não escala: 500 processos ativos
levariam uns 25 minutos por causa do limite.

## 3. Banco de dados

Migration nova, com `down_revision = "c2d3e4f5a6b7"` (M3 do multitenant).
Revisão humana; conferir `alembic -c migrations/alembic.ini heads` antes do PR.

### 3.1 Regras do multitenant que o DJEN segue

Valem para tudo abaixo (detalhes em `docs/plano-multitenant.md`):

- **Coluna e FKs.** As três tabelas novas recebem `coluna_tenant()`, e não
  entram em `TABELAS_GLOBAIS`. Toda FK para tabela de tenant (`casos`,
  `processos`, `usuarios`, `unidades`, `eventos`, `djen_*`) é composta,
  declarada com `fk_tenant(...)`, e toda tabela referenciada ganha
  `unica_tenant_id(...)`. Os testes estruturais
  (`tests/database/test_tenant_schema.py`, `test_fk_composta.py`) falham se
  isso faltar.
- **Unicidades por tenant.** `djen_oabs (tenant_id, numero_oab, uf_oab)` e
  `djen_comunicacoes (tenant_id, id_djen)`: uma OAB cadastrada em dois NPJs
  recebe a mesma publicação nos dois, como registros separados.
  `eventos.id_djen_comunicacao` continua `UNIQUE` (aponta para o id local).
- **Repositórios.** Toda consulta passa por `self.escopo(...)` e todo INSERT
  por `self.valores(...)`, como os 21 repositórios atuais. `text()` e
  `.execute()` fora de `gestaolegal/repositories/` são barrados pelo lint de
  `tests/api/test_tenant_guarda.py`; a guarda de execução recusa em runtime
  qualquer consulta a tabela de tenant sem critério de tenant.
- **Casamento dentro do tenant.** `processos.numero_cnj` é casado só com
  processos do mesmo tenant da publicação.
- **Ids referenciados** (`processo_id` no vínculo, `id_usuario` e `unidade_id`
  da OAB) são conferidos no repositório antes de gravar, com 400 genérico,
  como em `gestaolegal/services/referencias.py`.
- **Rotas novas** entram classificadas em `ROTAS` de
  `tests/api/test_tenant_vazamento.py`; sem isso a suíte falha. A varredura
  passa então a provar que um NPJ não vê publicações do outro.

### 3.2 Chave do DJEN por NPJ

Duas chaves, em camadas. A captura só roda para um NPJ com as duas ligadas.

| Chave | Onde | Quem controla | Para quê |
|---|---|---|---|
| `DJEN_SYNC_ENABLED` | `.env` do servidor | quem implanta | Trava do ambiente: em QA e demo fica desligada, para não gerar notificações reais por engano |
| `tenants.djen_ativo` | banco; interruptor na área da plataforma | admin da plataforma | Liga o DJEN por NPJ |

Com `djen_ativo` desligado:
- a rotina pula o NPJ e registra o motivo no log, sem gravar linha em
  `djen_sincronizacoes`;
- o menu DJEN não aparece, e as rotas `/api/djen/*` e
  `/api/processos/<id>/djen/buscar` respondem 403;
- nada é apagado: publicações já capturadas ficam no banco, e os eventos DJEN
  já vinculados continuam visíveis no caso. Religar retoma a captura de onde
  parou.

Uma tabela genérica de recursos e limites por NPJ fica para a fase futura
prevista no plano do multitenant. Se outros recursos opcionais surgirem, esta
coluna migra para lá.

### `tenants`
- `djen_ativo BOOLEAN NOT NULL DEFAULT 0`: liga o DJEN para o NPJ (seção
  3.2). Todos os NPJs começam desligados, inclusive a DAJ.

### `processos`
- `numero_cnj CHAR(20) NULL`, com índice: só os dígitos de `numero`, quando
  tiver exatamente 20. É preenchido pelo service ao salvar e calculado para os
  registros existentes na própria migration. Números antigos fora do padrão
  CNJ ficam nulos e não são casados. A migration informa quantos ficaram assim.
- `djen_pendente BOOLEAN NOT NULL DEFAULT 0` e `djen_consultado_em DATETIME
  NULL`.

### `djen_oabs` (nova)

Lista das OABs monitoradas, mantida pelo admin.

| Coluna | Observação |
|---|---|
| `id` | PK |
| `numero_oab` | Só dígitos |
| `uf_oab` | `CHAR(2)` |
| `id_usuario` | FK nula; dono da OAB, quando for alguém do sistema |
| `unidade_id` | `coluna_unidade()`: unidade das publicações que chegarem sem caso |
| `ativo` | Boolean |
| `criado_em`, `id_criado_por` | Controle |

Unicidade: (`numero_oab`, `uf_oab`). Na tela de cadastro, o `usuarios.oab` dos
orientadores aparece só como sugestão, porque é texto livre.

### `djen_comunicacoes` (nova)

| Coluna | Observação |
|---|---|
| `id` | PK |
| `id_djen` | `BIGINT UNIQUE`; o `id` da API |
| `hash` | Para a certidão |
| `numero_processo` | 20 dígitos, indexado |
| `data_disponibilizacao` | `DATE`, indexada |
| `sigla_tribunal`, `nome_orgao`, `tipo_comunicacao`, `tipo_documento`, `nome_classe` | Texto |
| `texto_html` | `MEDIUMTEXT`, original da API |
| `texto_plano` | Texto sem tags, para resumo e busca |
| `link` | `String(1000)` |
| `destinatarios`, `advogados` | JSON |
| `ativo` | Boolean; falso quando a publicação foi cancelada |
| `motivo_cancelamento` | Texto |
| `id_processo`, `id_caso` | FKs; nulos enquanto não houver vínculo |
| `situacao` | `vinculada`, `pendente` ou `descartada` |
| `unidade_id` | `coluna_unidade()`, sem default: passar sempre |
| `capturada_em`, `atualizada_em` | Datas de controle |
| `id_vinculado_por` | Quem vinculou ou descartou à mão |

A unidade vem do caso. Sem caso, vem da `unidade_id` da OAB em `djen_oabs`
por onde a publicação chegou.

### `djen_sincronizacoes` (nova)

Registro de cada execução:
- início, fim, `status` (`ok`, `parcial` ou `erro`) e parâmetros;
- contagem de publicações novas, atualizadas e vinculadas;
- mensagem de erro.

A tela usa esse registro para mostrar "última sincronização" e saber se a
rotina parou.

### `eventos`
- `origem VARCHAR(10) NOT NULL DEFAULT 'manual'`, com os valores `manual` e
  `djen`.
- `id_djen_comunicacao` FK nula, `UNIQUE`: no máximo um evento por
  publicação.
- `id_criado_por` passa a aceitar nulo, apenas para `origem='djen'`.
  Criar um usuário "sistema" foi descartado: `usuarios` exige CPF, RG e
  nascimento, e esse usuário apareceria nas listas e nos relatórios.

### `notificacao`
`tipo` ganha o valor `djen` (`TipoNotificacao`). Não precisa de coluna nova:
`id_caso`, `id_referencia` (o id do evento) e `detalhe` bastam.

## 4. Backend

**Cliente** (`gestaolegal/integrations/djen_client.py`):
- usa `urllib.request` da biblioteca padrão, sem dependência nova, atrás de uma
  função de transporte que os testes substituem;
- timeout de 30 s, `User-Agent` genérico do sistema e paginação;
- respeita o limite de taxa: espera quando `x-ratelimit-remaining` ≤ 1 e
  reage a 429 com backoff;
- devolve dataclasses e nunca toca no banco.

**Service** (`gestaolegal/services/djen_service.py`):
- `sincronizar(janela_dias=3, max_processos=15)`: busca pelas OABs ativas de `djen_oabs`, depois os
  processos pendentes, e grava em `djen_sincronizacoes`;
- `registrar(item)`: faz upsert por `id_djen`. Se a publicação já existe,
  atualiza `ativo` e o cancelamento;
- `vincular(comunicacao, processo)`: grava o vínculo, cria o evento e notifica
  na mesma transação, como `EventoService.create` já faz;
- `descartar(comunicacao, usuario)`: para publicações que não são do NPJ;
- casamento automático: `numero_processo` igual a `processos.numero_cnj` e
  processo ativo.

Pontos que diferem do fluxo de requisição:
- A rotina roda **sem request**: não há tenant nem unidade ativos. O comando
  lista os tenants ativos dentro de `sem_tenant("djen: listar NPJs ativos")` e
  processa **um de cada vez** dentro de `contexto_tenant(id)`. Só entram os
  NPJs com `djen_ativo` ligado (seção 3.2). Cada tenant
  grava sua própria linha em `djen_sincronizacoes`; a falha de um não
  interrompe os outros. NPJ inativo é pulado. `--tenant SLUG` roda um só.
- Dentro do tenant, `RequestContext.get_unidade_ativa()` também não existe: o
  service recebe a unidade explicitamente, e todo INSERT passa `unidade_id`.
- `NotificacaoService.notificar` hoje recebe `executor_id: int` e pula o
  destinatário que for igual ao executor. Na rotina, o executor é `None`. Já
  num vínculo manual, quem vinculou não recebe a notificação.
- Publicação cancelada depois do vínculo: o evento continua, com um selo de
  "cancelada" (lido de `djen_comunicacoes.ativo`), e o caso recebe outra
  notificação. Nada é apagado.

**Evento criado a partir da publicação:**
- `tipo`: `tipoComunicacao`;
- `data_evento`: `data_disponibilizacao`;
- `descricao`: órgão, classe e os primeiros cerca de 500 caracteres do
  `texto_plano`;
- `num_evento`: o próximo número do caso;
- `id_usuario_responsavel`: o estagiário do caso, ou o orientador se não
  houver estagiário;
- `origem`: `djen`.

**HTML:**
- A resposta da API é JSON, mas o campo `texto` vem com um documento HTML
  dentro: com `<!DOCTYPE>`, `<head>`, `<style>` e acentos em entidades
  (`&ccedil;`). Foi assim em 5 de 5 publicações do TRF6 (06/11) e em 79 de 100
  do TJMG; as outras vieram em texto simples.
- `texto_html` é conteúdo de terceiros.
- `head`, `style` e `script` são removidos **com o conteúdo**
  (`clean_content_tags` do `nh3`). Sem isso, o CSS da publicação mudaria a
  fonte e o espaçamento da nossa página.
- `texto_plano` é gerado com `html.parser` da biblioteca padrão (tags fora,
  entidades convertidas) e serve para o resumo do evento e para a busca.
- A API devolve um `texto_html_seguro`, limpo no backend com `nh3` (dependência
  nova) numa lista restrita de tags (`p`, `b`, `strong`, `i`, `u`, `br`,
  `table`, `tr`, `td`, `section`, `span`), sem atributos.
- O front só usa `{@html}` com esse campo, nunca com o original.

**Agendamento.** O sistema não tem agendador hoje.
- Criar o comando `flask djen sincronizar`, que também pode ser chamado por
  `scripts/sincronizar_djen.py`.
- Ele roda com `docker compose run --rm api ...`, por cron no host, em dias
  úteis (segunda a sexta) às 8h e às 14h, com `flock` para não sobrepor
  execuções. Feriados não são tratados: a execução só não encontra nada.
- O cron não é instalado por script; fica documentado no README, como no reset
  de demo.

**Configuração** (documentar em `.env.example`):
- `DJEN_API_URL` (padrão: a URL pública);
- `DJEN_SYNC_ENABLED` (padrão `false`);
- `DJEN_JANELA_DIAS` (padrão `3`).

Com `DJEN_SYNC_ENABLED` desligado, o comando sai sem fazer nada. Isso protege
QA e demo de gerar notificações para usuários reais por engano. Ligar em QA ou
produção exige decisão explícita.

## 5. Contrato da API (revisão humana: `web/src/lib/types` e `api-client.ts`)

| Método | Rota | Uso |
|---|---|---|
| GET | `/api/djen/publicacoes` | Lista. Filtros: `inicio`, `fim`, `tribunal`, `tipo`, `oab`, `situacao`, `caso_id`, `q` (texto) e paginação |
| GET | `/api/djen/publicacoes/<id>` | Detalhe com `texto_html_seguro`, links do tribunal e da certidão |
| POST | `/api/djen/publicacoes/<id>/vincular` | `{processo_id}`: cria o evento e notifica |
| POST | `/api/djen/publicacoes/<id>/descartar` | Marca como não pertencente ao NPJ |
| POST | `/api/processos/<id>/djen/buscar` | Busca imediata do histórico do processo |
| GET | `/api/djen/status` | Última sincronização e resultado |

Todas as rotas filtram por unidade e respondem 403 se o NPJ estiver com o
DJEN desligado. A certidão usa o link público direto; não há proxy.

Mudanças em rotas que já existem:

| Rota | Mudança |
|---|---|
| `GET /api/user/me` | `tenant` ganha `djen_ativo`, que o front usa para mostrar o menu |
| `GET`/`PUT /api/plataforma/tenants/<id>` e `GET /api/plataforma/tenants` | passam a ler e gravar `djen_ativo` |

## 6. Frontend

- **Menu "DJEN"** no `app-sidebar.svelte`, com os subitens "Publicações" e
  "Sem caso". Só aparece se `tenant.djen_ativo`. O "Sem caso" só aparece para
  os papéis que podem vincular.
- **Área da plataforma:** interruptor "Busca no DJEN" na edição do NPJ e
  coluna na lista de NPJs.
- **Lista:** data, tribunal, vara, tipo, processo com máscara, caso (link) e
  situação. Os filtros ficam na URL, no mesmo padrão adotado na lista de
  casos em `b8f2f8d`. No topo, aviso de "Última sincronização: …", com alerta
  se tiver mais de 2 dias úteis.
- **Detalhe:** texto limpo, destinatários por polo, advogados, links e o
  botão "Vincular a processo" (busca por número ou por caso) ou "Descartar".
- **Caso, lista de eventos:**
  - selo "DJEN" e filtro por origem;
  - o evento do DJEN abre o detalhe da publicação;
  - os campos vindos da publicação (`tipo`, `data_evento`, `descricao`) não
    são editáveis; responsável e anexos continuam editáveis.
- **Processo:** botão "Buscar publicações agora" e a data da última consulta.
- **Notificações:** o tipo `djen` leva ao evento no caso.

## 7. Permissões (decidido em 2026-11-06)

| Papel | Lista geral | Sem caso | Vincular/descartar | Eventos DJEN no caso |
|---|---|---|---|---|
| `admin`, `prof`, `orient` | Toda a unidade | Sim | Sim | Sim |
| `colab_proj` | Toda a unidade | Não | Não | Sim |
| `estag_direito`, `colab_ext` | Só casos de que participam | Não | Não | Sim, nos casos que já veem |

## 8. Dados pessoais e retenção

- As publicações são públicas, mas trazem nomes de terceiros.
- Em `djen_comunicacoes` só gravamos o que chega pelas OABs monitoradas, pelos
  processos cadastrados ou pela importação manual da busca por parte. Nada de
  captura ampla por tribunal ou por parte.
- Publicações `descartadas`, e as `pendentes` sem vínculo há mais de 90 dias,
  são apagadas pela própria rotina. O prazo conta a partir de `capturada_em`
  (pendentes) ou da data do descarte (descartadas).
- As vinculadas seguem a vida do caso.

### 8.1 Banco de exemplos (decidido em 09/11/2026)

Finalidade nova, distinta do acompanhamento dos processos: **treinar um
classificador** (regressão logística, no futuro) que sugira se uma publicação é
pertinente ao NPJ. Para isso o sistema guarda exemplos rotulados também das
publicações **não pertinentes**, inclusive das vistas na busca por parte, numa
tabela separada (`djen_exemplos`), que não aparece nas listas, na caixa "Sem
caso" nem nas contagens.

- **O que é guardado**: `id_djen`, número do processo, data, tribunal, órgão,
  classe, tipo de comunicação e de documento, destinatários (nomes e polo),
  texto plano da publicação (sem HTML), o nome buscado (busca por parte), o
  rótulo (`pertinente`, `nao_pertinente`, `nao_revisada`), a origem (busca por
  parte, vínculo manual, vínculo automático, descarte), quem rotulou e quando.
  Sem vínculo com atendido.
- **De onde vem**: importar uma publicação da busca por parte (pertinente) ou
  marcá-la como não pertinente; os demais itens da mesma consulta entram como
  "não revisada". Na rotina e na caixa "Sem caso": vínculo manual ou automático
  (pertinente) e descarte (não pertinente). A consulta da busca por parte, em
  si, continua sem gravar nada; pendentes não viram exemplo até alguém agir.
- **Por quanto tempo**: as "não revisadas" são apagadas inteiras em 90 dias
  (`DJEN_RETENCAO_DIAS`, contados da criação). Nas rotuladas, o texto e os
  destinatários são anulados depois de 2 anos (`DJEN_EXEMPLOS_RETENCAO_DIAS`,
  padrão 730, contados do rótulo); rótulo e metadados ficam. A limpeza roda no
  fim de cada execução da rotina, por NPJ. Rotular de novo renova o texto e o
  prazo.
- **Quem acessa**: só o `admin` do NPJ vê as contagens e exporta o arquivo
  (JSON Lines). O arquivo exportado não traz quem rotulou nem ids internos e
  deve ser tratado como dado pessoal de terceiros (nomes de partes): guardar
  só onde o treino roda e apagar depois.

## 9. Testes

Sem rede nos testes: o cliente recebe um transporte falso e fixtures JSON
sintéticas, montadas a partir da estrutura real, com nomes fictícios.

- Normalização de `numero_cnj`: máscara, espaços, números fora do padrão.
- Upsert idempotente: o mesmo `id_djen` duas vezes não cria nada novo.
  Cancelamento atualiza o registro e notifica.
- Casamento automático: cria um evento só e notifica os participantes certos,
  sem repetir; processo inativo não casa.
- Unidade: INSERT da rotina sem request grava a unidade do caso; publicação
  sem caso fica com a unidade do dono da OAB.
- Limite de taxa: espera com `remaining` baixo; 429 faz backoff; erro de rede
  gera sincronização `parcial` ou `erro`, sem perder o que já foi gravado.
- Sanitização: `<script>`, `onerror` e `javascript:` não sobrevivem em
  `texto_html_seguro`.
- Permissões por papel e por unidade em todas as rotas da seção 5.
- Tenant: a mesma publicação capturada em dois NPJs vira dois registros; o
  casamento não cruza NPJs; a rotina processa cada tenant ativo no seu
  contexto, pula os inativos e segue quando um falha; as rotas novas entram na
  varredura de vazamento.
- `DJEN_SYNC_ENABLED=false` sai sem chamar a API.
- `djen_ativo` desligado: a rotina pula o NPJ sem chamar a API; rotas DJEN dão
  403; o menu some; publicações e eventos já gravados continuam. Só o admin da
  plataforma altera a chave; token de NPJ não consegue.
- Evento DJEN: campos travados no update; eventos manuais não mudam.

## 10. Fases e PRs

1. **Captura e lista.**
   - Migration (`tenants.djen_ativo`, `processos.numero_cnj`,
     `djen_comunicacoes`, `djen_sincronizacoes`).
   - Interruptor por NPJ na área da plataforma (seção 3.2).
   - Cliente, service, comando `flask djen sincronizar` e busca por número do
     processo.
   - Rotas de leitura e menu DJEN só com a lista e o detalhe.
2. **Eventos e notificações.** Colunas novas em `eventos`, vínculo automático
   e manual, selo no caso, tipo de notificação `djen` e campos travados.
3. **Captura por OAB.** Tela de cadastro de `djen_oabs` (admin), caixa "Sem caso",
   descarte, retenção e cron documentado no README.
4. **Extras, se decidirem:**
   - sugestão de prazo, com calendário de feriados por tribunal;
   - e-mail (exige decisão: o envio é real);
   - movimentações via DataJud (API do CNJ, com chave pública);
   - busca manual por parte.

## Decisões

Tomadas em 2026-11-06 e 2026-11-07:

1. **OABs monitoradas:** lista própria (`djen_oabs`), mantida pelo admin.
   O `usuarios.oab` serve só como sugestão.
2. **Permissões:** a tabela da seção 7.
3. **Rotina:** dias úteis, às 8h e às 14h, com janela de 3 dias.
4. **Retenção:** 90 dias para publicações descartadas e para pendentes sem
   caso.
5. **Dependências:** `nh3` para filtrar o HTML do campo `texto` (mantém
   negrito, parágrafos e tabelas) e `urllib` da biblioteca padrão para chamar a
   API, sem `httpx`. Decidido em 2026-11-07.
6. **Chave por NPJ:** `tenants.djen_ativo`, ligada pelo admin da plataforma,
   começando desligada para todos; `DJEN_SYNC_ENABLED` continua como trava do
   ambiente. Decidido em 2026-11-08.

## Pendências para revisão

Escolhas feitas na implementação das fases 1 a 3 (branch `feat/djen`) onde o
plano não decidia, sempre pelo caminho mais conservador. Revisar antes do merge.

**Migration (`d3e4f5a6b7c8_djen.py`, única, `down_revision = c2d3e4f5a6b7`)**

1. Uma migration só, editada a cada fase: os commits intermediários não são
   pontos de deploy. Se as fases forem para produção em separado, ela precisa
   ser dividida.
2. Processos existentes **não** são marcados `djen_pendente`: o histórico deles
   só é buscado pelo botão da tela do processo ou depois de uma alteração do
   número. Marcar todos faria a primeira execução da rotina consultar centenas
   de processos e gerar uma onda de eventos e notificações antigas.
3. Colunas além das listadas no §3: `djen_comunicacoes.numero_processo_mascara`,
   `data_situacao` (data do vínculo ou do descarte, usada na retenção) e
   `oab_origem` (`numero/UF` da OAB por onde chegou, para o filtro `oab` e para
   a tela de detalhe).
4. `eventos`: a unicidade é `(tenant_id, id_djen_comunicacao)`, e não só a
   coluna, por causa da regra de unicidade por tenant do teste estrutural.
5. O downgrade recusa (RuntimeError) quando existem eventos do DJEN: sem a
   coluna `origem`, eles virariam eventos manuais sem autor e `id_criado_por`
   não voltaria a `NOT NULL`. Apagar eventos fica para decisão humana.
6. `djen_oabs.uf_oab` é `VARCHAR(2)`, não `CHAR(2)`, como as demais colunas de
   UF do esquema; a validação aceita só as 27 UFs.
7. `scripts/seed_database.py` passou a inserir só as colunas que existem na
   tabela (`Seed._colunas`), para o teste MySQL semear o banco numa revisão
   anterior à do DJEN.

**Permissões e escopo**

8. `colab_proj`, `estag_direito` e `colab_ext` veem só publicações
   **vinculadas** (o §7 diz "toda a unidade" para `colab_proj`, mas a caixa
   "Sem caso" é só de quem vincula; pendentes e descartadas ficam fora da lista
   geral desses papéis).
9. O botão "Buscar publicações agora" (`POST /processos/<id>/djen/buscar`) é
   só de `admin`, `prof` e `orient`: ele cria eventos e dispara notificações.
10. OABs monitoradas: só `admin` do NPJ. A lista e a edição são filtradas pela
    unidade ativa (a OAB de outra unidade dá 404); no cadastro, `unidade_id` é
    a unidade ativa ou outra unidade do próprio admin. A rotina consulta as
    OABs ativas de todas as unidades do NPJ. `DELETE` apaga o cadastro (as
    publicações capturadas ficam); para só pausar, `PUT {ativo: false}`.
11. Sugestões de OAB: `usuarios.oab` de `orient`, `prof` e `admin` ativos da
    unidade ativa, só quando o texto livre tem número e UF reconhecíveis.
12. Publicação descartada ainda pode ser vinculada manualmente (desfaz o
    descarte). A rotina não revincula sozinha uma descartada, mesmo que depois
    apareça um processo com o número dela.

**Comportamento**

13. Notificações agregadas: uma por caso a cada fonte da rotina (OAB ou
    processo), com "N novas publicações…", em vez de uma por publicação.
14. No evento do DJEN, `id_caso` também é travado, além de `tipo`,
    `data_evento` e `descricao`. Enviar um desses campos com valor diferente
    dá 400 com o campo; o mesmo valor é aceito e ignorado.
15. Status "atrasada" também quando nunca houve sincronização.
16. DJEN fora do ar no botão do processo: 422 com código `DJEN_INDISPONIVEL`,
    sem gravar nada.
17. A janela da busca por OAB vai de `hoje − DJEN_JANELA_DIAS` até hoje
    (inclusive), um dia a mais que "os últimos 3 dias", para não perder a
    borda.
18. Retenção: roda no fim de cada execução da rotina, só no NPJ da execução;
    uma falha nela não muda o status da sincronização (fica no log e é
    refeita na próxima). Prazo de 90 dias fixo (`Config.DJEN_RETENCAO_DIAS`),
    sem variável de ambiente.

**Testes existentes adaptados (nenhuma asserção removida ou afrouxada)**

19. `tests/database/test_tenant_schema.py`: contagem de tabelas de tenant de 28
    para 31 (as três do DJEN).
20. `tests/database/test_tenants_migration.py`: `tenants.djen_ativo` entra em
    `COLUNAS_POSTERIORES`, fora da comparação com a M1, e é conferida na
    migration do DJEN.
21. `tests/api/test_jwt_tenant.py`: o dicionário esperado do tenant ganhou
    `"djen_ativo": False`.

### Buscas manuais em lote e histórico completo

- Nas abas OAB, Nome da Parte e Número do Processo, **Buscar todos** consulta
  sequencialmente os itens ativos da aba, nas unidades listadas, usando uma cópia
  do período e tribunais selecionados. Pausados ficam fora do lote. O progresso
  identifica o item atual; uma falha não impede a consulta dos seguintes, e o
  resultado informa consultas incompletas.
- Para um número CNJ, **Buscar todas as publicações** consulta o histórico
  disponível sem filtro de datas ou tribunal e percorre todas as páginas. A ação
  está no formulário e nas linhas de processos monitorados, e também nos
  detalhes do processo. As páginas já recebidas permanecem no acervo em caso
  de falha; reconsultas preservam classificações e vínculos.
- O CNJ monitorado abre os detalhes quando há um único processo correspondente
  no mesmo NPJ e unidade. Sem cadastro correspondente, continua como texto.
  Abrir o link seleciona a unidade do processo.

### Contextos de classificação e sugestões — 17/11/2026

A operação usa **não analisado**, **importado** e **descartado**. Os valores
internos `nao_importada`/`pendente`, `vinculada` e `descartada` continuam
compatíveis com processos e eventos. Relevância pertence ao treino, por contexto.

Em **Acervo para treino**, criar um contexto com nome livre, variações do nome da
parte (separadas por ponto e vírgula) e tribunais (vazio significa todos).
O contexto pertence ao NPJ e à unidade ativa. Os nomes são comparados com os
**destinatários estruturados**, ignorando caixa e acentos; não com o texto inteiro.
Os filtros do contexto são fixados na criação. Para outra finalidade/filtro,
criar outro contexto evita misturar exemplos já avaliados.

A migration `27f86bd31ac9` acrescenta `djen_contextos`,
`djen_publicacao_contextos`, `djen_contexto_historico` e `djen_modelos`.
A relação publicação–contexto é única por NPJ e contém o rótulo, sua origem,
autor, data e última sugestão/versionamento. Conteúdo não é duplicado.
As tabelas anteriores de classificação permanecem para compatibilidade e auditoria,
identificadas como legado nos detalhes; **não alimentam os modelos novos**.

- Criar contexto inclui publicações já capturadas compatíveis com seus filtros.
- Novas capturas também passam a integrar os contextos compatíveis.
- Publicações anteriormente importadas/descartadas recebem rótulos iniciais
  relevante/irrelevante. Importação automática também rotula.
- A avaliação manual no treino tem prioridade e não é sobrescrita pela operação.
- Na lista operacional, um contexto selecionado recebe a avaliação da operação.
  Em “Todos os contextos”, o usuário marca quais contextos avaliar. Sem marcar
  nenhum, a ação apenas importa/descarta. Contextos não escolhidos ficam intactos,
  inclusive na próxima captura.
- As ações operacionais nas telas antigas de busca e detalhe não avaliam contextos;
  para isso usar a lista filtrada ou a tela de treino.
- Classificar no treino nunca importa, descarta, cria processos ou eventos.

O filtro **Contexto de classificação** mantém uma publicação por linha.
Cada contexto mostra sua sugestão, identificando a versão do modelo; divergências
são destacadas. O filtro **Sugestão do modelo** é separado da situação operacional.
Previsões não alteram rótulos. Ao avaliar, o histórico conserva a sugestão e a
versão do modelo disponíveis naquele momento.

O botão **Treinar modelo experimental** usa TF-IDF + regressão logística por
contexto. Exige 200 exemplos rotulados, pelo menos 50 de cada classe e 10 processos
distintos. “Não analisado” é excluído. A avaliação separa treino/teste por CNJ,
sem aprender o vocabulário do teste; exige ambas as classes nas duas partições.
São apresentados precisão, revocação e F1. O artefato final usa os exemplos
rotulados disponíveis; armazena vocabulário, IDF, coeficientes, intercepto,
amostra de treinamento e métricas em JSON, sem desserialização de pickle.
O modelo mais recente fornece sugestões experimentais às publicações não
analisadas, sem ações automáticas. Novo treino depende de clique explícito.
As métricas incluem rótulos operacionais e não substituem uma avaliação humana
independente. LightGBM não faz parte desta primeira implementação.

A imagem Python usa Debian slim para instalar as dependências científicas
pré-compiladas. O lockfile inclui scikit-learn, NumPy e SciPy.
