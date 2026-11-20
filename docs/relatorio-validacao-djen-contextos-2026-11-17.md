# Relatório para validação independente — DJEN, contextos e modelos

Data: 17/11/2026. **Este documento descreve o que foi implementado e o que o
próximo agente deve verificar; não é uma aprovação independente.**

## 1. Estado da entrega e escopo

- Repositório: `/mnt/dados/gestaolegal-multitenant`.
- Branch: `feat/multitenant`.
- Último commit enviado: `7361df6` — `feat(djen): unifique acervo e monitoramento`.
- A camada de contextos/modelos descrita aqui está no **working tree, ainda sem
  novo commit/push**. Validar os arquivos não rastreados também; `git diff` sozinho
  não mostra o conteúdo desses arquivos.
- `docs/.obsidian/` contém configuração pessoal e não integra a entrega.
- Aplicação local: frontend `http://localhost:5301`, API `http://localhost:5300`.
  Playwright inicia servidor isolado em `127.0.0.1:5302` e simula a API.
- Migration local atual: `27f86bd31ac9`, sucessora de `19e72ac50bd8`.
- API Docker local reconstruída com dependências de ML. Nenhum deploy nem
  alteração em produção foi feito nesta implementação.
- Na conferência autenticada local, `/api/djen/contextos` e `/api/djen/acervo`
  responderam 200. Não foram criados contextos reais nem treinados modelos com
  publicações reais para esta entrega; o teste de treinamento usou dados sintéticos.

### Implementações anteriores que compõem a base

O commit `7361df6` reúne o acervo persistente por NPJ, classificação anterior,
monitoramento por OAB/parte/processo com logs, buscas manuais em lote e histórico
completo por CNJ; vínculos automáticos ao processo e geração de eventos ao
associá-lo a um caso; progresso de consultas; página de detalhes da publicação;
redirecionamento da consulta de CNJ aos resultados; melhorias de login (mostrar
senha e trim do e-mail). Conferir também os documentos anteriores, sem interpretar
regras antigas de classificação global como a regra dos novos contextos.

O restore e o roteiro local anteriores estão em
[resultado do restore](resultado-restore-2026-11-17.md),
[monitoramento](resultado-monitoramento-djen-2026-11-17.md) e
[ensaio anterior](resultado-ensaio-completo-2026-11-16.md).
Não executar outro drop/restore para validar esta mudança.

## 2. Contrato funcional acordado

### Operação versus treinamento

| Camada | Estados visíveis | Efeito |
|---|---|---|
| Operacional | Não analisado, Importado, Descartado | Trabalha a publicação e seus vínculos com processos/casos/eventos |
| Treino por contexto | Não analisado, Relevante, Irrelevante | Avalia interesse sem criar vínculos nem executar operações |
| Sugestão do modelo | Relevante, Irrelevante ou Sem sugestão | Recomendação separada; não equivale a avaliação confirmada |

Os estados internos `nao_importada` e `pendente` são apresentados como não
analisado; `vinculada` como importado; `descartada` como descartado. O rótulo interno
`nao_classificado` é apresentado como não analisado. Cancelamento na fonte DJEN
continua sendo informação independente.

### Contextos

- Criados no topo de **Acervo para treino** (`/djen/classificacao`).
- Contêm nome livre, uma ou mais variações do nome da parte e lista de tribunais.
  Lista de tribunais vazia significa todos.
- O armazenamento e acesso atuais são por **NPJ e unidade ativa**. Confirmar que
  essa granularidade satisfaz o uso desejado; não há contexto compartilhado entre
  unidades na implementação atual.
- Correspondência por substring nos nomes de destinatários estruturados, ignorando
  caixa e acentos. Não faz busca semântica no texto e não resolve entidades.
- Na criação, inclui as publicações compatíveis já acessíveis na unidade. Novas
  capturas são associadas aos contextos compatíveis.
- Filtros do contexto são fixos após a criação. Não há edição, remoção ou pausa
  de contextos nesta versão; criar outro contexto representa outra finalidade.
- A mesma publicação participa de vários contextos sem duplicação do conteúdo.

### Rótulos e prioridade

