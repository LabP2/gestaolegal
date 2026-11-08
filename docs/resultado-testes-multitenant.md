# Correções e validação da multitenancy — 08/11/2026

Worktree: `/mnt/dados/gestaolegal-multitenant`, base de implementação `947661c`,
com as alterações locais desta revisão, ainda sem commit ou push.
Comparação do frontend: `b8f2f8d`, usando as mesmas dependências do container.
API/web/Mailpit locais: 5300/5301/8325. Nenhum acesso a QA, produção ou dumps.

## Correções entregues no worktree

1. Guarda valida UNION por ramo, inclusive em subqueries, e resolve binds
   nomeados/anônimos com os parâmetros efetivos. UPDATE e DELETE em lote,
   ordered_values e INSERT parametrizado têm testes de regressão. Construções
   sem suporte e SQL textual encapsulado são recusados antes da execução.
2. Links comuns e de primeiro acesso não validam nem alteram a senha enquanto
   o NPJ estiver inativo. Os testes conferem o hash intacto e o comportamento
   depois da reativação.
3. Coleções exigem HTTP 200; leituras por ID só admitem 200/403/404, com o
   controle de ID inexistente nas sublistas. Um teste prova que HTTP 500 é
   recusado pelos validadores. Há ataques nos dois sentidos entre NPJs.
4. A fixture da varredura restaura o banco ao sair: a ordem inversa inicialmente
   revelou interferência entre módulos, corrigida sem relaxar as asserções.
5. M3 preserva os nomes das quatro FKs legadas que determinam os nomes dos
   índices simples no MySQL. O esquema inteiro é comparado no round-trip.
6. Importador BH/Nova Lima e seus testes exclusivos removidos, conforme decisão
   de descontinuação após a fusão concluída. Histórico preservado em
   `docs/unidades.md` e no Git.

## Resultados automatizados

| Verificação | Resultado | Evidência / alcance |
|---|---|---|
| A1 — suíte completa | Passou | `845 passed, 2 skipped` em 135,57 s; os dois skips são os ensaios MySQL, executados separadamente abaixo |
| A2 — Alembic | Passou | Head único `c2d3e4f5a6b7` |
| A3 — frontend check | Falha preexistente, sem regressão | 21 erros e 42 avisos na branch; mesmos 21 erros na base. Comparação de arquivo e mensagem, não apenas quantidade |
| A4 — frontend lint | Falha preexistente, sem regressão | `anexos-evento.svelte` e `processo-schema.ts`, também fora do padrão na base |
| A5 — quatro módulos de segurança nas duas ordens | Passou | 180 testes em cada ordem; não é uma afirmação de independência de ordem de toda a suíte |
| G1 — baseline → M2 → seed de dois NPJs → M3 | Passou | 28 tabelas com tenant NOT NULL; todas as 53 FKs compostas conferidas no MySQL |
| G2 — referência cruzada antes da M3 | Passou | Recusa identifica `plantao.unidade_id`; esquema e revisão M2 intactos |
| G3 — referência cruzada após a M3 | Passou | INSERT e UPDATE recusados com erro MySQL 1452 |
| G4 — downgrade M3 e novo upgrade | Passou | Igualdade de colunas, PKs, FKs, ações e nomes dos índices; `arquivosCaso.id_caso` preserva CASCADE |
| G5 — downgrade M2 com segundo NPJ | Passou | Recusa com “Remova-os antes do downgrade”; M3 é reaplicada após a recusa |
| API com guarda e FKs MySQL | Passou | Login nos dois NPJs; leitura/exclusão/referência cruzadas nos dois sentidos; separação plataforma/NPJ; criação de NPJ e primeiro acesso; bloqueio de link e JWT com NPJ inativo |
| Seed após M3 | Passou | Nova execução não cria registros adicionais |
| `git diff --check` | Passou | Sem erros de whitespace |

Comandos principais:

```bash
uv run pytest tests/ -q -p no:cacheprovider
MULTITENANT_MYSQL_TEST=1 uv run pytest tests/database/test_multitenant_mysql.py -v
uv run pytest tests/api/test_tenant_isolamento.py tests/api/test_tenant_guarda.py tests/api/test_password_reset_api.py tests/api/test_tenant_vazamento.py -q
uv run pytest tests/api/test_tenant_vazamento.py tests/api/test_password_reset_api.py tests/api/test_tenant_guarda.py tests/api/test_tenant_isolamento.py -q
docker compose -f docker-compose.dev.yml exec -T web npm run check
docker compose -f docker-compose.dev.yml exec -T web npm run lint
```

O teste MySQL cria seus próprios containers `mysql:8.0.42`, portas aleatórias
em loopback e armazenamento tmpfs, sem aceitar URL de banco existente. Ambos
os ensaios passaram; os containers foram removidos pelo `finally`. Os testes
da API usam o cliente Flask e suprimem SMTP, sem enviar e-mail real.

Logs desta execução disponíveis em `/tmp/mt-fix-full-final.log`,
`/tmp/mt-fix-reverse.log`, `/tmp/mt-fix-mysql.log`,
`/tmp/mt-fix-front-check.log` e `/tmp/mt-fix-front-lint.log`.

## Limites e pendências

- Os fluxos de navegador P1–P8/E1–E7 não foram executados nesta rodada.
  A ferramenta de navegador não encontrou nenhuma superfície disponível e
  recusou criar uma aba (`Browser is not available: iab`). Foi solicitada a
  alternativa Playwright/Chrome; a resposta permanece pendente.
- B1–B12/C1–C7/F1–F3 não foram repetidos integralmente como roteiro manual.
  Os módulos de API, JWT, referências, senha, armazenamento e migração de
  arquivos fazem parte da suíte verde; isso não substitui verificar a interface
  nem os links enviados pelo Mailpit em navegador.
- A guarda continua verificando presença de critério, sem provar a semântica
  booleana de OR/CASE (limitação conhecida do plano). As correções de UNION e
  binds não equivalem a RLS no banco.
- O PR remoto #425 ainda termina em `4179632` (somente PRs 1–2). A descrição
  completa está preparada em `docs/descricao-pr-multitenant.md`; não foi
  publicada como se os commits posteriores já estivessem no diff remoto.
- Nenhum commit, push ou alteração de workflow foi realizado. Migrations,
  autenticação e filtros continuam sujeitos à revisão antes do merge.
