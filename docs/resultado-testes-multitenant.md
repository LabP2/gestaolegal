# Resultado do roteiro de testes — multitenancy

Execução de [roteiro-testes-multitenant.md](roteiro-testes-multitenant.md)
contra a stack local deste worktree, cujo banco é a **cópia da produção de
08/11/2026** (tenant 1, `daj-ufmg`), já migrada até `c2d3e4f5a6b7`. Este
arquivo substitui o relatório da revisão anterior, feita sobre o seed.

## 1. Ambiente

| Item | Valor |
|---|---|
| Commit testado | `9060352 perf(multitenant): M2 e M3 com um ALTER TABLE por tabela` |
| Data | 08/11/2026 |
| API / web / Mailpit | 5300 / 5301 / 8325 (MySQL em 3606) |
| Head do Alembic no banco | `c2d3e4f5a6b7` |
| Navegador | Playwright + Google Chrome do host (a extensão Claude in Chrome não conectou) |

Adaptações ao roteiro, por causa da base real:

- A DAJ **não** recebeu o seed. Entrei com o admin real de id 1 (senha `123456`,
  trocada só nesta cópia). Para E7 defini, pelo admin, a senha de um usuário
  real de cada papel (`orient`, `estag_direito`, `colab_ext`) que atua em BH e
  Nova Lima. Essas senhas só existem nesta cópia.
- O NPJ Demo foi criado com `seed_database.py --tenant npj-demo`, que não toca
  o tenant 1.
- O NPJ Teste foi criado pela API da plataforma. A política de senha exige 8
  caracteres, então as contas `@npjteste.br` ficaram com `Teste1234`
  (a estagiária terminou com `Nova12345`, após C7), e não `123456`.
- Nenhum nome, CPF ou e-mail real aparece aqui. Ids numéricos de registros da
  DAJ foram omitidos.
- Registros criados pelo roteiro e deixados no banco local: tenants `npj-teste`
  (3), `npj-nav` (4) e `npj-x5` (7, ver achado 4.3.1); no Demo, atendido
  "Teste Ensaio Demo", casos 948 a 951, um evento com anexo, uma assistência
  judiciária, dois anexos de F1. A DAJ permaneceu com 4036 atendidos, 945
  casos e 244 usuários, iguais ao início.

## 2. Resultado por teste

