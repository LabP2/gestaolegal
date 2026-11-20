# Ensaio completo — resultado parcial de 11/11/2026

Roteiro: [roteiro-ensaio-completo.md](roteiro-ensaio-completo.md).
Execução interrompida pelo usuário e salva a pedido. **O roteiro não foi concluído.**
Não houve correção do código nem commit nesta execução.

## Ambiente e método

- Worktree `/mnt/dados/gestaolegal-multitenant`, commit `222e512`.
- API, web, MySQL e Mailpit já estavam em execução; API e web usam fontes montadas deste worktree.
- Endereços locais: API 5300, web 5301, MySQL 3606, Mailpit 8325.
- Suíte automatizada local e verificações na API real e no navegador (Playwright com Chrome).
- Não foram exportados dados pessoais nem capturas de tela. Este relatório omite nomes, e-mails e identificadores pessoais reais.
- Os arquivos que já estavam modificados ou não rastreados no início foram preservados, inclusive `docs/resultado-testes-multitenant.md`.

## Checagens automatizadas

| Checagem | Resultado |
|---|---|
| `.venv/bin/pytest -q --junitxml=/tmp/gestaolegal-ensaio-pytest.xml` | ✅ **1.137 passaram, 5 ignorados**, em 248,31 s |
| `npm run check`, em `web/` | ❌ **8 erros e 41 avisos em 34 arquivos** |
| Testes MySQL descartáveis com `MULTITENANT_MYSQL_TEST=1` | ⏸ Sem execução confirmada; a solicitação foi interrompida e não havia log de resultado |

A suíte de API usa SQLite isolado e transporte simulado do DJEN. Seu resultado não substitui a execução do roteiro sobre a cópia real, nem comprova a integração com o DJEN externo.

### Erros do frontend

Não foi feita comparação com outra revisão; não é possível afirmar nesta execução se são regressões.

| Arquivo em `web/src/` | Linha | Erro |
|---|---|---|
| `lib/types/api-response.ts` | 70 e 71 | `captureStackTrace` não existe em `ErrorConstructor` (2 erros) |
| `lib/api-client.ts` | 64 | Operando à esquerda de `instanceof` com tipo incompatível |
| `routes/(dashboard)/casos/[id]/editar/+page.ts` | 33 | `No overload matches this call` |
| `routes/(dashboard)/plantao/assistencias-judiciarias/[id]/editar/+page.ts` | 33 | `No overload matches this call` |
| `routes/(dashboard)/plantao/atendidos-assistidos/[id]/editar/+page.ts` | 37 | `No overload matches this call` |
| `routes/(dashboard)/plantao/orientacoes-juridicas/[id]/editar/+page.ts` | 25 | `No overload matches this call` |
| `routes/(dashboard)/usuarios/[id]/editar/+page.svelte` | 36 | Propriedade `onUpdate` não existe em `$$ComponentProps` |

## Evidências do roteiro

✅ = verificado no escopo descrito; ❌ = divergência observada; ◐ = parcial; ⏸ = não executado.

