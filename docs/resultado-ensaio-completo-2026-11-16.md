# Ensaio completo — 16/11/2026

> **Atualização:** as correções do plano foram implementadas e os seis itens pendentes/falhos foram revalidados na seção final. A tabela abaixo preserva o resultado histórico do ensaio.

**Resultado do ensaio inicial em 16/11/2026: 80 itens aprovados, 3 com falha e 3 parcialmente verificados (86 itens).** As falhas e os limites estão discriminados abaixo; não é uma aprovação integral para implantação. Referência: [roteiro completo](roteiro-ensaio-completo.md). Checkout `222e512`; alterações preexistentes preservadas.

## Preparação

- Produção lida em `lab_prod_1`, projeto `gestaolegal`, por `scripts/producao_para_local.sh`.
- Pacote local: `dumps/producao-20261116-142931.tar`; revisão original `e2f3a4b5c6d7`; 695 anexos.
- Primeira restauração interrompida por permissão da pasta local `uploads`. Proprietário corrigido; restauração retomada com o mesmo pacote.
- Suíte geral: **1.137 passaram, 5 ignorados**, em 248,87 s.
- MySQL descartável: **5 passaram**, em 156,14 s.
- Frontend: **8 erros e 41 avisos**. Logs em `evidencias-ensaio-2026-11-16/`.
- Resultados automatizados não substituem os itens abaixo. Nenhuma correção de código realizada.

## Retomada após reinício da máquina

- Solicitado refazer o banco **somente local**, restaurar banco e anexos do pacote já baixado e executar o roteiro completo.
- Pacote validado novamente; banco local recriado e SQL restaurado, anexos substituídos.
- Backup automático anterior à nova restauração: `dumps/local-antes-20261116-152806.sql.gz`; anexos em `dumps/uploads-antes-20261116-152806`.
- Migrations concluídas de `e2f3a4b5c6d7` até **`b3c4d5e6f7a8`**, confirmado diretamente em `alembic_version` ao salvar.
- API e frontend em execução; MySQL e Mailpit saudáveis. Script encerrou com “pronto”.
- Migration DJEN registrou 82 processos fora do padrão CNJ, sem `numero_cnj`.
- Log: `evidencias-ensaio-2026-11-16/restauracao-retomada.log`.
- Backend na retomada: **1.137 passaram, 5 ignorados**, em 298,28 s (`pytest-retomada.log`).
- Frontend na retomada: **8 erros e 41 avisos em 34 arquivos** (`frontend-retomada.log`).
- A nova execução dos testes MySQL descartáveis não foi confirmada: chamada interrompida, sem `mysql-retomada.log`. Os 5 testes aprovados acima pertencem à tentativa anterior.
- Nenhum comando de acesso ao servidor de produção nesta retomada.

## Roteiro

