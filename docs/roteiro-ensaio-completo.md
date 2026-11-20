# Roteiro — ensaio completo: multitenant + DJEN + processos sem caso

Substitui `roteiro-ensaio-producao.md` e `roteiro-ensaio-djen.md`.

Stack do worktree `/mnt/dados/gestaolegal-multitenant` (branch `feat/multitenant`,
já com o DJEN), com o banco e os anexos da produção de 08/11/2026 migrados até
`b3c4d5e6f7a8`. Tudo é local: e-mail vai para o Mailpit e a produção não é
tocada. O DJEN consultado é o real (só leitura).

**Atenção:** dados pessoais reais, e as publicações do DJEN trazem nomes de
terceiros. Não tire print para fora da máquina, não cole nomes em chat/issue e
não leve o arquivo exportado do banco de exemplos para fora daqui.

Backup feito antes do DJEN (para voltar atrás): `dumps/ensaio-antes-djen-20261111-080546.sql.gz`
e `dumps/uploads-antes-djen-20261111-080546.tar`.

## Acessos

| O quê | Endereço | Login |
|---|---|---|
| Sistema da DAJ | http://localhost:5301 | admin de id 1 (e-mail em `dumps/ensaio/admin-email.txt`), senha `123456` (trocada só nesta cópia) |
| Plataforma | http://localhost:5301/plataforma/login | `plataforma@local.br` / `12345678` |
| E-mails | http://localhost:8325 | — |

Totais de referência:

| | BH | Nova Lima |
|---|---|---|
| Atendidos | 3461 | 575 |
| Casos | 612 (608 da produção + 4 criados no ensaio anterior) | 333 |
| Processos (ativos + inativos) | 35 | 51 |
| Processos com número CNJ válido (casam com o DJEN) | 0 | 4 |

A cópia já tem, além da DAJ, quatro NPJs de testes anteriores (`NPJD`, `TESTE`,
`NAV`, `XX5`). Neste ensaio você cria um novo, o **NPJ Ensaio**, usado no
isolamento (partes 5, 6 e 17).

Marque cada item com ✅ ou ❌ e anote o que viu.

---

# Parte A — Multitenant

## 1. Entrada na DAJ

| # | Ação | Esperado | |
|---|---|---|---|
| 1.1 | Entrar com o admin | cabeçalho com a sigla **DAJ**; seletor com BH e Nova Lima | |
| 1.2 | Abrir `/setup-admin` | página inexistente | |
| 1.3 | Sair e entrar de novo com senha errada | mensagem de credenciais inválidas | |
| 1.4 | Olhar o menu | **Processos** aparece; **DJEN** ainda não (está desligado) | |

## 2. Dados preservados

Faça em BH e repita em Nova Lima, trocando pelo seletor.

| # | Ação | Esperado | |
|---|---|---|---|
| 2.1 | Lista de atendidos | total igual à tabela acima | |
| 2.2 | Lista de casos | total igual à tabela acima; estagiário e assistido aparecem | |
| 2.3 | Abrir 3 casos antigos com processo | dados, processos, eventos e histórico como na produção | |
| 2.4 | Ficha de 2 atendidos antigos (um assistido, um não) | todos os dados aparecem; nada de "Não informado" onde havia dado | |
| 2.5 | Baixar anexos de um caso e de um evento | o arquivo abre. Exceção já conhecida: anexo herdado da 2.0 marcado como "indisponível no acervo original" | |
| 2.6 | Busca geral por um nome ou número de processo que você conheça | encontra | |
| 2.7 | Usuários, orientações jurídicas, plantão, fila, registro de entrada, notificações, relatórios, arquivos gerais | abrem sem erro, com os dados de sempre | |
| 2.8 | Assistência judiciária (parceiros) | lista igual à da produção | |

## 3. Escrita na DAJ

Os registros criados aqui ficam só nesta cópia.

