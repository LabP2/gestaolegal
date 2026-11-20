# Resultado da validação independente — DJEN, contextos e modelos

Data: 17/11/2026. Responde ao
[relatório para validação](relatorio-validacao-djen-contextos-2026-11-17.md).
A validação foi feita por execução dos testes automatizados, leitura do código
novo e testes adicionais de API. **A matriz manual pela interface com API e
banco reais não foi executada**; ver "Limitações".

## 1. Base e estado do working tree

- Repositório `/mnt/dados/gestaolegal-multitenant`, branch `feat/multitenant`,
  commit base `7361df6`.
- A camada de contextos continua no working tree, sem commit: 23 arquivos
  modificados e os novos `djen_contexto_repository.py`,
  `djen_contexto_service.py`, `27f86bd31ac9_djen_contextos.py`,
  `test_djen_contextos.py` e `contextos.svelte`. Os arquivos não rastreados
  foram lidos.
- Esta validação acrescentou três arquivos e não alterou nenhum existente:
  este relatório e os dois arquivos de teste da seção 3.
- Nenhum drop/restore, nenhum acesso a QA ou produção, nenhum dado real.

## 2. Comandos e resultados

| Comando | Resultado |
|---|---|
| `.venv/bin/pytest -q` (suíte completa, após a refatoração do SQL) | 1.191 passaram, 8 pulados (MySQL, exigem ativação) |
| `MULTITENANT_MYSQL_TEST=1 .venv/bin/pytest tests/database/test_multitenant_mysql.py -q -k contextos` | 1 passou, 7 excluídos pelo `-k` |
| `alembic -c migrations/alembic.ini heads` | um único head: `27f86bd31ac9` |
| `cd web && npm test` (Playwright, API simulada) | 31 passaram |
| `npm run check` | 0 erros, 25 avisos em 17 arquivos (igual ao inventário do relatório) |
| `npm run lint` | falha de estilo em 5 arquivos, nenhum alterado nesta entrega |
| `.venv/bin/pytest tests/api/test_djen_contextos_regras.py tests/api/test_djen_contextos_treino.py -q` | 28 passaram |
| `.venv/bin/pytest -q` com os dois arquivos novos | 1.219 passaram, 8 pulados |

O relatório de origem registrava que a suíte completa não havia sido reexecutada
depois da refatoração; essa pendência está fechada. `npm run build` não foi
reexecutado. Os outros 7 testes MySQL não foram executados nesta rodada.

Arquivos com falha no `prettier --check` (anteriores à entrega):
`src/lib/components/anexos-evento.svelte`, `src/lib/forms/schemas/login-schema.ts`,
`src/lib/forms/schemas/processo-schema.ts`,
`src/routes/(dashboard)/djen/busca-parte/+page.svelte`,
`src/routes/(dashboard)/djen/oabs/+page.ts`.

## 3. Testes adicionais

Os 9 testes de `tests/api/test_djen_contextos.py` cobriam parte da matriz
funcional. Dois arquivos novos acrescentam 28 casos de API (SQLite em memória,
dados sintéticos) para os itens sem cobertura. Todos passaram sem exigir
mudança no código da aplicação.

`tests/api/test_djen_contextos_regras.py` (21 casos):

| Item da matriz | Teste | Verificado |
|---|---|---|
| Papéis | `test_estagiario_nao_acessa_contextos` | `estag_direito` recebe 403 nas quatro rotas novas |
| Criação | `test_criacao_invalida_nao_grava` (6 casos) | nome, variações e tribunais malformados dão 400; nada é gravado |
| Variações/acentos/tribunal | `test_correspondencia_ignora_acentos_e_caixa` (4 casos) | acento, caixa e tribunal em minúsculas casam; nome ausente não |
| IDs estrangeiros no corpo | `test_contexto_de_outra_unidade_no_corpo_recusa_o_lote` | contexto de outra unidade em `contexto_ids` dá 404, sem descarte nem rótulo parcial |
| Corpo malformado | `test_contexto_ids_malformado` (5 casos) | string, booleano, texto numérico, decimal e objeto dão 400 |
| Regra 6 (limpeza manual) | `test_limpeza_manual_resiste_a_importacao`, `test_limpeza_manual_resiste_a_vinculo_automatico` | "não analisado" manual não é sobrescrito |
| Regra 7 (rota de detalhe) | `test_descarte_pela_rota_individual_nao_avalia_contextos` | descarte individual não rotula nenhum contexto |
| Histórico | `test_historico_separado_por_contexto` | entradas por contexto, com autor e origem; repetição não duplica |

`tests/api/test_djen_contextos_treino.py` (7 casos):

