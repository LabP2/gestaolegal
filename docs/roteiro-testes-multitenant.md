# Roteiro de testes — multitenancy (PRs 1 a 9)

Instruções para um agente (ou pessoa) verificar a implementação da
multitenancy descrita em [plano-multitenant.md](plano-multitenant.md). O
objetivo é **encontrar defeitos**, não confirmar que funciona: cada teste diz o
resultado esperado; qualquer desvio é um achado.

Branch: `feat/multitenant`, worktree `/mnt/dados/gestaolegal-multitenant`.
Commits, do mais antigo ao mais novo:

| Commit | PR | Conteúdo |
|---|---|---|
| `f0c325b` | 1 | Tabelas `tenants` e `plataforma_admins`, contexto de tenant, migration M1 |
| `4179632` | 2 | `tenant_id` nas 28 tabelas, repositórios filtrados, migration M2 |
| `d6dada4` | 4 | Tenant no JWT (`tenant_id`, `aud`), fim do `/setup-admin`, sigla do NPJ no cabeçalho |
| `b520f7c` | 8 | Anexos numa pasta por tenant e script de movimentação |
| `b94f37a` | 3 | Guarda de execução: consulta sem filtro de tenant é recusada |
| `ccf6177` | 7 | Área da plataforma: login, cadastro de NPJs, `flask plataforma criar-admin` |
| `af26424` | 6 | Testes de vazamento varrendo todas as rotas |
| `c08db38` | 6b | Services recusam ids de outro NPJ ou inexistentes |
| `5971f9d` | 9 | Seed com dois NPJs, reset restrito aos slugs de demonstração |
| `947661c` | 5 | FKs compostas `(tenant_id, x_id)`, migration M3 |

## Regras para quem testa

- **Só o ambiente local deste worktree.** Nada contra QA, produção ou os dumps
  em `dumps/`. Não executar `scripts/reset_demo.sh`.
- **Não alterar código, testes, `.env*` nem `.github/`.** Achou um defeito?
  Registre; não corrija. Não afrouxe asserção para um teste passar.
- **Sem push, sem PR, sem commit.** O relatório é o produto.
- **Não derrubar outras stacks** (`docker ps` mostra as do checkout principal
  em 5000/5001; não mexa nelas).
- Dados apenas fictícios nas evidências.

## Preparação

### Portas

Leia `APP_PORT` e `WEB_PORT` do `.env` do worktree (hoje 5300 e 5301; Mailpit
em `MAILPIT_UI_PORT`, hoje 8325).

```bash
cd /mnt/dados/gestaolegal-multitenant
export API=http://localhost:$(grep ^APP_PORT= .env | cut -d= -f2)/api
export WEB=http://localhost:$(grep ^WEB_PORT= .env | cut -d= -f2)
docker compose -f docker-compose.dev.yml ps        # api, web, db e mailpit "running"; migrate "exited (0)"
```

Se a stack não estiver no ar: `docker compose -f docker-compose.dev.yml up -d --build` (a cadeia de
migrations demora vários minutos neste disco). Confirme que o banco está no head:

```bash
docker compose -f docker-compose.dev.yml exec -T db sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE" -N -e "select version_num from alembic_version"'
# esperado: c2d3e4f5a6b7
```

Para consultas SQL ao longo do roteiro, use o mesmo padrão:

```bash
sql() { docker compose -f docker-compose.dev.yml exec -T db sh -c "mysql -uroot -p\"\$MYSQL_ROOT_PASSWORD\" \"\$MYSQL_DATABASE\" -e \"$1\"" 2>/dev/null; }
sql "select id, slug, ativo from tenants"
```

### Contas

| NPJ (slug) | Contas | Senha |
|---|---|---|
| DAJ/UFMG (`daj-ufmg`, id 1) | `admin@ufmg.br`, `orient@ufmg.br`, `estag_direito@ufmg.br`, `colab_ext@ufmg.br` | `123456` |
| NPJ Demo (`npj-demo`) | `admin@npjdemo.br`, `orient@npjdemo.br`, `estag_direito@npjdemo.br`, `colab_ext@npjdemo.br` | `123456` |
| NPJ Teste (`npj-teste`) | `admin@npjteste.br`, `estag@npjteste.br` | `123456` |
| **Plataforma** | `plataforma@local.br` | `12345678` |