| Item | Estado | Evidência e limites |
|---|---|---|
| 1.1 | ✅ | Login correto, cabeçalho DAJ e seletor das duas unidades |
| 1.2 | ✅ | Página setup-admin retorna 404 |
| 1.3 | ✅ | Senha errada recusada na tela |
| 1.4 | ✅ | Menu Processos presente; DJEN ausente |
| 2.1 | ✅ | Totais API e telas: BH 3499, NL 587, iguais ao banco restaurado |
| 2.2 | ✅ | Totais API e telas: BH 615, NL 335; colunas de assistido/estagiário presentes |
| 2.3 | ◐ | Três casos antigos com processo por unidade abertos; descrição igual ao SQL local e seções carregadas. Não houve comparação independente de todos os campos/eventos com a produção de origem. |
| 2.4 | ◐ | Um assistido e um não assistido por unidade abertos; nome/CPF/e-mail/celular iguais ao SQL local. Comparação exaustiva de todos os campos com dump original não realizada. |
| 2.5 | ✅ | 695 arquivos movidos ao layout tenant1; downloads de caso e evento BH/NL HTTP200, assinatura PDF válida e pdfinfo abriu os quatro arquivos. |
| 2.6 | ✅ | Busca geral encontra atendido ativo conhecido nas duas unidades; inativos excluídos conforme filtro |
| 2.7 | ✅ | Telas de usuários, orientações, escalas, fila, registro de presença, notificações, relatórios e arquivos abertas em BH e NL |
| 2.8 | ✅ | Parceiros: IDs, nomes e totais comparados com SQL local nas duas unidades |
| 3.1 | ✅ | Cadastro normal criado pela API, exibido em BH, inacessível em NL (404) |
| 3.2 | ✅ | Caso com orientador e estagiário criado via API e aberto na tela |
| 3.3 | ✅ | Processo criado pela API e exibido no caso |
| 3.4 | ✅ | Evento e PDF criados pela API; download idêntico ao original |
| 3.5 | ✅ | Descrição de caso antigo alterada e restaurada; histórico mudou |
| 3.6 | ❌ | Ficha antiga id2 não salva sem alterações: legado sem CPF válido e sem respostas para procurou outro local/PJ constituída; formulário exige preenchimento. Nenhum dado inventado para contornar. |
| 3.7 | ✅ | Recuperação pela tela, e-mail no Mailpit, link e login com nova senha testados |
| 4.1 | ✅ | Login pela tela; somente DAJ, como esperado nesta cópia nova |
| 4.2 | ✅ | Login da plataforma com credenciais do admin DAJ: HTTP 401 |
| 4.3 | ✅ | NPJ Ensaio criado pela tela, com unidade e link de primeiro acesso |
| 4.4 | ✅ | Sigla/slug duplicados recusados; SQL confirma 2 tenants, 3 unidades, 245 usuários e nenhum admin parcial |
| 5.1 | ✅ | Primeiro acesso e senha definidos pela tela; login ENS com uma unidade |
| 5.2 | ✅ | Atendido e caso ENS criados pela API |
| 5.3 | ✅ | Busca geral DAJ não encontra cadastro exclusivo ENS |
| 5.4 | ✅ | Caso DAJ inacessível ao ENS na API e URL direta |
| 5.5 | ✅ | Busca Maria ENS retorna somente seu cadastro |
| 5.6 | ✅ | Somente administrador ENS na lista |
| 5.7 | ✅ | Lista inicial de processos ENS vazia |
| 6.1 | ✅ | Desativação local pela API da plataforma |
| 6.2 | ✅ | Sessão ENS recarregada após desativação |
| 6.3 | ✅ | Login ENS inativo: HTTP 401 |
| 6.4 | ✅ | Sessão DAJ permanece válida |
| 6.5 | ✅ | Login ENS volta após reativação |
| 7.1 | ❌ | DJEN desligado exibe Acesso negado genérico, sem explicar a desativação |
| 7.2 | ✅ | DJEN ligado pela tela da plataforma; estado persistido confirmado |
| 7.3 | ✅ | Menu DJEN visível após recarga |
| 7.4 | ✅ | Publicações vazias antes da primeira rotina; status verificado |
| 8.1 | ✅ | Tela OAB aberta e sugestões consultadas |
| 8.2 | ✅ | Duas OABs reais sugeridas cadastradas em BH |
| 8.3 | ✅ | OAB repetida recusada HTTP 400 |
| 8.4 | ✅ | OAB desativada e reativada via API |
| 9.1 | ✅ | Confirmação informa todas as unidades, OABs ativas, 3 dias e até 15 processos |
| 9.2 | ✅ | Rotina real pela tela concluiu HTTP200 status ok em 13s, sem novas publicações |
| 9.3 | ✅ | Solicitação concorrente recusada HTTP422 DJEN_EM_EXECUCAO |
| 9.4 | ✅ | Rotina repetida; última execução sem publicações novas |
| 10.1 | ✅ | Publicação real aberta com texto, classe em maiúsculas e link externo |
| 10.2 | ✅ | Consulta complementar real de OABs em30 dias trouxe6 publicações pendentes; caixa Sem caso aberta |
| 10.3 | ✅ | Vínculo pela tela criou evento no caso951 e notificações DJEN para orientador9 e estagiário11 (SQL) |
| 10.4 | ✅ | Descarte pela tela aguardou resposta HTTP200 e estado descartada |
| 10.5 | ✅ | Publicação comprovadamente descartada foi vinculada pela tela ao processo87 |
| 11.1 | ✅ | Detalhe de processo com CNJ válido aberto em Nova Lima |
| 11.2 | ✅ | Card DJEN carregado no detalhe |
| 11.3 | ✅ | Busca real trouxe 5 novas publicações, 5 vínculos e eventos DJEN no caso |
| 12.1 | ✅ | Processos com caso: BH36 (35+teste), NL51; adicional sem caso BH88 identificado separadamente |
| 12.2 | ✅ | Filtro pelo nome do assistido encontra processos de caso antigo |
| 12.3 | ✅ | API restringe número/data/status/com-caso; filtros persistem na URL da tela |
| 12.4 | ✅ | Detalhe do processo possui link ao caso |
| 13.1 | ✅ | Parte UFMG sem triagem criada pela API |
| 13.2 | ✅ | Processo sem caso com CNJ real obtido do DJEN e parte UFMG |
| 13.3 | ✅ | Ficha mostra Sem triagem e campos não informados |
| 13.4 | ✅ | Variação UFMG incluída; repetição HTTP 400 |
| 13.5 | ✅ | Filtro por alias encontra processo |
| 13.6 | ✅ | Busca real retornou 3 publicações vinculadas ao processo sem caso; SQL confirma zero eventos |
| 13.7 | ✅ | Processo BH inacessível em Nova Lima |
| 14.1 | ✅ | Selecionar parte preenche nome completo e alias UFMG |
| 14.2 | ✅ | Campo único, dois meses e atalhos 7/15/30 dias; API recusa intervalo excessivo/futuro |
| 14.3 | ✅ | Busca real da tela com TRF6/TRT3 só retornou esses tribunais; requisição contém ambos |
| 14.4 | ✅ | 306 resultados reais, 20 itens por página; nenhuma gravação na busca |
| 14.5 | ✅ | Seleções preservadas entre páginas 1 e 2 |
| 14.6 | ✅ | Tela importou 2 publicações, criou processos89/90 Outros com UFMG; reimportação de publicação ligada ao88 não criou duplicatas |
| 14.7 | ✅ | Após nova consulta, tela exibe Já no sistema e Pertinente |
| 14.8 | ✅ | Não pertinente marcado via API; totais de processos e publicações não mudaram |
| 14.9 | ✅ | Publicação não pertinente importada, ganhou processo e passou a pertinente |
| 15.1 | ✅ | Cartão de exemplos e contagens por rótulo/origem consultados |
| 15.2 | ✅ | Resumo com origens vínculo manual, automático e descarte conferido após conclusão |
| 15.3 | ✅ | JSONL baixado com/sem não revisadas e conferido, mantido somente local |
| 16.1 | ✅ | Orientador vê processos sem caso e menu DJEN/Sem caso/Busca por parte; OAB e exemplos API403, rotina ausente |
| 16.2 | ◐ | Registro de presença pela tela funcionou. Lista geral de casos é ampla por desenho; equivalência de permissões com produção anterior não foi comprovada |
| 16.3 | ✅ | Estagiário vê apenas um processo de caso próprio, sem processo avulso; URL do avulso404 e Busca por parte ausente |
| 17.1 | ❌ | ENS desligado: API403 e tela mostra acesso negado genérico |
| 17.2 | ✅ | DJEN ENS habilitado localmente: publicações/OABs/exemplos vazios |
| 17.3 | ✅ | Processos ENS e busca UFMG vazios |
| 17.4 | ✅ | API responde404 para processo e publicação DAJ no ENS |
| 17.5 | ✅ | Consulta pública ENS retorna141 resultados sem marcas de importação da DAJ |