| Item | Estado | Evidência e limites |
|---|---|---|
| 1.1 | ◐ | Login do admin pela API e pela tela funcionou; cabeçalho DAJ observado. Seletor das duas unidades ainda não conferido pela tela. |
| 1.2 | ◐ | `/api/auth/setup-admin` respondeu 404. Falta conferir a URL de página `/setup-admin`. |
| 1.3 | ✅ | Senha errada: API 401; tela exibiu “E-mail ou senha incorretos. Verifique os dados e tente novamente.”; login correto funcionou depois. |
| 1.4 | ⏸ | O estado inicial diferia do roteiro: DJEN já estava ligado. Menu ainda não validado de forma conclusiva. |
| 2.1 | ✅ API | Incluindo inativos: BH 3.461 atendidos; Nova Lima 575. Iguais à referência. Lista visual ainda não auditada. |
| 2.2 | ◐ | API com inativos: BH 612 casos; Nova Lima 333. Iguais à referência. Exibição de estagiário e assistido ainda não conferida. |
| 2.3–2.8 | ⏸ | Não executados. |
| 3.1–3.7 | ⏸ | Não executados. |
| 4.1 | ✅ | Login na plataforma pela tela funcionou; API listou DAJ, NPJD, TESTE, NAV e XX5 antes da criação do ENS. |
| 4.2 | ✅ API | Login da plataforma com credenciais do admin da DAJ recusado com 401. |
| 4.3 | ✅ | NPJ Ensaio criado pela tela: sigla ENS, slug `npj-ensaio`, unidade Sede Ensaio/SE, admin fictício `admin@npjensaio.br`. Link de primeiro acesso exibido e conferido. Tenant criado: 8. |
| 4.4 | ◐ | API recusou sigla `daj` e slug `npj-ensaio` repetidos com 400, nos campos corretos. Mensagens: “Sigla já usada por outro NPJ” e “Identificador já usado por outro NPJ”. Ausência de registros parciais ainda não auditada no banco. |
| 5.1 | ◐ | Link aberto em contexto separado; formulário apresentou senha, confirmação e botão “Redefinir senha”. A senha ainda não foi definida e o login do ENS não foi testado. |
| 5.2–5.7 | ⏸ | Não executados. |
| 6.1–6.5 | ⏸ | Não executados. |
| 7.1 | ❌ | Após desligar o DJEN da DAJ pela API da plataforma e recarregar `/djen`, a tela mostrou “Acesso negado” e “Você não tem permissão para acessar esta página.” Não explicou que o DJEN estava desligado para o NPJ, como exige o roteiro. |
| 7.2 | ◐ | DJEN desligado e religado pela API da plataforma (PUT 200 em ambos). Cartão e estado “Ligada” pela tela ainda não testados. |
| 7.3 | ⏸ | Menu após reativação ainda não conferido. |
| 7.4 | ✅ | Antes da alternância, com DJEN já ligado: tela sem publicações, aviso “A rotina do DJEN ainda não rodou para este NPJ.”; API com `ultima: null`. Banco de exemplos com contagens zero. |
| 8.1–8.4 | ⏸ | Não executados. |
| 9.1–9.4 | ⏸ | Não executados; nenhuma rotina DJEN disparada nesta execução. |
| 10.1–10.5 | ⏸ | Não executados. |
| 11.1–11.3 | ⏸ | Não executados. |
| 12.1 | ◐ | Totais iniciais na API com `status=todos`: BH 35, Nova Lima 51. Processo de 3.3 não criado; lista visual ainda não conferida. |
| 12.2–12.4 | ⏸ | Não executados. |
| 13.1–13.7 | ⏸ | Não executados. |
| 14.1–14.9 | ⏸ | Não executados. |
| 15.1 | ◐ | Cartão Banco de exemplos apareceu abaixo da lista, com contagens zero. Contagens posteriores aos vínculos ainda não verificadas. |
| 15.2–15.3 | ⏸ | Não executados. |
| 16.1–16.3 | ⏸ | Solicitados IDs e senhas locais do orientador e do estagiário conforme o roteiro. Nenhuma resposta disponível até o salvamento. Nenhuma senha desses perfis foi alterada. |
| 17.1–17.5 | ⏸ | Não executados. |

## Falha funcional observada: 7.1

1. Autenticar como admin da DAJ e abrir `/djen`.
2. Com token da plataforma, enviar `PUT /api/plataforma/tenants/1` com `{"djen_ativo": false}`.
3. Recarregar `/djen`.
4. Observar: **“Acesso negado” / “Você não tem permissão para acessar esta página.”**
5. Esperado: aviso explícito de que o DJEN está desligado para este NPJ.

A página de carregamento `web/src/routes/(dashboard)/djen/+page.ts` repassa a mensagem da API para o erro do SvelteKit. O componente `web/src/routes/+error.svelte` lê uma prop `error` e usa a mensagem genérica quando ela não está disponível. Esta é uma hipótese de causa a investigar, não uma correção validada.

## Estado deixado e retomada

- **DAJ: DJEN ligado novamente**, confirmado pelo PUT 200 posterior à verificação de 7.1; corresponde ao estado inicial observado.
- **NPJ Ensaio criado (tenant 8)**. Não criar outro ao retomar: usar o existente.
- Primeiro acesso do ENS foi aberto, mas a definição da senha não foi enviada. Se o link não estiver mais disponível, usar recuperação de senha com o e-mail fictício e Mailpit.
- Nenhum atendido, caso, processo, evento ou OAB foi criado nesta execução. Nenhuma consulta real ao DJEN foi disparada.
- Não houve restauração de backup nem alteração dos contêineres existentes.
- Retomar as verificações parciais das partes 1–4 e concluir o primeiro acesso de 5.1; seguir pelas partes restantes. Não considerar resultados da suíte automatizada como conclusão dos itens manuais pendentes.

## Artefatos locais

Logs sem dados pessoais copiados para `docs/evidencias-ensaio-2026-11-11/`:

- `pytest.log`: resultado completo da suíte.
- `frontend-check.log`: erros e avisos completos do frontend.

Artefatos temporários, sujeitos a limpeza do sistema:

- `/tmp/gestaolegal-ensaio-pytest.xml`: JUnit.
- `/tmp/gl-ensaio-browser.cjs` e `/tmp/gl-step*.cjs`: scripts usados no navegador e na API; não versionados.

O link de primeiro acesso e tokens de autenticação não foram incluídos neste relatório.
