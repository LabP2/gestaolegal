# Roteiro — ensaio completo: multitenant + DJEN + processos sem caso

Stack do worktree `/mnt/dados/gestaolegal-multitenant` (branch `feat/multitenant`,
já com o DJEN), com a cópia da produção de 08/11/2026 migrada até
`b3c4d5e6f7a8`. Tudo é local: e-mail vai para o Mailpit e a produção não é
tocada. O DJEN consultado é o real (só leitura).

**Atenção:** dados pessoais reais, e as publicações do DJEN trazem nomes de
terceiros. Não tire print para fora da máquina, não cole nomes em chat/issue e
não leve o arquivo exportado do banco de exemplos para fora daqui.

Backup feito antes desta etapa (para voltar atrás): `dumps/ensaio-antes-djen-20261111-080546.sql.gz`
e `dumps/uploads-antes-djen-20261111-080546.tar`.

## Acessos

| O quê | Endereço | Login |
|---|---|---|
| Sistema da DAJ | http://localhost:5301 | admin de id 1 (e-mail em `dumps/ensaio/admin-email.txt`), senha `123456` |
| Plataforma | http://localhost:5301/plataforma/login | `plataforma@local.br` / `12345678` |
| E-mails | http://localhost:8325 | — |

Totais de referência:

| | BH | Nova Lima |
|---|---|---|
| Atendidos | 3461 | 575 |
| Casos | 608 (+ os criados no ensaio anterior; hoje 612) | 333 |
| Processos (ativos + inativos) | 35 | 51 |
| Processos com número CNJ válido (casam com o DJEN) | 0 | 4 |

Como só 4 processos (todos de Nova Lima) casam com o DJEN, os itens 6.x rendem
mais em Nova Lima, e a busca por parte (9.x) é o caminho principal para BH.

Marque cada item com ✅ ou ❌ e anote o que viu.

## 1. Regressão do multitenant (rápida)

O roteiro anterior (`docs/roteiro-ensaio-producao.md`) continua valendo. Aqui só
o essencial, porque a migration nova mexeu em `processos` e `atendidos`.

| # | Ação | Esperado | |
|---|---|---|---|
| 1.1 | Entrar com o admin | sigla **DAJ**; seletor com BH e Nova Lima | |
| 1.2 | Listas de atendidos e casos em BH e em Nova Lima | totais da tabela acima | |
| 1.3 | Abrir 3 casos antigos com processo | processos, eventos e histórico como antes | |
| 1.4 | Abrir a ficha de 2 atendidos antigos (um assistido, um não) | todos os dados aparecem; nada de "Não informado" onde havia dado | |
| 1.5 | Editar um atendido antigo e salvar sem mudar nada | salva; o cadastro normal continua exigindo todos os campos | |
| 1.6 | Cadastrar um processo novo dentro de um caso | salva; aparece no caso | |

## 2. Ligar o DJEN para a DAJ

| # | Ação | Esperado | |
|---|---|---|---|
| 2.1 | Na DAJ, antes de ligar, olhar o menu e abrir http://localhost:5301/djen direto | **DJEN** não aparece no menu; pela URL, aviso de que o DJEN não está ligado para este NPJ | |
| 2.2 | Na plataforma, abrir a DAJ → cartão **Busca no DJEN** → ligar | estado "Ligada" | |
| 2.3 | Voltar à DAJ, recarregar a página (F5; se não aparecer, sair e entrar de novo) e abrir **DJEN** | lista de publicações vazia, faixa "Última sincronização" sem execução | |

## 3. OABs monitoradas (admin)

| # | Ação | Esperado | |
|---|---|---|---|
| 3.1 | **DJEN → OABs** | lista vazia e **sugestões** vindas do campo OAB dos usuários (orientadores, professores, admin) | |
| 3.2 | Cadastrar 2 ou 3 OABs reais de orientadores, por sugestão ou à mão (número + UF) | aparecem na lista, na unidade ativa | |
| 3.3 | Cadastrar a mesma OAB de novo | recusado | |
| 3.4 | Desativar e reativar uma OAB | estado muda | |

## 4. Rotina do DJEN pela tela (admin)

| # | Ação | Esperado | |
|---|---|---|---|
| 4.1 | **DJEN** → **Rodar rotina agora** | confirmação explica: todas as OABs ativas de todas as unidades, últimos 3 dias, e processos pendentes (até 15 por vez) | |
| 4.2 | Confirmar | botão "Rodando a rotina…"; ao fim, aviso com novas / vinculadas / atualizadas; lista e horário atualizados | |
| 4.3 | Clicar duas vezes seguidas (duas abas) | a segunda é recusada: "A rotina do DJEN já está rodando" | |
| 4.4 | Rodar de novo logo depois | nenhuma publicação duplicada | |

## 5. Publicações e caixa "Sem caso"

| # | Ação | Esperado | |
|---|---|---|---|
| 5.1 | Abrir uma publicação (olho) | texto completo legível, sem palavras grudadas por nossa conta; classe em maiúsculas; link para o tribunal | |
| 5.2 | **DJEN → Sem caso** | publicações das OABs que não casaram com processo | |
| 5.3 | Vincular uma delas a um processo de caso | some da caixa; vira **evento** no caso; orientador/estagiário do caso recebem **notificação** | |
| 5.4 | Descartar outra | some da caixa | |
| 5.5 | Vincular uma descartada (filtro de descartadas, se houver) | volta a valer, vinculada | |

## 6. Processo de caso e DJEN