| Item da matriz | Teste | Verificado |
|---|---|---|
| Portas do treino | `test_treino_recusado_nao_grava_modelo` (4 casos) | classe minoritária, menos de 10 processos, divisão sem as duas classes e textos vazios dão 400, sem modelo gravado |
| Separação por CNJ | `test_holdout_separa_por_processo` | nenhum processo nos dois lados do holdout; amostra completa |
| Retreino e texto vazio | `test_retreino_preserva_versao_e_texto_vazio_fica_sem_sugestao` | versão anterior preservada; sugestão migra para a versão nova; texto vazio e publicações já avaliadas ficam sem sugestão; `amostra`/`ids_teste` fora da listagem |
| Sugestões divergentes | `test_sugestoes_divergentes_em_uma_unica_linha` | uma linha por publicação, duas sugestões opostas, rótulos intactos, filtro agregado |

Itens da matriz já cobertos pelos testes da entrega: contextos sobrepostos e
tribunal sem correspondência; rótulos independentes em A e B; vínculo
automático preservando avaliação manual; herança em contexto criado depois;
importar/descartar em A sem alterar B após reconsulta; lote atômico; isolamento
entre unidades; isolamento entre NPJs nas quatro rotas
(`tests/api/test_tenant_vazamento.py`).

## 4. Casos manuais

Nenhum caso manual pela interface foi executado. Os cenários da matriz foram
verificados pela API em testes automatizados, não pela aplicação em
`localhost:5301`/`5300`.

## 5. Achados

Nenhum defeito funcional foi reproduzido. Os achados abaixo são lacunas de
verificação e riscos identificados por leitura.

### Médios

1. **Caminho MySQL do repositório nunca é executado.**
   `gestaolegal/repositories/djen_contexto_repository.py:128`
   (`on_duplicate_key_update`) e `:167` (`with_for_update`) só rodam em MySQL; a
   suíte usa SQLite e o teste MySQL valida apenas schema, FK e
   downgrade/upgrade. Reprodução da lacuna: nenhum teste com
   `MULTITENANT_MYSQL_TEST=1` cria contexto ou rotula pela aplicação.
2. **Custo do filtro por sugestão cresce com o acervo inteiro.**
   `gestaolegal/repositories/djen_acervo_repository.py:239-246` carrega todos
   os IDs acessíveis da unidade, passa-os num `IN (...)` e calcula e grava
   previsões pendentes dentro de um GET
   (`gestaolegal/services/djen_contexto_service.py:135` faz `commit`). Não há
   medição; o relatório de origem já registrava a ausência de ensaio de carga.
3. **Concorrência não exercitada.** Retreino simultâneo a uma avaliação em
   outra sessão depende do `with_for_update`, que o SQLite ignora.

### Baixos

4. **Asserções frouxas.** `tests/api/test_djen_contextos.py:47` aceita
   `nao_classificado` ou `relevante` logo após rotular como relevante;
   `:112-119` aceita 400, 403 ou 404 para o outro NPJ. Os testes novos e
   `test_tenant_vazamento.py` cobrem o comportamento, mas esses dois testes
   deixariam passar regressão.
5. **`npm run lint` falha** em 5 arquivos anteriores à entrega. Não é
   regressão, mas o comando faz parte da verificação do front.
6. **Treino síncrono na requisição** (`djen_contexto_service.py:8`), sem
   limite de tempo; limitação já declarada.

## 6. Limitações desta validação

- Interface não validada contra API e banco reais; o Playwright simula a API.
- Sem medição de tempo/memória em volumes crescentes.
- Imagem Docker não inspecionada (dependências de ML, exclusão de anexos).
- Cenários dos 25 avisos do Svelte não executados: troca SPA A→B na edição de
  evento e em `/processos/[id]/editar`, troca de unidade, presença na virada
  do dia.
- Regressões manuais da base não repetidas (consultas CNJ, lote com
  pausa/falha, login e mostrar senha), além do que a suíte já cobre.
- Qualidade do classificador não avaliada: todos os treinos usaram textos
  sintéticos separáveis.
- A granularidade por NPJ e unidade é decisão de produto e não foi julgada.

## 7. Recomendação

**Sem bloqueio para commit na branch `feat/multitenant`.** A semântica de
rótulos, o isolamento por NPJ/unidade, as permissões e as portas do treino se
comportaram conforme o contrato em todos os testes.

Antes de merge no `master` ou de uso em acervo real, recomenda-se:

1. um teste em MySQL descartável que crie contexto, sincronize e rotule pela
   aplicação (achado 1);
2. medição do filtro por sugestão e do treino com volume (achado 2);
3. roteiro manual pela interface com a stack local;
4. revisão humana da migration `27f86bd31ac9` e das regras de permissão e de
   filtro por unidade, como exige o `CLAUDE.md`.

A contagem de testes não substitui os itens 2 a 4.