## Execução funcional de 16/11 — estado final

O ambiente local usou o pacote de **16/11**, não a cópia de 08/11 descrita no roteiro. Referência anterior às escritas: BH 3.499 atendidos / 615 casos / 35 processos; Nova Lima 587 / 335 / 51. A cópia inicialmente tinha somente a DAJ. Nenhum acesso ao servidor de produção nesta execução.

### Falhas e verificações parciais

- **7.1 e 17.1 — mesma falha de interface:** DJEN desativado mostra “Acesso negado”, sem explicar que o recurso está desligado. O bloqueio de acesso funciona.
- **3.6 — compatibilidade com dados legados:** a ficha antiga amostrada não salva sem alterações, pois faltam CPF válido e respostas obrigatórias. Os campos obrigatórios continuam sendo validados; não foram preenchidos com dados fictícios para forçar aprovação.
- **2.3 e 2.4 — comparação parcial:** casos e fichas antigos abriram e campos amostrados coincidem com o SQL restaurado. Não foi realizada comparação independente e exaustiva de todos os campos/eventos com o dump original anterior às migrations.
- **16.2 — comparação parcial:** estagiário registra presença pela tela; restrições de processos sem caso foram verificadas em 16.3. A lista geral de casos é ampla pelo comportamento atual; não se comprovou equivalência exata com o sistema anterior em produção.