| # | Ação | Esperado | |
|---|---|---|---|
| 6.1 | Num caso com processo de número CNJ válido, clicar no título do processo ou no olho | abre o detalhe | |
| 6.2 | Card **Publicações no DJEN** | lista carrega sozinha, sem clicar | |
| 6.3 | **Buscar publicações agora** | busca o histórico do número; publicações novas viram eventos do caso | |

## 7. Lista de processos

| # | Ação | Esperado | |
|---|---|---|---|
| 7.1 | Menu **Processos** em BH e em Nova Lima | totais batem com a tabela de referência (com "status: todos") | |
| 7.2 | Filtro por nome de assistido de um caso antigo | acha os processos do caso | |
| 7.3 | Filtros por número, distribuição de/até, status, com/sem caso | cada um restringe certo; a URL guarda os filtros | |
| 7.4 | Olho de um processo de caso | detalhe, com link para o caso | |

## 8. Parte sem triagem e processo sem caso

| # | Ação | Esperado | |
|---|---|---|---|
| 8.1 | **Processos → Novo processo sem caso** → cadastrar a parte "Universidade Federal de Minas Gerais" sem triagem (CNPJ opcional) | parte criada | |
| 8.2 | Preencher número CNJ real de um processo da UFMG, espécie, vara; salvar | processo criado, **sem caso**, com a parte | |
| 8.3 | Ficha da parte | selo **Sem triagem**; campos vazios aparecem como "Não informado" | |
| 8.4 | Seção **Nomes para o DJEN** → incluir "UFMG"; repetir o mesmo nome | inclui; repetido é recusado | |
| 8.5 | Lista de processos filtrando "UFMG" | acha o processo (pela variação do nome) | |
| 8.6 | Detalhe do processo sem caso → **Buscar publicações agora** | publicações vinculadas ao processo, **sem** criar evento | |
| 8.7 | Trocar para Nova Lima | o processo de BH não aparece | |

## 9. Busca por parte no DJEN

| # | Ação | Esperado | |
|---|---|---|---|
| 9.1 | **DJEN → Busca por parte** → escolher o atendido UFMG | nomes preenchidos com o nome e as variações | |
| 9.2 | Seletor de **período** | um campo só; dois meses; atalhos 7/15/30 dias; não passa de 30 dias nem de hoje | |
| 9.3 | **Tribunais**: marcar TRF6 e TRT3 | busca só nesses; sem nenhum marcado, busca em todos | |
| 9.4 | Buscar | resultados **paginados** (20 por página); nada gravado (a lista de publicações do DJEN não muda) | |
| 9.5 | Marcar itens em páginas diferentes | a seleção se mantém ao trocar de página | |
| 9.6 | **Importar selecionadas** | números já cadastrados são vinculados; números novos viram **processo sem caso** com a parte escolhida, espécie "Outros" | |
| 9.7 | Buscar de novo o mesmo período | importadas com selo "Já no sistema" e rótulo "Pertinente" | |
| 9.8 | Marcar outras e **Marcar como não pertinentes** | rótulo "Não pertinente"; **nenhum** processo nem publicação criados | |
| 9.9 | Importar uma que estava como não pertinente | vira pertinente e é importada | |

## 10. Banco de exemplos (admin)

| # | Ação | Esperado | |
|---|---|---|---|
| 10.1 | **DJEN** → cartão **Banco de exemplos** (abaixo da lista) | contagens: pertinentes, não pertinentes, não revisadas, por origem | |
| 10.2 | Conferir que os vínculos (5.3, 6.3) e o descarte (5.4) contaram | origem "vínculo manual/automático" e "descarte" | |
| 10.3 | **Exportar (JSONL)**, sem e com "Incluir as não revisadas" | arquivo baixa; sem a opção não vêm as não revisadas. **Não tire o arquivo da máquina.** | |

## 11. Papéis

Peça para eu trocar a senha de um orientador e de um estagiário específicos
nesta cópia.

| # | Papel | Esperado | |
|---|---|---|---|
| 11.1 | Orientador | vê **Processos** (inclusive sem caso), DJEN, Sem caso, Busca por parte; não vê OABs, "Rodar rotina agora" nem Banco de exemplos | |
| 11.2 | Estagiário | em Processos, só os dos casos dele; nenhum processo sem caso (abrir a URL de um dá "não encontrado"); não vê Busca por parte | |

## 12. Isolamento entre NPJs

Use o NPJ Teste do roteiro anterior (ou crie um), em janela anônima.

| # | Ação | Esperado | |
|---|---|---|---|
| 12.1 | NPJ Teste com DJEN desligado | DJEN fora do menu; pela URL, aviso de desligado | |
| 12.2 | Ligar o DJEN do NPJ Teste na plataforma | lista vazia; nenhuma OAB, publicação ou exemplo da DAJ | |
| 12.3 | No NPJ Teste, **Processos** e busca por "UFMG" | vazio | |
| 12.4 | Abrir no NPJ Teste a URL de um processo sem caso da DAJ e de uma publicação da DAJ | "não encontrado" | |
| 12.5 | No NPJ Teste, busca por parte "Universidade Federal de Minas Gerais" | resultados sem selo "Já no sistema" (os da DAJ não contam) | |

## Limitações conhecidas (não marcar como ❌)

- Só 4 (de 86) dos processos da produção têm número CNJ válido; os outros não
  casam com o DJEN até a correção do número (issue #205, em andamento).
- Completar o cadastro de uma parte sem triagem pela tela de edição exige todos os campos.
- O vínculo manual da caixa "Sem caso" ainda só oferece processos de caso.
- A captura automática não usa nome de parte (só OAB e número), por decisão do plano.

## Ao terminar

Devolva a lista com os ❌ e o que apareceu na tela. Para voltar ao estado
anterior ao DJEN, eu restauro o backup acima.
