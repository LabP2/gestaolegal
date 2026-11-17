# Monitoramento DJEN — entrega local de 17/11/2026

Implementação na branch `feat/multitenant`, sem commit/push nesta etapa e sem acesso à produção.

## Comportamento

- Menu **Monitoramento**, abas OAB, Nome da Parte, Número do Processo e Logs de varredura.
- A busca por parte mantém a interface e o fluxo de importação anteriores dentro da aba, com cadastro dos nomes no monitoramento.
- Busca manual avulsa por item, período e tribunais; não exige cadastro.
- Rotina por OAB e processo consulta todos os tribunais; nomes usam os tribunais cadastrados.
- Processos ativos com CNJ são incorporados automaticamente; número CNJ avulso também pode ser cadastrado.
- Pausar/remover preserva publicações, classificações e vínculos; remoção impede que a reconciliação automática recrie o monitoramento.
- Administradores veem o NPJ; demais gestores veem suas unidades. Itens iguais compartilham chamadas e dão acesso às unidades participantes.
- Sem caso passou a ser aba dentro de Publicações; saiu do menu lateral.
- Agendador Docker dedicado: diariamente 04h (7 dias), 10h/16h (3 dias), fuso America/Sao_Paulo. As janelas incluem hoje.
- Recuperação desde o último sucesso, sobreposição de datas, fila sequencial e trava por NPJ. Todas as páginas são percorridas; repetição de página sem avanço é tratada como falha.
- Logs por consulta com estados aguardando/executando/ok/parcial/erro/interrompida, períodos, tribunais, quantidades, duração e erro. Resumo de execução mantido em djen_sincronizacoes.
- Retenção configurável, padrão 90 dias. A associação permanente publicação/unidade/origem independe dos logs.

## Banco e ambiente local

Migração `19e72ac50bd8` aplicada no MySQL local: novas tabelas `djen_monitoramentos` e `djen_publicacao_unidades`, campos adicionais de logs e índice tenant/início. Migração transfere os acessos já existentes e as OABs cadastradas, preservando seu estado ativo/pausado.

Worker local instalado e em execução. A chave `DJEN_SYNC_ENABLED=false` foi preservada: não foram disparadas varreduras automáticas reais. A tela informa que a rotina está desligada; buscas manuais permanecem disponíveis. Configurações locais verificadas: janela 7, diurna 3, retenção 90.

O Compose de produção foi atualizado somente no checkout para o futuro deploy; servidor de produção não foi acessado. O cron antigo deve ser removido no ambiente que adotar o worker para evitar execuções redundantes.

## Validação

- Regressão API/banco: **1.084 passaram, 7 pulados**; os sete de MySQL foram executados separadamente.
- MySQL descartável: **6 passaram**, mais **1 teste de migração/backfill passou**.
- Verificação final direcionada (monitoramento, isolamento por unidade/NPJ, horários, paginação): **50 passaram**.
- `npm test`: **21 passaram**, incluindo cadastro, pausa e quatro abas.
- `npm run check`: **0 erros**, 25 avisos preexistentes.
- `npm run build`: aprovado.
- Verificação visual em 768 px, sem transbordamento horizontal.
- Smoke autenticado na API local: logs e status responderam HTTP 200.
- `git diff --check`: aprovado.

Evidências em `docs/evidencias-monitoramento-2026-11-17/`. Testes usam dados sintéticos e transporte DJEN simulado; não constituem ensaio de disponibilidade da API pública nos horários agendados.