### Correção operacional dos anexos

Os downloads inicialmente falharam porque os 695 arquivos ainda estavam em `uploads/casos` e `uploads/eventos`, fora da estrutura multitenant. Foi executado o script existente `scripts/mover_arquivos_tenant.py` **somente no volume local**, primeiro em dry-run e depois dentro do contêiner como root, devido às permissões do volume. Resultado: **695 movidos, zero conflitos, zero erros**. Downloads de caso e evento em BH e NL passaram; os quatro PDFs foram abertos pelo `pdfinfo`. Não se alterou a aplicação nem o banco para contornar o problema.

### DJEN real

- Rotina de 3 dias pela tela: concluída, sem novas publicações; concorrência recusada com HTTP422 e código DJEN_EM_EXECUCAO; repetição sem duplicações.
- Busca por CNJ de caso em Nova Lima: 5 novas publicações, 5 vínculos e 5 eventos.
- Processo sem caso UFMG: 3 publicações vinculadas, zero eventos (conferido por SQL).
- Busca por parte pela tela com TRF6/TRT3: 306 resultados, paginação de 20, seleções mantidas entre páginas e nenhuma gravação durante a consulta.
- Importação pela tela criou dois processos sem caso com espécie Outros; reimportação de publicação já ligada não duplicou registros. Classificação não pertinente não criou processos/publicações; importá-la depois a tornou pertinente.
- Como a janela de 3 dias não produziu itens pendentes, foi feita consulta **complementar** real pelas OABs, via CLI local, com janela de 30 dias e sem buscar processos pendentes. Trouxe 6 publicações. Não se mudou o padrão de 3 dias nem se ativou agendamento permanente.
- Vínculo manual pela tela criou evento e notificações para orientador e estagiário. Descarte e posterior vínculo passaram. Origens de exemplos manual/automática/descarte conferidas.
- Exportações JSONL com e sem não revisadas conferidas e mantidas em diretório privado local. Consulta ENS retornou 141 resultados públicos sem marcas das importações DAJ.

### Método e persistência

Foram usados navegador real, API local, SQL local somente para auditoria e consultas reais ao DJEN. Os itens feitos pela API estão identificados na tabela; **nem todos os cadastros foram digitados pelos formulários**. As verificações não equivalem a cobertura integral de toda a interface.

- Estado por item salvo continuamente em `dumps/ensaio/roteiro-resultados.json`; artefatos contendo dados pessoais, tokens, links de senha, downloads e JSONL ficam somente em `dumps/ensaio/`, ignorado pelo Git.
- Contas locais preparadas de admin, orientador e estagiário; senha do orientador alterada pelo fluxo de recuperação. Credenciais e IDs de retomada em `dumps/ensaio/estado-final.json`, com permissão 0600.
- Criados NPJ Ensaio (tenant2), unidade3, atendidos de teste4371/4372, parte UFMG4373, casos951/952 e processos87–91. DJEN habilitado em DAJ e ENS; ENS reativado. Esses registros permanecem somente nesta cópia.
- Migrations permanecem em `b3c4d5e6f7a8`. Não foi necessário novo drop/restore.
- Alterações anteriores de código/documentação preservadas. Nenhum commit realizado.

## Correção do frontend após o ensaio

Implementação local dos oito erros registrados no `npm run check`:

- `ApiException`: acesso a `captureStackTrace` condicionado à existência de uma função, compatível com navegadores sem essa extensão.
- Cliente HTTP: removido `instanceof FormData` redundante após o estreitamento para string; JSON mantém seu Content-Type e multipart deixa o navegador criar o boundary.
- Quatro carregamentos de edição: dados ainda não validados da API são explicitamente `Record<string, unknown>` antes de `superValidate`. O schema continua executando em runtime e reportando enums inválidos e campos ausentes; não foram usados casts para fingir validade, nem alteradas as regras obrigatórias. Normalização de `deferido` e datas preservada.
- Edição de usuário: removidos callbacks não recebidos pelo componente; mensagens e redirecionamento continuam a cargo do `UserForm`.
- Reactividade: iniciais do usuário, placeholders, debounce e dados de detalhe passam a acompanhar props. Formulários de edição alterados são remontados quando muda o ID, preservando o rascunho enquanto permanece o mesmo registro.