Se alguma conta não existir: `docker compose -f docker-compose.dev.yml exec -T api python
scripts/seed_database.py` recria DAJ e NPJ Demo sem duplicar nada, e
`docker compose -f docker-compose.dev.yml exec -T api flask --app 'gestaolegal:create_app()' plataforma
criar-admin --email plataforma@local.br --nome "Admin Plataforma" --senha
12345678` cria o admin da plataforma. O NPJ Teste foi criado à mão; se faltar,
crie um NPJ equivalente pela área da plataforma (teste P3).

### Atalhos para a API

```bash
login() { curl -s $API/auth/login -H 'Content-Type: application/json' \
  -d "{\"email\":\"$1\",\"password\":\"${2:-123456}\"}" | jq -r .data.token; }
unidade() { curl -s $API/user/me -H "Authorization: Bearer $1" | jq -r '.data.unidades[0].id'; }
# chamada autenticada: get TOKEN UNIDADE /rota
get() { curl -s -w '\nHTTP %{http_code}\n' "$API$3" -H "Authorization: Bearer $1" -H "X-Unidade-Id: $2"; }

DAJ=$(login admin@ufmg.br);    U_DAJ=$(unidade $DAJ)
DEMO=$(login admin@npjdemo.br); U_DEMO=$(unidade $DEMO)
PLAT=$(curl -s $API/plataforma/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"plataforma@local.br","password":"12345678"}' | jq -r .data.token)
```

Para montar os corpos de POST/PUT, use como referência os testes da API
(`tests/api/conftest.py`, `sample_*_data`, e `tests/api/test_referencias_api.py`).

## Parte A — verificação automatizada

| # | Comando | Esperado |
|---|---|---|
| A1 | `uv sync --all-extras --all-groups && uv run pytest tests/ -q` | nenhuma falha ou xfail; o único skip permitido é o ensaio MySQL, executado separadamente em G. A retirada do importador remove seus testes exclusivos |
| A2 | `uv run alembic -c migrations/alembic.ini heads` | um único head, `c2d3e4f5a6b7` |
| A3 | `cd web && npm ci && npm run check` | comparar diagnósticos com `b8f2f8d` usando as mesmas dependências; a base tem 21 erros. Exigir zero erros novos, inclusive em arquivos não tocados. `api-client.ts` foi tocado mas seu erro é anterior |
| A4 | `cd web && npm run lint` | somente `anexos-evento.svelte` e `processo-schema.ts`, confirmados também na base `b8f2f8d` |
| A5 | `uv run pytest tests/api/test_tenant_isolamento.py tests/api/test_tenant_guarda.py tests/api/test_password_reset_api.py tests/api/test_tenant_vazamento.py -q`, depois os quatro módulos na ordem inversa | ambos passam; a varredura restaura o banco ao sair. Repetir na mesma ordem não testa dependência de ordem |

## Parte B — API: isolamento entre NPJs

Em todos: a resposta **nunca** contém nome, e-mail, CPF ou id de registro do
outro NPJ, e o banco do NPJ atacado fica intacto.

| # | Ação | Esperado |
|---|---|---|
| B1 | `get $DAJ $U_DAJ /user/me` e `get $DEMO $U_DEMO /user/me` | cada um vê o próprio e-mail e `tenant.sigla` do próprio NPJ |
| B2 | `get $DEMO $U_DAJ /atendido/` (unidade da DAJ com token do Demo) | 403 |
| B3 | Pegue um id em `get $DAJ $U_DAJ /atendido/` e faça `get $DEMO $U_DEMO /atendido/<id>` | 404 |
| B4 | Repita B3 para caso, processo, evento, orientação, lembrete, assistência judiciária, arquivo e usuário | 404 (ou 403) em todos |
| B5 | `PUT` e `DELETE` com token do Demo nos ids da DAJ obtidos em B3/B4 | 4xx, e o registro da DAJ igual ao de antes (`sql` ou `get $DAJ ...`) |
| B6 | `DELETE /user/<id de usuário da DAJ>` com token do Demo | 404 — antes respondia 200 sem fazer nada |
| B7 | Busca global: `get $DEMO $U_DEMO "/search/?q=<4 letras de um atendido da DAJ>"` | `atendidos.items` vazio; `usuarios` só do Demo |
| B8 | Listagens e totais (`/atendido/`, `/caso/`, `/user/`, `/notificacao/`, relatórios) com token do Demo | contagens só do Demo; compare com `sql "select count(*) from atendidos where tenant_id=<id do demo>"` |
| B9 | Criar caso, orientação, senha da fila e lembrete no Demo referenciando ids da DAJ (`ids_clientes`, `id_orientador`, `atendidos_ids`, `id_atendido`, `id_usuario`) | 400 com `details.field` apontando o campo; mesma resposta que para um id inexistente (ex.: 999999) |
| B10 | `POST /user/` no Demo com o e-mail `orient@ufmg.br` | 400 "E-mail já está em uso", sem citar a DAJ |
| B11 | Unicidade por NPJ: no Demo, cadastrar assistência judiciária com o mesmo e-mail de uma da DAJ | aceito (a unicidade vale dentro de cada NPJ) |
| B12 | Avisos gerais (notificação sem destinatário) criados na DAJ | não aparecem em `get $DEMO $U_DEMO /notificacao/` |