| # | Ação | Esperado | |
|---|---|---|---|
| 3.1 | Cadastrar um atendido "Teste Ensaio" em BH | salva; aparece em BH e não em Nova Lima | |
| 3.2 | Abrir um caso para ele, com orientador e estagiário | salva; aparece na lista | |
| 3.3 | Cadastrar um processo nesse caso | salva; aparece no caso | |
| 3.4 | Criar um evento no caso e anexar um PDF qualquer | salva; o anexo baixa | |
| 3.5 | Editar um caso antigo (ex.: mudar a descrição) e desfazer | salva; o histórico registra | |
| 3.6 | Editar um atendido antigo e salvar sem mudar nada | salva; o cadastro normal continua exigindo todos os campos | |
| 3.7 | Recuperar senha de um usuário pela tela de login | o e-mail chega no Mailpit, e o link funciona | |

## 4. Plataforma

| # | Ação | Esperado | |
|---|---|---|---|
| 4.1 | Entrar na plataforma | lista com a DAJ e os NPJs de testes anteriores | |
| 4.2 | Tentar entrar na plataforma com o admin da DAJ | recusado | |
| 4.3 | Criar o NPJ "NPJ Ensaio" (sigla `ENS`, slug `npj-ensaio`, uma unidade, admin com e-mail inventado, ex. `admin@npjensaio.br`) | a tela mostra o **link de primeiro acesso** | |
| 4.4 | Criar outro NPJ repetindo a sigla `daj` ou o slug `npj-ensaio` | recusado; nada criado pela metade | |

## 5. Isolamento entre os NPJs

Use uma janela anônima para o NPJ Ensaio e mantenha a DAJ na janela normal.

| # | Ação | Esperado | |
|---|---|---|---|
| 5.1 | Abrir o link de 4.3, definir a senha e entrar | sigla **ENS**; listas vazias; só a unidade criada | |
| 5.2 | No NPJ Ensaio, cadastrar um atendido e um caso | salvam | |
| 5.3 | Na DAJ, procurar esse atendido pela busca | não aparece | |
| 5.4 | Copiar a URL de um caso da DAJ e abrir na janela do NPJ Ensaio | "não encontrado", sem mostrar dado | |
| 5.5 | No NPJ Ensaio, busca por um nome comum (ex.: "Maria") | só resultados do NPJ Ensaio (nenhum, ou o seu cadastro) | |
| 5.6 | No NPJ Ensaio, lista de usuários | só o admin dele | |
| 5.7 | No NPJ Ensaio, menu **Processos** | lista vazia | |

## 6. Desativação de NPJ

| # | Ação | Esperado | |
|---|---|---|---|
| 6.1 | Na plataforma, desativar o NPJ Ensaio | estado passa a inativo | |
| 6.2 | Na janela anônima (já logada), recarregar | sessão cai | |
| 6.3 | Tentar entrar de novo como admin do NPJ Ensaio | recusado | |
| 6.4 | Na DAJ | segue normal | |
| 6.5 | Reativar o NPJ Ensaio | login volta a funcionar (ele é usado de novo na parte 17) | |

---

# Parte B — DJEN e processos sem caso

## 7. Ligar o DJEN para a DAJ

| # | Ação | Esperado | |
|---|---|---|---|
| 7.1 | Na DAJ, antes de ligar, abrir http://localhost:5301/djen direto | aviso de que o DJEN não está ligado para este NPJ | |
| 7.2 | Na plataforma, abrir a DAJ → cartão **Busca no DJEN** → ligar | estado "Ligada" | |
| 7.3 | Voltar à DAJ e recarregar (F5; se não aparecer, sair e entrar de novo) | **DJEN** aparece no menu | |
| 7.4 | Abrir **DJEN** | lista de publicações vazia; faixa "Última sincronização" sem execução | |

## 8. OABs monitoradas (admin)

| # | Ação | Esperado | |
|---|---|---|---|
| 8.1 | **DJEN → OABs** | lista vazia e **sugestões** vindas do campo OAB dos usuários (orientadores, professores, admin) | |
| 8.2 | Cadastrar 2 ou 3 OABs reais de orientadores, por sugestão ou à mão (número + UF) | aparecem na lista, na unidade ativa | |
| 8.3 | Cadastrar a mesma OAB de novo | recusado | |
| 8.4 | Desativar e reativar uma OAB | estado muda | |