1. Contexto criado depois da operação: importadas começam relevantes;
   descartadas começam irrelevantes; demais começam não analisadas.
2. Vínculo/importação automática rotula nos contextos compatíveis, preservando
   avaliações manuais feitas no treino.
3. Na lista com contexto selecionado, importar/descartar alimenta esse contexto.
4. Em “Todos os contextos”, caixas de seleção determinam quais contextos recebem
   a avaliação. Sem selecionar, executa somente a operação. Só se aplicam rótulos
   aos contextos a que cada publicação efetivamente pertence.
5. Reconsulta não desfaz avaliação humana nem rotula posteriormente um contexto
   que foi deixado fora de uma operação manual.
6. Classificar manualmente como não analisado também é decisão manual e não deve
   ser sobrescrito por uma operação posterior.
7. Rotas antigas de detalhe/vínculo e ações da busca por parte operam sem avaliar
   contextos. Para avaliar relevância, usar lista contextual ou tela de treino.
8. Sem `contexto_ids`, a API de importação/descarte em lote mantém compatibilidade
   para zero/um contexto; havendo vários, exige escolha explícita. O frontend novo
   sempre envia uma lista, inclusive `[]` para operação sem avaliação.

### Apresentação operacional

- Filtro **Contexto de classificação**: todos ou um contexto salvo.
- Filtro **Sugestão do modelo**: todas, relevante, irrelevante, sem sugestão.
- Uma linha por publicação; sugestões identificadas por nome do contexto e versão.
- Sugestões conflitantes mostram “Sugestões divergentes”, sem rótulo agregado.
- Avaliação já registrada é distinta da sugestão.
- Bordas/cor da lista operacional acompanham a situação operacional; no treino,
  acompanham o rótulo do contexto selecionado.
- Ler publicação abre a página de detalhes com histórico contextual identificado;
  auditoria antiga é identificada como “Legado (sem contexto)”.

## 3. Persistência e compatibilidade

Migration aditiva: `migrations/versions/27f86bd31ac9_djen_contextos.py`.

| Tabela | Conteúdo |
|---|---|
| `djen_contextos` | NPJ, unidade, nome, variações da parte, tribunais, criação |
| `djen_publicacao_contextos` | Publicação × contexto, rótulo/origem/autor/data, modelo/sugestão/probabilidade |
| `djen_contexto_historico` | Mudanças de rótulo da relação, autor, momento, sugestão e versão disponíveis |
| `djen_modelos` | Contexto, versão identificada pelo ID, artefato JSON, métricas e amostra |

Há unicidade em `(tenant_id, id_publicacao, contexto_id)`, índice por
`(tenant_id, contexto_id, rotulo)` e FKs compostas com tenant nas referências.
A probabilidade é armazenada como texto numérico na relação; não é exibida como
confiança calibrada na interface.

As tabelas antigas `djen_classificacoes` e `djen_classificacao_historico` e rotas
anteriores continuam por compatibilidade. **Não são a fonte do treinamento novo.**
A tela não expõe mais o antigo card global de exemplos. Validar a convivência:
filtros/exports/clientes antigos podem continuar usando a semântica anterior;
não presumir que essas APIs foram removidas ou migradas para contextos.

O downgrade remove as quatro tabelas novas e seus dados, preservando o acervo.
Testar downgrade somente em banco descartável, não no banco local de trabalho.

## 4. Modelo implementado

- **TF-IDF + regressão logística**, um modelo por contexto. LightGBM não foi implementado.
- Texto: `texto_plano`, sem usar o rótulo ou situação operacional como atributo.
- TF-IDF: caixa baixa, remoção de acentos, unigramas/bigramas, até 20.000 atributos,
  frequência sublinear. Regressão logística balanceada, até 1.000 iterações.
- Porta de entrada: 200 exemplos rotulados, pelo menos 50 de cada classe.
  Exige ainda 10 CNJs distintos e ambas as classes em treino e teste.
- A interface habilita o botão pela contagem de rótulos; os requisitos de processos
  e da divisão são verificados no backend, podendo resultar em mensagem de recusa.