### Revisão dos avisos

A checagem passou de 41 para **25 avisos**, todos de captura de valor inicial:

- Nove inicializações de `superForm` em componentes e quatro nas páginas de autenticação/senha; uma desestruturação do formulário de login. São instâncias com estado editável, não cálculos de exibição: recriá-las em cada mudança pode perder entradas do usuário.
- Quatro capturas de defaults/seleção inicial do caso e uma seleção inicial de atendidos da orientação. A troca de registro nas páginas de edição alteradas fica protegida por `{#key id}`.
- Duas capturas dos campos editáveis de arquivo, duas na edição de evento e duas no registro de presença. Continuam explícitas no diagnóstico; não foram convertidas automaticamente para efeitos que sobrescreveriam o rascunho. A navegação entre registros dessas telas não é coberta pela nova suíte.

Os avisos não foram silenciados globalmente. O roteiro de integração foi posteriormente percorrido conforme a tabela acima. A investigação adicional dos avisos nas telas fora dos cinco formulários não integra esta execução.

### Testes npm

Nova suíte: `cd web && npm test`, com Playwright e Chrome local, servidor Vite próprio na porta 5302. API inteiramente simulada, sem gravações no banco restaurado. Instruções em `tests/browser/README.md`.

Resultados confirmados:

| Comando em `web/` | Resultado | Evidência |
|---|---|---|
| `npm run check` | **0 erros, 25 avisos em 17 arquivos** | `evidencias-ensaio-2026-11-16/frontend-corrigido-check.log` |
| `npm test` | **12 testes passaram**, em 20,7 s | `evidencias-ensaio-2026-11-16/frontend-corrigido-test.log` |
| `npm run build` | **Aprovado**, site estático gerado | `evidencias-ensaio-2026-11-16/frontend-corrigido-build.log` |
| `git diff --check` | Aprovado | Sem erros de whitespace |

Arquivos alterados formatados com Prettier. Alterações preexistentes preservadas; nenhum comando de banco, migration ou produção executado durante esta correção. O navegador usa API simulada: persistência e recarregamento são validados contra o estado sintético de cada teste, não contra o MySQL.

### Revalidação npm ao encerrar o roteiro

- `npm test`: **12 passaram**, em 20,0 s — `evidencias-ensaio-2026-11-16/frontend-roteiro-test.log`.
- `npm run check`: **0 erros, 25 avisos em 17 arquivos** — `evidencias-ensaio-2026-11-16/frontend-roteiro-check.log`.
- `git diff --check`: aprovado.

Esses 12 testes usam API simulada; os 86 itens da tabela foram avaliados separadamente no ambiente restaurado real, com as ressalvas indicadas. Build e suítes Python têm os resultados anteriores registrados acima; não foram novamente executados nesta etapa sem alterações adicionais no código.


## Correções e conferências após o plano aprovado — 16/11/2026

As ocorrências abaixo pertencem ao ensaio original e foram preservadas na tabela histórica. Esta seção registra a implementação e a revalidação posterior, sem repetir os 86 itens nem declarar nova execução integral.

| Item original | Revalidação | Evidência |
|---|---|---|
| 7.1 / 17.1 | ✅ | Página de erro lê a mensagem de `$page.error`; aviso de DJEN desabilitado confirmado na DAJ e ENS reais. API continua bloqueando o acesso. Ambos os tenants foram devolvidos ao estado habilitado anterior. |
| 3.6 | ✅ | Ficha antiga id2 salva pela tela com HTTP200; comparação de todos os campos da resposta antes/depois não encontrou alterações. |
| 2.3 / 2.4 | ✅ | Dump original restaurado em banco local temporário separado; comparação dos campos originais nas tabelas abaixo sem registros perdidos nem diferenças. |
| 16.2 | ✅ | Código anterior associado à revisão `e2f3a4b5c6d7` (commit44d9a99) já permitia listagem geral na unidade e filtro opcional por participante. Teste real: 616 casos gerais,24 em Meus casos, consulta de caso de terceiro HTTP200; outra unidade, outro NPJ e processo sem caso HTTP404. Não foi alterada essa regra. O dump não contém o SHA da aplicação implantada; a referência de código é a revisão correspondente disponível localmente. |

