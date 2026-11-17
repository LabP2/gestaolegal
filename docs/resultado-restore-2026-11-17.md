# Restore local e regressão — 17/11/2026

Restauração concluída exclusivamente na stack local do checkout
`gestaolegal-multitenant`. Nenhum acesso SSH, dump novo ou alteração no servidor
de produção foi realizado.

## Restauração

- Pacote existente: `dumps/producao-20261116-142931.tar`, validado pelos hashes.
- Destino: MySQL do Docker local, banco `gestaolegal`, porta 3606.
- Banco anterior salvo em `dumps/local-antes-20261117-073705.sql.gz`.
- Anexos anteriores preservados em `dumps/uploads-antes-20261117-073705`.
- Banco local removido, recriado e carregado do dump.
- Todas as migrations aplicadas de `e2f3a4b5c6d7` até **`19e72ac50bd8`**.
- 695 anexos reorganizados para o layout por tenant, sem conflitos ou erros.
- API em localhost:5300, frontend em localhost:5301 e Mailpit em localhost:8325.
- Captura periódica DJEN permanece desabilitada (`DJEN_SYNC_ENABLED=False`).
- Aviso esperado da migration: 82 processos legados sem número CNJ válido;
  seus números e registros foram preservados.

O disco apresentou forte concorrência de I/O. Com autorização do usuário, o
Dropbox foi parado durante a restauração e retomado ao final, confirmado pelo
status de sincronização. Os ajustes temporários de durabilidade do MySQL foram
revertidos: `innodb_flush_log_at_trx_commit=1` e `sync_binlog=1`.

## Preservação dos dados

Uma segunda cópia do SQL original foi carregada em MySQL descartável, com dados
em tmpfs e rede desabilitada. Antes das escritas do ensaio, foram comparadas
todas as colunas originais das 12 tabelas abaixo. Não houve diferença nem perda.

| Tabela | Registros originais e restaurados |
|---|---:|
| atendidos | 4086 |
| casos | 950 |
| eventos | 1183 |
| assistidos | 950 |
| arquivosCaso | 247 |
| arquivosEvento | 461 |
| assistencias_judiciarias | 1 |
| enderecos | 4359 |
| processos | 86 |
| historicos | 1461 |
| casos_atendidos | 980 |
| assistidos_pessoa_juridica | 10 |

Os **695 arquivos** foram comparados por SHA-256 com o pacote:
**695 idênticos, nenhum ausente, nenhum diferente**.
O MySQL de auditoria foi removido.

## Testes

| Verificação | Resultado |
|---|---|
| Suíte Python completa `pytest tests` | 1172 aprovados, 1 falha de expectativa de configuração, 7 pulados |
| Correção e reteste da configuração Compose | 2 aprovados; a falha acima foi resolvida |
| Total de testes Python regulares aprovados, considerando o reteste | 1173 |
| MySQL descartável com `MULTITENANT_MYSQL_TEST=1` | 7 aprovados; cobre os 7 pulados na suíte padrão |
| `npm run check` | 0 erros, 25 avisos preexistentes |
| `npm test` | 22 aprovados |
| `npm run build` | Aprovado |
| Entrada no navegador com API real | 5 verificações aprovadas |
| API real com MySQL restaurado | 62 verificações HTTP aprovadas |
| Navegação real em BH e Nova Lima | 20 páginas, nenhuma falha, nenhum erro JavaScript |
| `git diff --check` | Aprovado |

A única alteração de código desta rodada foi no teste
`tests/config/test_compose.py`: ele ainda esperava a stack anterior, sem
`djen-worker`. Agora inclui o worker e verifica comando, dependência da
migration, host do banco e montagem dos scripts em modo somente leitura.
A suíte completa não foi repetida depois dessa alteração restrita ao teste;
os dois testes de configuração foram reexecutados e passaram.

O ensaio real incluiu login correto/incorreto, ausência de setup-admin, mensagem
de DJEN desativado, leitura nas duas unidades, bootstrap da plataforma, criação
e primeiro acesso ao NPJ Ensaio, duplicidade recusada, isolamento entre NPJs,
desativação e reativação, e acesso às páginas do acervo e monitoramento.

Também foi verificado no MySQL restaurado o fluxo de processo sem caso com duas
publicações sintéticas anteriores: a associação criou **2 eventos**; a repetição
criou **0**, mantendo apenas dois eventos no caso. O outro NPJ não acessou esse
processo.

## Estado final e alcance

Foram recriados acessos locais de ensaio e deixados registros sintéticos de
teste, incluindo o NPJ Ensaio e um processo associado a um caso com duas
publicações. Os dados originais foram auditados antes dessas escritas.

Os testes DJEN desta rodada usaram dados sintéticos, sem novas consultas ao
serviço externo da Justiça. A navegação real verificou carregamento e ausência
de erros; não equivale à repetição manual de cada interação do roteiro antigo
de 86 itens, que contém telas e comportamentos já substituídos.

Evidências agregadas em [evidencias-restore-2026-11-17](evidencias-restore-2026-11-17/).
Scripts e estado de autenticação do ensaio permanecem privados, ignorados pelo
Git, em `dumps/ensaio-20261117/`. Falhas intermediárias de prontidão do frontend,
seletores antigos e leitura de resposta 401 em texto foram corrigidas no
harness de ensaio; as verificações finais acima passaram.