- Holdout de 25%, por CNJ, com semente fixa 42. O vocabulário da avaliação é
  aprendido exclusivamente no treino. Precisão, revocação e F1 são registrados.
- Após avaliar, ajusta o artefato final com todos os exemplos rotulados disponíveis.
  As métricas exibidas são as do holdout, não do ajuste final com todos os dados.
- Artefatos JSON com vocabulário, IDF, coeficientes/intercepto e identificador do
  algoritmo. Não há carregamento de pickle enviado pelo usuário.
- Modelos/versionamento não são apagados ao retreinar. A versão mais recente passa
  a fornecer sugestões experimentais automaticamente; não há promoção/aprovação
  separada de modelo.
- Inferência ocorre no carregamento/filtro do acervo e persiste a sugestão. Para
  uma nova versão, calcula para relações ainda não analisadas. Texto vazio fica
  sem nova sugestão. Não modifica rótulo, importação, processo ou evento.
- Não há treino a cada clique: retreinar exige comando explícito.

**Limites que o validador deve considerar:** treinamento síncrono na requisição;
sem job de fundo, curva de aprendizado, holdout temporal, calibração, comparação
com LightGBM ou avaliação humana independente. Métricas usam inclusive rótulos
operacionais; exemplos sintéticos provam funcionamento, não qualidade em DJEN real.
O holdout por CNJ não elimina textos quase idênticos entre processos diferentes.
A associação inicial percorre metadados das publicações acessíveis; o filtro de
sugestão pode calcular previsões pendentes para um conjunto amplo. Validar custo
em volume antes de adotar em acervo grande. Não houve ensaio de carga.

## 5. Mapa de código para revisão

- `gestaolegal/database/tables.py`: definições das quatro tabelas.
- `migrations/versions/27f86bd31ac9_djen_contextos.py`: schema da migration congelado.
- `gestaolegal/repositories/djen_contexto_repository.py`: escopo, associação,
  rótulos/histórico, escolhas operacionais e persistência de modelos/previsões.
- `gestaolegal/services/djen_contexto_service.py`: treinamento e inferência; SQL
  foi separado para obedecer à guarda arquitetural existente.
- `gestaolegal/repositories/djen_acervo_repository.py`: filtro contextual,
  enriquecimento das linhas, filtro de sugestão e histórico.
- `gestaolegal/services/djen_service.py`: integração das decisões operacionais.
- `gestaolegal/controllers/djen_controller.py`: novas rotas e filtro `contexto_id`.
- `web/src/lib/components/djen/contextos.svelte`: seleção/criação/treinamento.
- `web/src/lib/components/djen/acervo.svelte`: filtros, escolhas e sugestões.
- `web/src/lib/components/djen/busca-parte.svelte`: descarte operacional em vez
  da ação antiga de marcar irrelevante globalmente.
- `web/src/lib/components/djen/detalhe-publicacao.svelte`,
  `lista-publicacoes.svelte`, `web/src/lib/types/djen.ts` e rotas de acervo/treino:
  semântica, contratos e histórico.
- `pyproject.toml`, `uv.lock`, `Dockerfile`: scikit-learn/NumPy/SciPy; base Debian slim.
- `.dockerignore`: exclui anexos locais, cópias anteriores, Obsidian e cache graft
  do contexto da imagem.

Novas rotas, prefixadas por `/api`, protegidas por autenticação, papéis de gestão
(`admin`, `prof`, `orient`) e DJEN habilitado:

| Método | Rota | Uso |
|---|---|---|
| GET / POST | `/djen/contextos` | Listar / criar na unidade ativa |
| POST | `/djen/contextos/<cid>/classificar` | Rótulo manual em lote |
| POST | `/djen/contextos/<cid>/treinar` | Treinar versão experimental |

## 6. Evidências de execução e limites da cobertura

Os arquivos estão em [evidencias-contextos-2026-11-17](evidencias-contextos-2026-11-17/).
São cópias dos logs selecionados, com caminho absoluto substituído por `REPO` e
espaços finais removidos. A captura de tela usa somente dados sintéticos.