### Implementação

- **Mensagem de erro:** correção na página compartilhada `+error.svelte`, com regressões para DJEN desativado e falta de permissão normal. O título de status403 continua “Acesso negado”; a descrição explica a causa específica.
- **Legado:** exceção restrita a CPF e respostas procurou outro local/PJ constituída que já existiam no registro. A interface mostra as pendências, não inventa respostas e omite do PUT esses campos quando inalterados. Valores novos inválidos e limpeza de campos válidos são recusados. A API compara com o registro persistido do tenant/unidade; não aceita uma declaração de legado enviada pelo cliente. Cadastro novo e conclusão de parte sem triagem mantêm a validação normal. Outros campos incompletos continuam exigindo regularização.
- **Restauração:** o fluxo agora faz dry-run e movimentação por tenant dentro do volume do contêiner local, como root, antes de subir API/web. Conflitos interrompem o fluxo. O mover retorna1 quando houver falhas, evitando que256 conflitos se convertam em código0 no shell. Testes cobrem conflito, preservação do destino e idempotência. O teste do fluxo shell substitui Docker; o mover atua de verdade em diretório temporário. Não foi feito novo drop/restore do banco do ensaio.
- **Isolamento dos testes:** a execução combinada de casos/processos revelou referências órfãs no SQLite compartilhado. A preparação do módulo de processos remove processos de casos inexistentes e vínculos sem caso/atendido antes da reutilização dos IDs. A bateria combinada afetada passou com134 testes depois do ajuste. A execução ampliada também revelou IDs de usuários fixados em2 nos testes de casos; esses testes passaram a consultar o ID da conta autenticada.

### Comparação independente com o dump

Banco temporário local `gl_auditoria_dump_20261116`, carregado exclusivamente do pacote já baixado e removido ao terminar a comparação. Nenhum acesso à produção. Para as sete primeiras tabelas, a comparação usou o snapshot SQL anterior às escritas do ensaio. Nas restantes, comparou somente registros/colunas originais com o banco atual, excluindo registros novos do ensaio.

| Tabela | Registros originais | Diferenças/perdas |
|---|---:|---:|
| atendidos | 4086 | 0 |
| casos | 950 | 0 |
| eventos | 1183 | 0 |
| assistidos | 950 | 0 |
| arquivosCaso | 247 | 0 |
| arquivosEvento | 461 | 0 |
| assistencias_judiciarias | 1 | 0 |
| enderecos | 4359 | 0 |
| processos | 86 | 0 |
| historicos | 1461 | 0 |
| casos_atendidos | 980 | 0 |
| assistidos_pessoa_juridica | 10 | 0 |

Essa auditoria verifica preservação de dados nas tabelas listadas; não é uma comparação visual de todos os campos em todas as telas. Resultado agregado em `dumps/ensaio/comparacao-original.json`; script e evidências brutas permanecem privados em `dumps/ensaio/`.

### Validação das correções

- `npm run check`: **0 erros,25 avisos**, sem aumento de avisos em relação ao estado anterior.
- `npm test`: **17 testes passaram**, incluindo CPF legado vazio/nulo/inválido e mensagens403; API simulada.
- `npm run build`: aprovado.
- Navegador com API/MySQL reais: ficha antiga salva sem mudar dados; mensagens de DJEN desabilitado em ambos os tenants; permissões de estagiário conferidas.
- Testes de movimentação e integração do restore: **11 passaram**. O cenário de integração usa Docker substituído e arquivos reais temporários.
- `bash -n scripts/producao_para_local.sh` e `git diff --check`: aprovados.

Alterações anteriores preservadas; nenhum commit e nenhuma publicação. Credenciais e dados reais continuam somente nos artefatos locais ignorados pelo Git.


**Fechamento:** bateria Python conjunta de atendidos, PJ, isolamento de tenants, casos, processos e restore: **348 passaram**, em64,47s. Evidência: `evidencias-ensaio-2026-11-16/correcoes-python.log`. As falhas intermediárias de isolamento/IDs dos testes foram corrigidas antes desta execução final. Evidências npm, comparação do dump e navegação real estão na mesma pasta, com prefixo `correcoes-`. API, banco, frontend e Mailpit continuam em execução. Não há falha pendente nos testes executados; os25 avisos de frontend anteriores permanecem.