## 9. Rotina do DJEN pela tela (admin)

| # | Ação | Esperado | |
|---|---|---|---|
| 9.1 | **DJEN** → **Rodar rotina agora** | a confirmação explica: todas as OABs ativas de todas as unidades, últimos 3 dias, e processos pendentes (até 15 por vez) | |
| 9.2 | Confirmar | botão "Rodando a rotina…"; ao fim, aviso com novas / vinculadas / atualizadas; lista e horário atualizados | |
| 9.3 | Clicar duas vezes seguidas (duas abas) | a segunda é recusada: "A rotina do DJEN já está rodando" | |
| 9.4 | Rodar de novo logo depois | nenhuma publicação duplicada | |

## 10. Publicações e caixa "Sem caso"

| # | Ação | Esperado | |
|---|---|---|---|
| 10.1 | Abrir uma publicação (olho) | texto completo legível, sem palavras grudadas por nossa conta; classe em maiúsculas; link para o tribunal | |
| 10.2 | **DJEN → Sem caso** | publicações das OABs que não casaram com processo | |
| 10.3 | Vincular uma delas a um processo de caso | some da caixa; vira **evento** no caso; orientador/estagiário do caso recebem **notificação** | |
| 10.4 | Descartar outra | some da caixa | |
| 10.5 | Vincular uma descartada (filtro de descartadas, se houver) | volta a valer, vinculada | |

## 11. Processo de caso e DJEN

Rende mais em Nova Lima (únicos processos com CNJ válido).

| # | Ação | Esperado | |
|---|---|---|---|
| 11.1 | Num caso com processo de número CNJ válido, clicar no título do processo ou no olho | abre o detalhe | |
| 11.2 | Card **Publicações no DJEN** | a lista carrega sozinha, sem clicar | |
| 11.3 | **Buscar publicações agora** | busca o histórico do número; publicações novas viram eventos do caso | |

## 12. Lista de processos

| # | Ação | Esperado | |
|---|---|---|---|
| 12.1 | Menu **Processos** em BH e em Nova Lima, com "status: todos" | totais batem com a tabela de referência (BH +1 pelo processo de 3.3) | |
| 12.2 | Filtro por nome de assistido de um caso antigo | acha os processos do caso | |
| 12.3 | Filtros por número, distribuição de/até, status, com/sem caso | cada um restringe certo; a URL guarda os filtros | |
| 12.4 | Olho de um processo de caso | detalhe, com link para o caso | |

## 13. Parte sem triagem e processo sem caso

| # | Ação | Esperado | |
|---|---|---|---|
| 13.1 | **Processos → Novo processo sem caso** → cadastrar a parte "Universidade Federal de Minas Gerais" sem triagem (CNPJ opcional) | parte criada | |
| 13.2 | Preencher número CNJ real de um processo da UFMG, espécie, vara; salvar | processo criado, **sem caso**, com a parte | |
| 13.3 | Ficha da parte | selo **Sem triagem**; campos vazios aparecem como "Não informado" | |
| 13.4 | Seção **Nomes para o DJEN** → incluir "UFMG"; repetir o mesmo nome | inclui; o repetido é recusado | |
| 13.5 | Lista de processos filtrando "UFMG" | acha o processo (pela variação do nome) | |
| 13.6 | Detalhe do processo sem caso → **Buscar publicações agora** | publicações vinculadas ao processo, **sem** criar evento | |
| 13.7 | Trocar para Nova Lima | o processo de BH não aparece | |

## 14. Busca por parte no DJEN