| Execução | Resultado observado | Evidência |
|---|---|---|
| Suíte completa pytest, antes de separar SQL do serviço | 1.188 passaram, 1 falhou, 8 pulados; falha na regra arquitetural de SQL fora de repositório | `pytest-completo-antes-refatoracao.txt` |
| API, contextos, acervo, isolamento e guarda após refatoração | 237 passaram | `pytest-pos-refatoracao.txt` |
| Contextos e guarda após último ajuste de leitura de metadados | 50 passaram | `pytest-verificacao-final.txt` |
| Navegador, incluindo novos cenários | 31 passaram | `npm-test-31.txt` |
| Repetição dos 2 cenários afetados pela padronização final dos selects | 2 passaram | `npm-test-seletores.txt` |
| Migration, FK entre NPJs e downgrade/upgrade em MySQL descartável | 1 passou; 7 outros testes excluídos por `-k` | `mysql-migration.txt` |
| Migration no MySQL local de trabalho | Upgrade concluído | `migration-local.txt` |
| Checagem final Svelte | 0 erros, 25 avisos em 17 arquivos | `npm-check.txt` |
| Build final frontend | Concluído | `npm-build.txt` |

**Não somar as linhas:** há sobreposição de testes. A suíte completa não foi
reexecutada integralmente depois da refatoração; a falha foi corrigida e os testes
afetados repetidos. Os 8 testes MySQL pulados na execução comum exigem ativação
explícita; somente o novo teste MySQL foi executado nesta rodada. Houve falhas
intermediárias de seletor/sincronização e de assinatura de exceção, corrigidas antes
das repetições registradas. A aprovação aqui não equivale a toda a interface com
API e banco reais: Playwright simula a API. O teste de ML executa treinamento real,
mas sobre textos sintéticos.

## 7. Os 25 avisos: significado e impacto