## Parte C — token e login

| # | Ação | Esperado |
|---|---|---|
| C1 | Decodifique o payload do token (`echo $DAJ \| cut -d. -f2 \| base64 -d`) | tem `tenant_id: 1` e `aud: "tenant"` |
| C2 | `curl $API/auth/setup-admin` e `$API/auth/needs-setup` (GET e POST) | 404 |
| C3 | Use o token da plataforma em rota de NPJ: `get $PLAT $U_DAJ /atendido/` | 401 |
| C4 | Use o token de NPJ em rota da plataforma: `curl $API/plataforma/tenants -H "Authorization: Bearer $DAJ"` | 401 |
| C5 | Login da plataforma com credenciais de NPJ (`admin@ufmg.br`/`123456`) | 401 |
| C6 | Desative o NPJ Teste: `curl -X PATCH $API/plataforma/tenants/<id>/ativo -H "Authorization: Bearer $PLAT" -H 'Content-Type: application/json' -d '{"ativo":false}'` | 200. Depois: login de `admin@npjteste.br` dá 401, e um token dele obtido **antes** da desativação também dá 401. DAJ e Demo seguem normais. Reative ao final (`{"ativo":true}`) |
| C7 | Recuperação de senha: `POST $API/auth/forgot-password` com `estag@npjteste.br`; abra o e-mail no Mailpit, siga o link, troque a senha e faça login | funciona; o token de redefinição só vale para essa conta |

## Parte D — plataforma (navegador)

Em `$WEB/plataforma/login`, entre como `plataforma@local.br`.

| # | Ação | Esperado |
|---|---|---|
| P1 | Abrir a lista de NPJs | mostra DAJ, NPJ Demo e NPJ Teste, com estado ativo/inativo |
| P2 | Editar o nome de um NPJ | salva; o slug não pode ser alterado |
| P3 | Criar um NPJ com nome, sigla, slug, unidade e admin (e-mail novo) | 201; a tela mostra o **link de primeiro acesso** |
| P4 | Abrir o link de P3 numa janela anônima, definir a senha e entrar como o admin novo | entra no NPJ novo, com listas vazias e a sigla nova no cabeçalho |
| P5 | Criar NPJ repetindo slug, sigla (em outra caixa: `daj`) ou o e-mail de um admin existente | 400 no campo certo; nenhum tenant ou unidade criado pela metade (`sql "select id, slug from tenants"`) |
| P6 | Slug inválido (`NPJ X`, `npj_x`, `-npj`) | recusado |
| P7 | Com a sessão da plataforma aberta, abrir `$WEB/` | a sessão da plataforma não dá acesso ao sistema do NPJ, e vice-versa |
| P8 | Desativar um NPJ pela tela | igual a C6 |

## Parte E — sistema do NPJ (navegador)

| # | Ação | Esperado |
|---|---|---|
| E1 | `$WEB/setup-admin` | página inexistente; o login não oferece "configurar administrador" |
| E2 | Entrar como `admin@ufmg.br` | sigla da DAJ no cabeçalho; BH e Nova Lima disponíveis; dados do seed |
| E3 | Entrar como `admin@npjdemo.br` | sigla do Demo; só a unidade dele; atendidos com nomes diferentes dos da DAJ |
| E4 | Copiar a URL de um atendido/caso da DAJ e abri-la logado no Demo | "não encontrado", sem mostrar dado algum |
| E5 | No Demo, fluxo completo: atendido → caso (com estagiário do Demo) → evento → anexo → notificação | tudo funciona; a estagiária do Demo vê o caso |
| E6 | Formulários que agora podem responder 400 por id inválido (caso, orientação, fila, lembrete, evento, processo) | registre como o front exibe esse erro — sabidamente ainda não é mostrado no campo; anote o comportamento |
| E7 | Regressão da DAJ com `orient@`, `estag_direito@` e `colab_ext@`: casos, plantão, fila, presença, relatórios, arquivos, troca BH ↔ Nova Lima | igual à `master` |