| # | Ação | Esperado | |
|---|---|---|---|
| 14.1 | **DJEN → Busca por parte** → escolher o atendido UFMG | nomes preenchidos com o nome e as variações | |
| 14.2 | Seletor de **período** | um campo só; dois meses; atalhos 7/15/30 dias; não passa de 30 dias nem de hoje | |
| 14.3 | **Tribunais**: marcar TRF6 e TRT3 | busca só nesses; sem nenhum marcado, busca em todos | |
| 14.4 | Buscar | resultados **paginados** (20 por página); nada gravado (a lista de publicações do DJEN não muda) | |
| 14.5 | Marcar itens em páginas diferentes | a seleção se mantém ao trocar de página | |
| 14.6 | **Importar selecionadas** | números já cadastrados são vinculados; números novos viram **processo sem caso** com a parte escolhida, espécie "Outros" | |
| 14.7 | Buscar de novo o mesmo período | importadas com selo "Já no sistema" e rótulo "Pertinente" | |
| 14.8 | Marcar outras e **Marcar como não pertinentes** | rótulo "Não pertinente"; **nenhum** processo nem publicação criados | |
| 14.9 | Importar uma que estava como não pertinente | vira pertinente e é importada | |

## 15. Banco de exemplos (admin)

| # | Ação | Esperado | |
|---|---|---|---|
| 15.1 | **DJEN** → cartão **Banco de exemplos** (abaixo da lista) | contagens: pertinentes, não pertinentes, não revisadas, por origem | |
| 15.2 | Conferir que os vínculos (10.3, 11.3) e o descarte (10.4) contaram | origem "vínculo manual/automático" e "descarte" | |
| 15.3 | **Exportar (JSONL)**, sem e com "Incluir as não revisadas" | o arquivo baixa; sem a opção não vêm as não revisadas. **Não tire o arquivo da máquina.** | |

---

# Parte C — Papéis e isolamento do DJEN

## 16. Outros perfis da DAJ

Peça para eu trocar a senha de um orientador e de um estagiário específicos
nesta cópia.

| # | Papel | Esperado | |
|---|---|---|---|
| 16.1 | Orientador | vê os casos de sempre; vê **Processos** (inclusive sem caso), DJEN, Sem caso, Busca por parte; não vê OABs, "Rodar rotina agora" nem Banco de exemplos | |
| 16.2 | Estagiário | vê só o que via antes; registro de entrada funciona | |
| 16.3 | Estagiário em Processos | só os dos casos dele; nenhum processo sem caso (abrir a URL de um dá "não encontrado"); não vê Busca por parte | |

## 17. Isolamento do DJEN entre NPJs

Use o NPJ Ensaio (reativado em 6.5), em janela anônima.

| # | Ação | Esperado | |
|---|---|---|---|
| 17.1 | NPJ Ensaio com DJEN desligado | DJEN fora do menu; pela URL `/djen`, aviso de desligado | |
| 17.2 | Ligar o DJEN do NPJ Ensaio na plataforma e recarregar | lista vazia; nenhuma OAB, publicação ou exemplo da DAJ | |
| 17.3 | No NPJ Ensaio, **Processos** e busca por "UFMG" | vazio | |
| 17.4 | Abrir no NPJ Ensaio a URL de um processo sem caso da DAJ e de uma publicação da DAJ | "não encontrado" | |
| 17.5 | No NPJ Ensaio, busca por parte "Universidade Federal de Minas Gerais" | resultados sem selo "Já no sistema" (os da DAJ não contam) | |

## Limitações conhecidas (não marcar como ❌)

- Só 4 (de 86) dos processos da produção têm número CNJ válido; os outros não
  casam com o DJEN até a correção do número (issue #205, em andamento).
- Anexo herdado da 2.0 sem arquivo no acervo aparece como "indisponível no acervo original".
- Completar o cadastro de uma parte sem triagem pela tela de edição exige todos os campos.
- O vínculo manual da caixa "Sem caso" ainda só oferece processos de caso.
- A captura automática não usa nome de parte (só OAB e número), por decisão do plano.

## Ao terminar

Devolva a lista com os ❌ e o que apareceu na tela. Para voltar ao estado
anterior ao DJEN, eu restauro o backup acima.