Todos são `state_referenced_locally`. Indicam leitura de uma prop/estado reativo
apenas na inicialização local, que **não acompanhará sua substituição** depois.
Referência: [documentação oficial do Svelte](https://svelte.dev/docs/svelte/compiler-warnings#state_referenced_locally).

- Não são erros de compilação e não impedem o build atual.
- Não são, por si, exceções de runtime nem mensagens obrigatoriamente exibidas
  ao usuário. São diagnósticos do compilador/checador, vistos nos logs de
  desenvolvimento/build; não confundir com erros do console do navegador.
- Não provam lentidão, perda de dados ou falha no modelo DJEN.
- O risco funcional é **estado desatualizado em componente reutilizado**. Exemplo:
  navegar de edição A para B na mesma instância pode manter campos/seleções de A,
  enquanto o ID usado para salvar já corresponde a B.
- Capturar o estado inicial pode ser intencional: o formulário contém um rascunho
  editável. Fazer tudo reagir indiscriminadamente pode sobrescrever a digitação.
- Não foram silenciados. Nenhum dos novos componentes de contextos aparece no
  diagnóstico. Os avisos já estavam presentes antes da camada de contextos.

### Inventário exato da checagem final

Linhas registradas na evidência; podem mudar com futuras edições.

| Arquivo | Linhas | Avisos |
|---|---|---|
| `web/src/lib/components/evento-dialog.svelte` | 32 | 1 |
| `web/src/lib/forms/processo-form.svelte` | 41 | 1 |
| `web/src/lib/forms/arquivo-form.svelte` | 16, 17 | 2 |
| `web/src/lib/forms/assistencia-judiciaria-form.svelte` | 31 | 1 |
| `web/src/lib/forms/assistido-form.svelte` | 34 | 1 |
| `web/src/lib/forms/atendido-form.svelte` | 54 | 1 |
| `web/src/lib/forms/caso-form.svelte` | 99, 177, 178, 179, 186 | 5 |
| `web/src/lib/forms/login-form.svelte` | 10 | 1 |
| `web/src/lib/forms/orientacao-juridica-form.svelte` | 45, 89 | 2 |
| `web/src/lib/forms/password-form.svelte` | 31 | 1 |
| `web/src/lib/forms/user-form.svelte` | 43 | 1 |
| `web/src/routes/(dashboard)/casos/[id]/eventos/[eventoId]/editar/+page.svelte` | 28, 94 | 2 |
| `web/src/routes/(dashboard)/plantao/registro-presenca/+page.svelte` | 14, 15 | 2 |
| `web/src/routes/(dashboard)/usuarios/eu/alterar-senha/+page.svelte` | 23 | 1 |
| `web/src/routes/esqueci-a-senha/+page.svelte` | 22 | 1 |
| `web/src/routes/login/+page.svelte` | 28 | 1 |
| `web/src/routes/redefinir-senha/[token]/+page.svelte` | 24 | 1 |

### Impacto por grupo e prioridade de validação

| Grupo | Quantidade | Interpretação e teste necessário |
|---|---:|---|
| Inicialização `superForm` (9 componentes e 4 páginas de autenticação/senha) | 13 | Geralmente estado inicial editável. Conferir troca de registro, token e modo sem remontagem; não converter cegamente em efeito |
| Desestruturação do objeto `form` em login | 1 | Pode manter stores do objeto anterior se a prop `form` for substituída; provar comportamento de reutilização |
| Defaults e seleções do formulário de caso | 4 | Defaults de criação e assistidos não seguem novas props; verificar criação/edição e troca de caso |
| Seleção inicial de atendidos na orientação | 1 | Pode manter atendidos de outra orientação se reutilizar a instância |
| Título e descrição de arquivo | 2 | Edição entre arquivos deve reinicializar; página atual usa `{#key data.arquivo.id}` |
| Formulário e responsável na edição de evento | 2 | Prioridade alta de investigação: a página usa dados iniciais, mas URL de envio usa evento/caso atuais; falta demonstração específica de troca SPA A→B |
| Estado e hora de registro de presença | 2 | A ação local atualiza ambos pela resposta da API; ainda verificar invalidação externa, troca de unidade e virada do dia |

Proteções conferidas no código: `{#key id}` em edições de usuário, caso,
arquivo, orientação, atendido/assistido, assistência judiciária e processo dentro
do caso. Isso protege a troca do ID, mas não prova comportamento em mudanças de
props com o mesmo ID. A edição direta `/processos/[id]/editar` não mostrou a mesma
proteção na inspeção; priorizar teste específico. O teste SPA existente exercita
usuários, não prova automaticamente todas essas telas.

**Não há bug reproduzido novo atribuído aos avisos nesta rodada.** Os cenários acima
são riscos identificados por inspeção, para confirmação. O relatório anterior
já registrava a necessidade de validar eventos/presença fora dos formulários
cobertos. O próximo agente deve separar inicializações intencionais de falhas reais
antes de propor correções ou supressões locais justificadas.

## 8. Roteiro para o agente validador

Não usar produção; não executar drop/restore. Para dados de teste, usar fixtures,
NPJ/unidade sintéticos ou MySQL descartável. Não versionar tokens, dumps, senhas,
textos ou anexos reais. Não remover alterações do working tree nem Obsidian.

### Revisão e testes automatizados

```bash
git status --short
git diff --stat
# Ler também os arquivos novos listados por git status.
.venv/bin/pytest -q
.venv/bin/pytest tests/api/test_djen_contextos.py tests/api/test_tenant_guarda.py tests/api/test_tenant_vazamento.py -q
MULTITENANT_MYSQL_TEST=1 .venv/bin/pytest tests/database/test_multitenant_mysql.py -q -k contextos
cd web
npm test
npm run check
npm run build
```

O teste MySQL cria seu próprio contêiner e porta local, nunca recebe URL de banco
existente. Se a infraestrutura não estiver disponível, relatar a limitação.

### Matriz funcional a executar e registrar

- [ ] Criar dois contextos com filtros sobrepostos e um que não corresponda; conferir
  quantidade de publicações, variações/acentos e todos versus tribunal específico.
- [ ] Verificar exclusão de outro NPJ e outra unidade em leitura, classificação,
  escolha operacional e treinamento; tentar IDs estrangeiros no corpo e na URL.
- [ ] Classificar a mesma publicação como relevante em A e irrelevante em B;
  recarregar, reconsultar e verificar persistência e histórico independente.
- [ ] Importar automaticamente publicação de processo cadastrado; conferir vínculo,
  eventos quando houver caso e rótulo inicial em contextos compatíveis.
- [ ] Criar contexto após importação/descarte; conferir herança inicial dos rótulos.
- [ ] Importar/descartar em A sem alterar B; repetir captura e confirmar que B não
  recebe retroativamente a avaliação omitida.
- [ ] Fazer avaliação manual contrária à operação e também limpar para não analisado;
  conferir prioridade manual diante de importação automática e operação posterior.
- [ ] Em todos os contextos, nenhuma caixa marcada executa só operação; escolhidas
  A/C não alteram B. Lote parcialmente inválido deve falhar sem gravação parcial.
- [ ] Verificar ações das telas de busca por parte e detalhe: sem avaliação de contexto.
- [ ] Sem contexto selecionado, botão de classificar permanece desabilitado.
- [ ] Treino recusa insuficiência de classes, quantidade, processos e divisão sem
  ambas as classes. Conferir mensagem e ausência de modelo incompleto.
- [ ] Treinar com corpus sintético diversificado; conferir separação por CNJ, métricas,
  amostra e artefato. Repetir treinamento: nova versão, versões anteriores preservadas.
- [ ] Novas publicações recebem sugestões por contexto; sugestões divergentes visíveis,
  sem duplicar linhas ou alterar rótulos/operações. Texto vazio não gera nova sugestão.
- [ ] Conferir filtros de sugestão/contexto, paginação e manutenção dos filtros ao
  ler/voltar. Confirmar que sugestões não são tratadas como rótulos confirmados.
- [ ] Verificar histórico após decisão: autor, origem, relação correta e versão/sugestão.
  Investigar concorrência entre retreino, outra sessão e confirmação de avaliação.
- [ ] Medir tempo/memória da criação de contexto, filtro por sugestão e treino com
  volumes crescentes; registrar limites do processamento síncrono e timeouts.
- [ ] Inspecionar imagem Docker nova para confirmar dependências e exclusão de anexos
  locais; não confundir caminho montado em runtime com conteúdo da imagem.
- [ ] Executar cenários dos avisos: editar A→B por navegação SPA, alterar unidade,
  invalidar dados, preservar rascunho no mesmo registro e testar presença na virada do dia.
- [ ] Testar regressões da base: consultas CNJ completas, lote com pausa/falha,
  vínculos processo→caso, leitura de publicação, login e mostrar senha.

### Resultado esperado da validação independente

Entregar outro relatório em `docs` com: commit/base e estado do working tree;
comandos e resultados; casos manuais realizados; achados por gravidade com
arquivo/linha e reprodução; limitações; recomendação de aprovação ou bloqueio.
**Não considerar contagem de testes como substituto da revisão de segurança,
semântica de rótulos ou qualidade do classificador.**

## 9. Atualização de interface após o relatório inicial

O acervo para treino passou a reunir seleção/criação de contexto, resumo da parte
 e tribunais, filtro de classificação, contagens e treinamento em um único card.
“Novo contexto” abre o formulário; tribunais usam seleção múltipla compacta.
Período e número do processo ficam em “Filtros adicionais” (aberto quando há filtro
ativo). OAB, origem, situação operacional e filtros redundantes de parte/tribunal
foram retirados da tela de treino. Sem contexto, o loader busca apenas a lista de
contextos e não carrega publicações. Os parâmetros aceitos nessa página são
contexto, classificação, processo, datas e página, evitando filtros antigos ocultos.

Validação deste ajuste: três testes Playwright afetados passaram, incluindo
criação, classificação, filtros e largura de tablet. `npm run check`: zero erros,
mesmos 25 avisos. Essas verificações são posteriores às evidências da seção 6.

## 10. Partes sugeridas nos cards e importação sem parte

A listagem agora devolve `partes` (nomes dos destinatários estruturados do DJEN)
e `atendidos_sugeridos`. A correspondência é exata após normalização de acentos,
caixa e espaços, incluindo variações cadastradas; limita-se a atendidos ativos
do NPJ e da unidade ativa. Homônimos permanecem candidatos distintos, sem
pré-seleção. Uma única correspondência é sugerida, mas exige confirmação.
A comparação carrega nomes e variações da unidade uma vez por página; não há
índice de nomes normalizados nem ensaio de desempenho em grande volume.

Cada card operacional não importado contém escolha da parte e botão de
importação. O seletor geral foi removido. O botão de lote é “Importar selecionadas
sem parte”: envia `sem_parte: true`, reutiliza processos encontrados pelo CNJ e
cria os novos sem caso e sem partes. A associação de partes pode ser feita depois.
O nome não dispara importação automática. Importações para processos existentes
preservam as partes já cadastradas. O endpoint de cadastro manual de processos
continua exigindo parte; a exceção usa `ProcessoDjenInput` apenas na importação.

Validação desta alteração: 119 testes API (acervo, contextos, processos avulsos e
novas sugestões) passaram; 43 testes de sugestões e guarda de tenant passaram
após acrescentar cenário de outro NPJ. Navegador: 14 testes DJEN passaram no lote;
o teste novo teve o seletor de teste corrigido de combobox para button e passou
na repetição, incluindo confirmação individual, homônimos sem pré-seleção,
importação em lote e largura de tablet. Svelte check: 0 erros e os 25 avisos
anteriores. Ruff F e `git diff --check` passaram. Sem mudanças em produção.

## 11. Correções após a validação independente: processamento assíncrono

Implementação de 17/11/2026, posterior ao relatório independente:

- Migration aditiva `38a97ce42bd0` (depois de `27f86bd31ac9`) persiste estado,
  token de execução, erro e horários do último treino no contexto. Nenhuma
  tabela nova e nenhum rótulo/conteúdo removido. Já aplicada apenas em localhost.
- `POST /djen/contextos/<id>/treinar` agora retorna **202**, com estado `na_fila`.
  Verifica os mínimos de rótulos sem carregar textos. Pedidos simultâneos para
  o mesmo contexto reutilizam o token. As validações de CNJ, divisão de classes
  e qualidade dos textos continuam no treino e produzem estado `erro` quando
  não atendidas. Não houve redução das exigências para treinar.
- O serviço `djen-ml-worker`, separado de `djen-worker`, executa
  `python -m scripts.processar_djen_modelos`. Está definido nos dois Composes,
  com as mesmas dependências de banco/migration; só foi iniciado no Compose dev.
  Não consulta a justiça nem depende de `DJEN_SYNC_ENABLED`.
- Worker percorre apenas NPJs ativos com DJEN habilitado; os repositórios
  continuam escopados por tenant/unidade. Treinos usam processo separado, prazo
  de 10 minutos e estados `na_fila`, `executando`, `concluido`, `erro`.
  Execuções abandonadas há mais de 15 minutos são marcadas como erro. É possível
  solicitar novamente; o token antigo não pode publicar modelo nem finalizar
  uma execução nova. Publicação do modelo e conclusão usam a mesma transação.
- Inferência sai dos GETs. A listagem e o filtro por sugestão consultam apenas
  previsões persistidas; publicações recém-capturadas podem ficar temporariamente
  sem sugestão. O worker processa até 200 relações por contexto a cada ciclo,
  com prazo de 60 segundos por subprocesso de inferência. Textos vazios registram
  a versão examinada sem sugestão, evitando repetição infinita no primeiro lote.
- UPDATE de previsão exige rótulo ainda não analisado e versão anterior à nova:
  inferência tardia não sobrescreve decisão humana nem substitui versão mais nova.
- A tela acompanha a fila a cada cinco segundos consultando apenas contextos,
  sem recarregar a lista nem apagar seleção de publicações. Mostra erro e permite
  nova solicitação. Após o treino, informa que sugestões são atualizadas em lotes.
- As asserções frouxas apontadas foram substituídas por rótulos por ID e código
  exato para o cenário de autorização. Os cinco arquivos de frontend apontados
  foram formatados; `npm run lint` passou.

Validação nova inclui: API e treino reais em MySQL descartável; upsert repetido;
lock de rótulo em duas sessões (manual prevalece); dois pedidos simultâneos com
um único token/modelo; fila idempotente; GET sem execução de ML; lote de 200 + 5;
previsão tardia; token expirado; recuperação de processo abandonado; timeout;
UI de fila/andamento/erro. Resultados finais e logs são registrados abaixo ao
concluir a execução completa.

Limites que continuam: treino carrega a amostra do contexto em memória no
subprocesso; não houve ensaio com acervo real ou validação da qualidade do modelo
com rótulos reais. Não há percentual de progresso do algoritmo nem cancelamento
manual. Se o worker estiver parado, pedidos permanecem na fila. A infraestrutura
nova e a migration ainda requerem revisão antes de merge conforme `CLAUDE.md`.

Resultados finais da seção 11:

- Suíte Python completa: **1.225 passaram, 9 pulados**, em 244,90 s. Os pulados
  são os testes MySQL, executados separadamente com ativação explícita.
- Suíte MySQL descartável completa: **9 passaram**, em 130,21 s. Containers de
  ensaio removidos; não utilizam o banco de desenvolvimento nem produção.
- Navegador completo: **33 passaram**. Depois do ajuste para consultar só o
  status sem invalidar a lista, o teste afetado passou novamente.
- Fila/worker/Composes: **7 passaram**, incluindo o teste adicional de
  recuperação e timeout acrescentado após a coleta da suíte completa.
- `npm run check`: **0 erros, 25 avisos preexistentes**; `npm run lint` passou;
  `npm run build` passou. Ruff F e `git diff --check` passaram.
- Localhost: head confirmado `38a97ce42bd0`; `djen-ml-worker` iniciado e seus
  ciclos verificados sem erro. Nenhum commit/push ou ação em produção.
- Logs: `docs/evidencias-contextos-2026-11-17/async-*.log`.

As contagens acima se sobrepõem e não devem ser somadas. Permanecem para revisão:
ensaio de carga com volume representativo, qualidade do classificador com dados
reais e revisão humana da migration/contrato de API antes do merge.


## 12. Chrome com API e banco locais reais

Validação de 17/11/2026 via Playwright e Google Chrome instalado, em
`http://localhost:5301`, sem mocks ou interceptação da API. Produção não foi
acessada. Login pela interface aceitou espaços nas extremidades do email.

Preparação: 248 publicações sintéticas e 240 rótulos iniciais inseridos por
código no banco local (não por cliques), sem alterar decisões de publicações
reais. Contexto criado pela interface: **VALIDACAO UI 20261117 — TJMG**, id 1.
O contexto e os dados de teste permanecem no ambiente para reprodução.

**13 verificações passaram**, conforme `real-resultado.json`: filtros de
parte/contexto; importação com atendido sugerido; lote sem parte e reutilização
do processo para o mesmo CNJ; reimportação idempotente; descarte operacional;
detalhes com texto e link original; parte confirmada no processo; classificação
sem importar; fila real; conclusão pelo worker com atualização automática;
filtro por previsão persistida; layout tablet sem transbordamento; ausência
de erros JavaScript e HTTP na execução. O link original foi conferido pelo
href, sem navegar ao destino sintético.

Leitura posterior do banco confirmou rótulos relevantes nas importações,
irrelevantes no descarte/classificação manual e previsões do modelo 1 em
publicações não classificadas. Texto vazio permaneceu sem sugestão.

Correção encontrada no ensaio: a data dos cards agora usa `formatDateOnly`,
mostrando `17/11/2026` em vez da string RFC da API. Três verificações reais
adicionais passaram após recarregar: data e classificação sem importação;
processo do lote sem parte; conclusão e métricas persistidas. Três regressões
automatizadas direcionadas passaram; `npm run check`: zero erros, 25 avisos
preexistentes.

Evidências: `docs/evidencias-contextos-2026-11-17/real-*` (JSON, logs e capturas
restritas ao card/contexto). Credenciais e estado autenticado não foram
copiados para o repositório.

Limites: não constitui teste de toda a aplicação. Permanecem carga e qualidade
com rótulos reais; não foram revalidados aqui todos os fluxos de monitoramento,
troca de unidade ou vinculação posterior de processo a caso/eventos.
Nenhum commit ou push foi feito.
