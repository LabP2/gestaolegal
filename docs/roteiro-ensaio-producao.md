# Roteiro — ensaio do multitenant com a cópia da produção

Stack do worktree `/mnt/dados/gestaolegal-multitenant` com o banco e os anexos da
produção de 08/11/2026, já migrados até `c2d3e4f5a6b7`. Tudo é local: nenhum
e-mail sai (vai para o Mailpit), e a produção não é tocada.

**Atenção:** são dados pessoais reais. Não tire print para fora da máquina nem
cole nomes em chat/issue.

## Acessos

| O quê | Endereço | Login |
|---|---|---|
| Sistema da DAJ | http://localhost:5301 | admin de id 1 (e-mail em `dumps/ensaio/admin-email.txt`), senha `123456` — trocada só nesta cópia |
| Plataforma | http://localhost:5301/plataforma/login | `plataforma@local.br` / `12345678` |
| E-mails | http://localhost:8325 | — |

Totais de referência (contados no banco antes da migration):

| | BH | Nova Lima |
|---|---|---|
| Atendidos | 3461 | 575 |
| Casos | 608 | 333 |

Marque cada item com ✅ ou ❌ e anote o que viu.

## 1. Entrada na DAJ

| # | Ação | Esperado | |
|---|---|---|---|
| 1.1 | Entrar com o admin | cabeçalho com a sigla **DAJ**; seletor com BH e Nova Lima | |
| 1.2 | Abrir `/setup-admin` | página inexistente | |
| 1.3 | Sair e entrar de novo com senha errada | mensagem de credenciais inválidas | |

## 2. Dados preservados

Faça em BH e repita em Nova Lima, trocando pelo seletor.

| # | Ação | Esperado | |
|---|---|---|---|
| 2.1 | Lista de atendidos | total igual à tabela acima | |
| 2.2 | Lista de casos | total igual à tabela acima; estagiário e assistido aparecem | |
| 2.3 | Abrir 3 casos antigos quaisquer | dados, processos, eventos e histórico como na produção | |
| 2.4 | Baixar anexos de um caso e de um evento | o arquivo abre. Exceção já conhecida: anexo herdado da 2.0 marcado como "indisponível no acervo original" | |
| 2.5 | Busca geral por um nome ou número de processo que você conheça | encontra | |
| 2.6 | Usuários, orientações jurídicas, plantão, fila, registro de entrada, notificações, relatórios, arquivos gerais | abrem sem erro, com os dados de sempre | |
| 2.7 | Assistência judiciária (parceiros) | lista igual à da produção | |

## 3. Escrita no NPJ existente

Os registros criados aqui ficam só nesta cópia.

| # | Ação | Esperado | |
|---|---|---|---|
| 3.1 | Cadastrar um atendido "Teste Ensaio" em BH | salva; aparece em BH e não em Nova Lima | |
| 3.2 | Abrir um caso para ele, com orientador e estagiário | salva; aparece na lista | |
| 3.3 | Criar um evento no caso e anexar um PDF qualquer | salva; o anexo baixa | |
| 3.4 | Editar um caso antigo (ex.: mudar a descrição) e desfazer | salva; o histórico registra | |
| 3.5 | Recuperar senha de um usuário pela tela de login | o e-mail chega no Mailpit, e o link funciona | |

## 4. Plataforma

| # | Ação | Esperado | |
|---|---|---|---|
| 4.1 | Entrar na plataforma | lista só com a DAJ, ativa | |
| 4.2 | Tentar entrar na plataforma com o admin da DAJ | recusado | |
| 4.3 | Criar um NPJ "NPJ Teste" (sigla `TESTE`, slug `npj-teste`, uma unidade, admin com e-mail inventado, ex. `admin@npjteste.br`) | a tela mostra o **link de primeiro acesso** | |
| 4.4 | Criar outro NPJ repetindo a sigla `daj` ou o slug `npj-teste` | recusado; nada criado pela metade | |

## 5. Isolamento entre os NPJs

Use uma janela anônima para o NPJ Teste e mantenha a DAJ na janela normal.

| # | Ação | Esperado | |
|---|---|---|---|
| 5.1 | Abrir o link de 4.3, definir a senha e entrar | sigla **TESTE**; listas vazias; só a unidade criada | |
| 5.2 | No NPJ Teste, cadastrar um atendido e um caso | salvam | |
| 5.3 | Na DAJ, procurar esse atendido pela busca | não aparece | |
| 5.4 | Copiar a URL de um caso da DAJ e abrir na janela do NPJ Teste | "não encontrado", sem mostrar dado | |
| 5.5 | No NPJ Teste, busca por um nome comum (ex.: "Maria") | só resultados do NPJ Teste (nenhum, ou o seu cadastro) | |
| 5.6 | No NPJ Teste, lista de usuários | só o admin dele | |

## 6. Desativação de NPJ

| # | Ação | Esperado | |
|---|---|---|---|
| 6.1 | Na plataforma, desativar o NPJ Teste | estado passa a inativo | |
| 6.2 | Na janela anônima (já logada), recarregar | sessão cai | |
| 6.3 | Tentar entrar de novo como admin do NPJ Teste | recusado | |
| 6.4 | Na DAJ | segue normal | |
| 6.5 | Reativar o NPJ Teste | login volta a funcionar | |

## 7. Outros perfis da DAJ (opcional)

Para entrar como orientador ou estagiário sem saber a senha deles, peça para eu
trocar a senha de um usuário específico nesta cópia.

| # | Ação | Esperado | |
|---|---|---|---|
| 7.1 | Orientador | vê os casos de sempre | |
| 7.2 | Estagiário | vê só o que via antes; registro de entrada funciona | |

## Ao terminar

Devolva a lista com os ❌ e o que apareceu na tela. Para voltar ao estado de
antes do ensaio, eu restauro o backup local (`dumps/local-antes-*.sql.gz` e
`dumps/uploads-antes-*`) e religo a stack do checkout principal.