## Parte F — anexos por NPJ

| # | Ação | Esperado |
|---|---|---|
| F1 | Enviar um anexo no Demo (caso, evento ou arquivos gerais) | o arquivo aparece em `<PRIVATE_FILES_ROOT>/<id do tenant>/<categoria>/` dentro do container da API (`docker compose -f docker-compose.dev.yml exec api ls -R /data/gestaolegal/uploads`) |
| F2 | Tentar baixar esse anexo com token da DAJ (id do arquivo na URL) | 404 |
| F3 | `docker compose -f docker-compose.dev.yml exec -T api python scripts/mover_arquivos_tenant.py --dry-run` | relatório sem mover nada; rodar duas vezes dá o mesmo resultado |

## Parte G — migrations em MySQL descartável (obrigatório antes do merge)

Ensaio reproduzível: `MULTITENANT_MYSQL_TEST=1 uv run pytest tests/database/test_multitenant_mysql.py -v`.
O teste cria MySQL 8.0.42 com nome e porta exclusivos, usa tmpfs e remove o
container no `finally`. Não aceita URL de banco existente. Executa G1–G5 e
confere a idempotência do seed após a M3.

Só num container novo, nunca no banco da stack nem em cópia de produção sem
autorização. Use nome e porta próprios (ex.: `mt-teste-mysql`,
`127.0.0.1:33999`) e espere a **conexão TCP** responder, não só a linha
"ready for connections" (a inicialização reinicia o servidor e pode levar
vários minutos).

| # | Ação | Esperado |
|---|---|---|
| G1 | `upgrade head` desde a baseline, com `scripts/seed_database.py` rodado antes da M3 | sucesso; 28 tabelas com `tenant_id` NOT NULL; FKs compostas |
| G2 | Inserir um registro cruzado (ex.: plantão do tenant 1 apontando para unidade do tenant 2) **antes** da M3 e aplicar | M3 aborta com relatório `tabela.coluna -> pai: N registro(s)` e não altera nada |
| G3 | Após a M3, inserir registro cruzado | erro 1452 (FK) |
| G4 | `downgrade b1c2d3e4f5a6` e `upgrade head` de novo | esquema idêntico ao da primeira vez; `arquivosCaso.id_caso` mantém `ON DELETE CASCADE` |
| G5 | Com dados de um segundo tenant, `downgrade a0b1c2d3e4f5` | recusado com "Remova-os antes do downgrade" |

Remova o container ao final se executar manualmente. O teste automatizado já faz isso.

## Regressões acrescentadas na revisão

- Guarda: UNION/UNION ALL em cada ramo e em subqueries; overrides de binds
  nomeados e anônimos; UPDATE/DELETE em lote; INSERT parametrizado; SQL textual
  encapsulado e construções não suportadas. Violações devem falhar antes da execução.
- Isolamento: leitura, edição, exclusão e listagem nos dois sentidos entre NPJs.
  Coleções devem responder 200; leituras por ID só aceitam 200/403/404, com
  comparação de resultado vazio para 200. Erro 500 nunca prova isolamento.
- Senha: emitir link comum e de primeiro acesso, desativar o NPJ e tentar
  validar/consumir. Esperar 400 e hash de senha intacto. Reativar e conferir
  que o link ainda válido funciona.
- Importação BH/Nova Lima: concluída. O script e seus testes exclusivos foram
  removidos; não executar nem adaptar o importador. Histórico em `docs/unidades.md`.

## Relatório

Grave o resultado em `docs/resultado-testes-multitenant.md` (ou devolva no
chat, se não puder escrever no worktree), com:

1. Ambiente: commit testado (`git log --oneline -1`), portas e data.
2. Tabela com cada teste (A1…G5): **passou**, **falhou** ou **não executado**
   (com o motivo).
3. Para cada falha: passos exatos para reproduzir, resposta obtida (status e
   corpo, sem dados pessoais reais) e o resultado esperado.
4. Achados fora do roteiro, separados por gravidade: **vazamento entre NPJs**
   primeiro, depois erro 500, depois comportamento divergente do plano, depois
   problemas de interface.

Limitações já conhecidas, que não contam como achado novo: os listados em
[known_issues.md](known_issues.md) e as pendências registradas na seção
"Revisão humana" da descrição do PR #425.