| # | Resultado | Observação |
|---|---|---|
| A1 | passou | `846 passed, 2 skipped` em 134 s; os dois skips são o ensaio MySQL (G) |
| A2 | passou | head único `c2d3e4f5a6b7` |
| A3 | passou | 21 erros na branch e 21 na base `b8f2f8d` (mesmas dependências, via worktree temporário); comparação por arquivo e mensagem: nenhum erro novo nem removido |
| A4 | passou | só `anexos-evento.svelte` e `processo-schema.ts` |
| A5 | passou | 181 testes em cada ordem, ambas verdes |
| B1 | passou | cada token vê o próprio e-mail e a sigla do próprio NPJ (`DAJ`, `NPJD`) |
| B2 | passou | 403 "Você não tem acesso à unidade informada" |
| B3 | passou | 404 `ATENDIDO_NOT_FOUND` |
| B4 | passou | 404 em caso, processo, evento, lembrete, orientação, assistência judiciária, arquivo de caso (lista e download) e usuário. Sublistas `/atendido/<id>/casos`, `/atendido/<id>/orientacoes` e `/caso/<id>/historico` respondem 200 com lista vazia (ver 4.3.2) |
| B5 | passou | PUT, DELETE, PATCH (deferir/indeferir, notificação lida/arquivada), fila (chamar/cancelar), tornar-assistido, troca de senha administrativa: todos 404 com token do Demo. Hash das nove tabelas da DAJ conferido antes e depois: idêntico |
| B6 | passou | `DELETE /user/<id da DAJ>` → 404; usuário intacto |
| B7 | passou | busca por um termo que traz 14 atendidos, 4 casos e 9 orientações na DAJ devolve zero em tudo no Demo; busca por sobrenome do admin da DAJ só devolve usuário do Demo |
| B8 | passou | totais do Demo (20 atendidos, 2 casos, 4 usuários, 2 orientações, 0 notificações, 0 arquivos, 0 fila, 1 unidade) iguais ao `count(*)` por `tenant_id`; os quatro relatórios do Demo só trazem dados do Demo |
| B9 | passou | caso (`ids_clientes`, `id_orientador`, `id_usuario_responsavel`, `id_estagiario`, `id_colaborador`), orientação (`atendidos_ids`), fila (`id_atendido`) e lembrete (`id_usuario`): 400 com `details.field` correto e mesma mensagem para id da DAJ e para 999999; nada gravado |
| B10 | passou | e-mail de usuário real da DAJ, em caixa baixa e em caixa alta: 400 "E-mail já está em uso", sem mencionar a DAJ |
| B11 | passou | assistência judiciária no Demo com o e-mail da existente na DAJ: 201 |
| B12 | passou | aviso geral inserido na DAJ não aparece no Demo. Ressalva: avisos gerais só são listados para `orient` e `estag_direito`; o admin não os vê (comportamento do service, não da multitenancy) |
| C1 | passou | `tenant_id`, `aud: "tenant"`; o token da plataforma tem `aud: "plataforma"` |
| C2 | passou | 404 em GET e POST de `setup-admin` e `needs-setup` |
| C3 | passou | 401 |
| C4 | passou | 401 |
| C5 | passou | 401; o inverso (conta da plataforma em `/auth/login`) também 401 |
| C6 | passou | desativado: login 401, token anterior 401, DAJ e Demo seguem 200; `forgot-password` responde 200 mas não envia e-mail e o hash fica intacto; reativado, login volta |
| C7 | passou | e-mail chega ao Mailpit, link redefine a senha da estagiária, hash do admin intacto, token recusado na segunda vez |
| P1 | passou | lista com DAJ, NPJ Demo e NPJ Teste, com situação |
| P2 | passou | nome salvo (PUT 200); a tela mostra o slug como texto fixo, sem campo |
| P3 | passou | 201; a tela mostra o link de primeiro acesso ("vale por 3 dias e só funciona uma vez") |
| P4 | passou | link em contexto novo: senha definida, login, cabeçalho `NAV · NPJ Navegador`, listas vazias, uma unidade |
| P5 | **falhou** em um caso | slug, sigla em caixa diferente (`daj`) e e-mail de usuário de outro NPJ (admin e não-admin): 400 no campo certo, nada criado pela metade (ids 5 e 6 de `tenants` foram consumidos pelo rollback, sem linhas). **E-mail do admin da plataforma foi aceito** (ver 4.3.1) |
| P6 | passou | os três slugs recusados com "Use letras minúsculas, números e hífens" (a validação é só do servidor, o campo aceita o texto) |
| P7 | passou | sessão da plataforma em `/` ou `/casos` cai no `/login` do NPJ; sessão de NPJ em `/plataforma` cai no `/plataforma/login`; cookies distintos |
| P8 | passou | diálogo de confirmação, PATCH 200, lista mostra "Desativado", login do NPJ recusado, reativação pela tela |
| E1 | passou | `/setup-admin` → 404 e redirecionamento ao login; o login não oferece configuração de administrador |
| E2 | passou | `DAJ · Divisão de Assistência Judiciária`, seletor com Belo Horizonte e Nova Lima; BH: 3446 atendidos e 608 casos ativos; NL: 573 e 333 (os totais do ensaio, 3461 e 575, incluem inativos: 15 e 2) |
| E3 | passou | `NPJD · NPJ de Demonstração`, só `SEDE`, atendidos do seed |
| E4 | passou | atendido, caso, edição de ambos, usuário e orientação da DAJ abertos no Demo: "Página não encontrada", API 404, nenhum dado exibido (ver 4.4.1) |
| E5 | passou | atendido (CEP preenchido pela ViaCEP) → caso com assistida e estagiária do Demo → evento com responsável e anexo PDF → a estagiária vê a notificação "Cadastrado no evento 1 do caso 950" e abre o caso |
| E6 | registrado | caso, lembrete e fila com id de outro NPJ (corpo alterado em trânsito): a API responde 400 e o front mostra só um toast com a mensagem ("Atendido não encontrado", "Usuário não encontrado"); o campo não é marcado e o diálogo permanece aberto. Evento e processo não exercitados (multipart / sem campo cruzado); orientação barrada antes pela validação de sub-área |
| E7 | passou | `orient`, `estag_direito` e `colab_ext` reais: casos, escalas, fila, registro de presença, atendidos, orientações, assistências, relatórios, arquivos, notificações, perfil, em BH e Nova Lima, sem erro de API nem de página; páginas restritas por papel (`/usuarios`, `/unidades`, `/confirmar-presenca`, `/relatorios` para estagiário) mostram o erro genérico de permissão, como antes |
| F1 | passou | anexo de caso em `2/casos/`, arquivo geral em `2/arquivos/`, anexo de evento (E5) em `2/eventos/`; a produção segue em `1/` |
| F2 | passou | download de ambos com token da DAJ → 404; com token do Demo → 200 |
| F3 | passou | `--dry-run` duas vezes: "a mover: 0", sem alteração |
| G1–G5 | passou | `MULTITENANT_MYSQL_TEST=1`: 2 testes em 24,7 s, container removido |

