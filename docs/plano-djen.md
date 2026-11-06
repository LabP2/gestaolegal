# Plano — integração com o DJEN (Comunica PJe)

Base: `master` em `b8f2f8d`, branch `feat/djen`. Este documento só traz o
planejamento: nada foi implementado nem migrado.

## Resultado esperado

O sistema captura do Diário de Justiça Eletrônico Nacional (DJEN) as
publicações dos processos da DAJ e:

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

Migration nova (revisão humana; conferir `alembic -c migrations/alembic.ini
heads` antes do PR).

### `processos`
- `numero_cnj CHAR(20) NULL`, com índice: só os dígitos de `numero`, quando
  tiver exatamente 20. É preenchido pelo service ao salvar e calculado para os
  registros existentes na própria migration. Números antigos fora do padrão
  CNJ ficam nulos e não são casados. A migration informa quantos ficaram assim.
- `djen_pendente BOOLEAN NOT NULL DEFAULT 0` e `djen_consultado_em DATETIME
  NULL`.

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

A unidade vem do caso. Sem caso, vem da unidade do dono da OAB, quando ele
tiver uma só. Se tiver várias, a publicação fica em `pendente` na primeira
unidade dele e o admin pode mudar.

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
- usa `urllib` da biblioteca padrão, ou `httpx` como dependência nova;
- timeout de 30 s, `User-Agent` genérico do sistema e paginação;
- respeita o limite de taxa: espera quando `x-ratelimit-remaining` ≤ 1 e
  reage a 429 com backoff;
- devolve dataclasses e nunca toca no banco.

**Service** (`gestaolegal/services/djen_service.py`):
- `sincronizar(janela_dias=3, max_processos=15)`: busca por OAB, depois os
  processos pendentes, e grava em `djen_sincronizacoes`;
- `registrar(item)`: faz upsert por `id_djen`. Se a publicação já existe,
  atualiza `ativo` e o cancelamento;
- `vincular(comunicacao, processo)`: grava o vínculo, cria o evento e notifica
  na mesma transação, como `EventoService.create` já faz;
- `descartar(comunicacao, usuario)`: para publicações que não são da DAJ;
- casamento automático: `numero_processo` igual a `processos.numero_cnj` e
  processo ativo.

Pontos que diferem do fluxo de requisição:
- A rotina roda **sem request**: `RequestContext.get_unidade_ativa()` não
  existe nesse contexto. O service recebe a unidade explicitamente, e todo
  INSERT passa `unidade_id`.
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
- `texto_html` é conteúdo de terceiros.
- A API devolve um `texto_html_seguro`, limpo no backend com `nh3` (dependência
  nova) numa lista restrita de tags (`p`, `b`, `strong`, `i`, `u`, `br`,
  `table`, `tr`, `td`, `section`, `span`), sem atributos.
- O front só usa `{@html}` com esse campo, nunca com o original.

**Agendamento.** O sistema não tem agendador hoje.
- Criar o comando `flask djen sincronizar`, que também pode ser chamado por
  `scripts/sincronizar_djen.py`.
- Ele roda com `docker compose run --rm api ...`, por cron no host, em dias
  úteis às 8h e às 14h, com `flock` para não sobrepor execuções.
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
| POST | `/api/djen/publicacoes/<id>/descartar` | Marca como não pertencente à DAJ |
| POST | `/api/processos/<id>/djen/buscar` | Busca imediata do histórico do processo |
| GET | `/api/djen/status` | Última sincronização e resultado |

Todas as rotas filtram por unidade. A certidão usa o link público direto;
não há proxy.

## 6. Frontend

- **Menu "DJEN"** no `app-sidebar.svelte`, com os subitens "Publicações" e
  "Sem caso". O "Sem caso" só aparece para os papéis que podem vincular.
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

## 7. Permissões (decisão pendente; proposta)

| Papel | Lista geral | Sem caso | Vincular/descartar | Eventos DJEN no caso |
|---|---|---|---|---|
| `admin`, `prof`, `orient` | Toda a unidade | Sim | Sim | Sim |
| `colab_proj` | Toda a unidade | Não | Não | Sim |
| `estag_direito`, `colab_ext` | Só casos de que participam | Não | Não | Sim, nos casos que já veem |

## 8. Dados pessoais e retenção

- As publicações são públicas, mas trazem nomes de terceiros.
- Só gravamos o que chega pelas OABs monitoradas ou pelos processos
  cadastrados. Nada de busca ampla por tribunal ou por parte.
- Publicações `descartadas`, e as `pendentes` sem vínculo há mais de 90 dias,
  são apagadas pela própria rotina (prazo a confirmar).
- As vinculadas seguem a vida do caso.

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
- `DJEN_SYNC_ENABLED=false` sai sem chamar a API.
- Evento DJEN: campos travados no update; eventos manuais não mudam.

## 10. Fases e PRs

1. **Captura e lista.**
   - Migration (`processos.numero_cnj`, `djen_comunicacoes`,
     `djen_sincronizacoes`).
   - Cliente, service, comando `flask djen sincronizar` e busca por número do
     processo.
   - Rotas de leitura e menu DJEN só com a lista e o detalhe.
2. **Eventos e notificações.** Colunas novas em `eventos`, vínculo automático
   e manual, selo no caso, tipo de notificação `djen` e campos travados.
3. **Captura por OAB.** Cadastro das OABs monitoradas, caixa "Sem caso",
   descarte, retenção e cron documentado no README.
4. **Extras, se decidirem:**
   - sugestão de prazo, com calendário de feriados por tribunal;
   - e-mail (exige decisão: o envio é real);
   - movimentações via DataJud (API do CNJ, com chave pública);
   - busca manual por parte.

## Decisões em aberto

1. **Quais OABs monitorar.** As dos orientadores, lidas de `usuarios.oab`
   (texto livre, `String(30)`, com preenchimento a conferir), ou uma lista
   institucional própria?
   - Proposta: tabela `djen_oabs` (número, UF, usuário dono opcional,
     unidade, ativo), administrada pelo admin. O `usuarios.oab` serve só para
     sugerir o cadastro inicial.
2. **Permissões** da seção 7.
3. **Horários da rotina** e se ela roda em fim de semana.
4. **Prazo de retenção** das publicações descartadas e das pendentes.
5. **Dependências novas:** `nh3` para limpar HTML; `httpx` ou `urllib` para o
   cliente.