## 3. Falhas: reprodução

### P5 — e-mail do admin da plataforma aceito como admin de NPJ

1. Em `/plataforma/novo`, preencher nome `X`, sigla `XX5`, slug `npj-x5`,
   unidade `U`/`U1`, admin `A` e e-mail `plataforma@local.br`.
2. Resposta: **201**; tenant 7 criado com um usuário `plataforma@local.br`.
3. Esperado, pelo texto de ajuda do campo ("Não pode ser usado por nenhuma
   outra conta da plataforma"): 400 em `admin_email`.

Gravidade baixa: `plataforma_admins` e `usuarios` são tabelas distintas e o
login de cada área só consulta a sua, então não há acesso cruzado (C3, C4 e
C5 passam). É divergência entre a mensagem da tela e a regra.

## 4. Achados fora do roteiro

### 4.1 Vazamento entre NPJs

Nenhum.

### 4.2 Erro 500

Nenhum em toda a execução (API e navegador).

### 4.3 Divergência do plano

1. **P5**, acima.
2. Sublistas com pai de outro NPJ respondem 200 vazio em vez de 404:
   `GET /atendido/<id>/casos`, `GET /atendido/<id>/orientacoes` e
   `GET /caso/<id>/historico`. Já `/caso/<id>/eventos`, `/processos` e
   `/lembretes` respondem 404. Para id inexistente (999999) a resposta é a
   mesma lista vazia, então não há como distinguir "existe em outro NPJ" de
   "não existe"; é só inconsistência entre rotas, sem vazamento.
3. `forgot-password` para conta de NPJ desativado responde 200 sem enviar
   e-mail. Coerente com não revelar contas, mas vale registrar que a pessoa não
   recebe nenhum aviso de que o NPJ está inativo.

### 4.4 Interface

1. A página de registro de outro NPJ (E4) mostra ao mesmo tempo "Página não
   encontrada" e "Ocorreu um erro inesperado"; a segunda frase confunde.
2. Textos fixos com "DAJ" aparecem em qualquer NPJ: `/unidades` ("Locais de
   atendimento da DAJ"), ficha do atendido ("Como Conheceu o DAJ"),
   formulário de usuário ("Certificado de Atuação DAJ") e termos de uso.
3. E6: o erro 400 por id inválido chega só como toast; o campo não é marcado
   (limitação já prevista no roteiro).
4. `/plantao` sem subrota mostra "Página não encontrada" para todos os papéis;
   os links do menu apontam para as subrotas, então só afeta URL digitada.
5. A validação do slug é só no servidor; o campo aceita maiúsculas, espaço e
   sublinhado até o envio.

## 5. Não executado

- Comparação de E7 com a `master` em execução: não há stack da `master` com a
  mesma base; verifiquei ausência de erros e consistência de totais entre BH e
  Nova Lima, não paridade tela a tela.
- E6 para evento (multipart) e processo; orientação jurídica no front.
- B4/B5 para `registro_entrada`, `plantao/escalas` e `unidades` por id: as
  rotas não expõem leitura por id de outro NPJ além do que a varredura
  automatizada (`test_tenant_vazamento.py`, A5) já cobre.

## 6. Artefatos

Scripts Playwright e capturas de tela da execução ficaram em
`/tmp/claude-1000/-mnt-dados-gestaolegal-multitenant/6eda3188-4745-4b8c-a8d9-0fa473797039/scratchpad/pw/`
(sessão temporária; não contêm dados pessoais além do que a tela do NPJ Demo
mostra).
