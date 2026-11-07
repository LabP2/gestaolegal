# Problemas conhecidos

Registro de limitações já identificadas e ainda não corrigidas. Cada item
diz o que acontece hoje, por que acontece e o que seria preciso para
resolver.

Revisado em **07/09/2026**, contra a `master` em `3b0fba74`. A revisão
considera o código e os testes locais; não certifica a implantação em produção.
Os issues no GitHub detalham os pedidos e os critérios de aceite.

## Casos: a API aceita qualquer valor em `situacao_deferimento`

`CasoCreateInput.situacao_deferimento` é `str`, sem conjunto fechado de
valores. Foi assim que registros com o valor legado `deferido` entraram no
banco — e eles não podiam ser editados, porque o formulário não tem essa
opção (corrigido pela migração `9b4a1c7e30df` e pela normalização na carga
do formulário). Fechar o conjunto no input evitaria a recorrência, mas
alguns testes usam `deferido` de propósito e precisariam ser revistos
junto.

## Recuperação de senha: limite de pedidos só por usuário

**O que acontece.** `PasswordResetService.solicitar` conta os pedidos de cada
usuário nos últimos 15 minutos e para de enviar acima de três, o que protege
uma caixa de entrada de ser inundada.

**O que fica de fora.** Nada limita a quantidade de tentativas por origem: um
script pode chamar `POST /api/auth/forgot-password` com milhares de endereços
diferentes. A resposta é sempre a mesma, então isso não revela quem tem conta,
mas consome recursos do servidor e do MTA.

**Como resolver.** Limitar por IP exige estado compartilhado entre os workers
do gunicorn — Flask-Limiter com Redis, ou `limit_req` no nginx à frente da
API. A segunda opção não acrescenta dependência à aplicação.

## Pessoa jurídica: campos complementares legados

A ficha de assistido coleta enquadramento, especificação de “Outros”, nomes dos
sócios e situação perante a Receita Federal, conforme a issue #114. Conversão,
edição e perfil usam os mesmos dados. MEI não possui sócios; salvar como MEI
remove os nomes anteriores. Os nomes são armazenados como uma lista JSON na
coluna legada `socios` (até 1000 caracteres); texto livre antigo é apresentado
como um único nome, sem inferir separadores. A ficha aceita até 20 nomes de até
80 caracteres cada, respeitado o limite total da coluna.

A migration `e2f3a4b5c6d7` acrescenta `especificacao_enquadramento` e torna
opcionais os campos legados que não eram coletados. Não altera respostas
existentes. O downgrade exige que esses campos estejam preenchidos; caso
contrário, é recusado antes de alterar o esquema.

Continuam sem formulário os campos complementares da tabela
`assistidos_pessoa_juridica`: sede, área de atuação, negócio nascente, órgão de
registro, faturamento, balanço, resultado e funcionários. As gravações da ficha
preservam esses campos. Não remover a tabela nem inferir que esteja vazia.

## Usuários: o cadastro novo nasce sem senha utilizável

**O que acontece.** O formulário de novo usuário não pede senha, e
`UsuarioService.create` gera uma senha aleatória de 12 caracteres
(`usuario_service.py`) que não é exibida na tela nem enviada a ninguém. A pessoa
recém-cadastrada, portanto, não consegue entrar.

**Como se contorna hoje.** O administrador abre a tela do usuário e define uma
senha em **Alterar Senha** (a troca administrativa dispensa a senha atual), ou a
pessoa usa o **Esqueci minha senha** com o e-mail cadastrado — possível desde a
fase 4. O segundo caminho é melhor: a senha não passa por terceiros.

**Como resolver.** Enviar, no cadastro, um e-mail de convite com um link de
definição de senha, reaproveitando a infraestrutura de
`password_reset_service.py` (token de uso único, com validade maior). É o item
"convite por e-mail a usuários novos" da lista de pendências de
`paridade-v2-v3.md`.


## Permissões: deferimento e arquivos de casos

As rotas de edição, deferimento e indeferimento de casos continuam exigindo
apenas autenticação, sem a restrição por papel pedida no
[#203](https://github.com/gestaolegalufmg/gestaolegal/issues/203). Upload,
substituição e exclusão de arquivos de casos também continuam sem listas
específicas de papéis, conforme
[#159](https://github.com/gestaolegalufmg/gestaolegal/issues/159).

O filtro por unidade e o armazenamento privado não substituem essas regras.
É preciso definir a política de acesso e aplicá-la na API e na interface.
A wiki descreve o comportamento implementado; isso não encerra os pedidos
de alteração das permissões.

## Banco: caracteres fora de latin-1 em instalações legadas

A migration inicial `ed1b0a0a61a6` cria colunas com `latin1_general_ci`.
As conversões pontuais posteriores não convertem todo o esquema para
`utf8mb4`. Instalações que ainda tenham essas colunas podem recusar caracteres
como cirílico e emoji. O
[#191](https://github.com/gestaolegalufmg/gestaolegal/issues/191) permanece
pendente: conferir o esquema real e preparar a conversão das colunas e dos
dados. Os testes com SQLite não validam o charset do MySQL.

## Formulários: especificação e preservação de dados

- [#364](https://github.com/gestaolegalufmg/gestaolegal/issues/364): o questionário
  de assistido ainda diverge da ordem, dos textos e das opções solicitadas.
  Por exemplo, “Qual benefício?” aparece para benefícios além de “Outro”, e
  a pergunta de doença grave não oferece “Não informou”.
- [#365](https://github.com/gestaolegalufmg/gestaolegal/issues/365): CPF e e-mail
  continuam obrigatórios no schema de atendido; falta o fluxo conjunto de
  cadastrar e incluir na fila.
- [#363](https://github.com/gestaolegalufmg/gestaolegal/issues/363) e
  [#326](https://github.com/gestaolegalufmg/gestaolegal/issues/326): a correção da
  perda de endereço no envio e de texto após atendimento prolongado ainda
  precisa ser comprovada no navegador. O formulário de orientação preserva
  estado em erros comuns, mas não salva rascunho; um 401 redireciona ao login.
  Não considerar esses relatos resolvidos apenas pela inspeção do código.

## Unidades: desativação não é validada pelo cabeçalho da API

O seletor do frontend oculta unidades inativas, mas `_resolver_unidade_ativa`
confere apenas se `X-Unidade-Id` pertence aos vínculos do usuário. A consulta
que carrega esses vínculos inclui unidades inativas. Assim, desativar a unidade
não impede por si só o acesso direto à API de quem continua vinculado a ela.
A validação precisa conferir também `ativa`, com teste de acesso após a
desativação. Administradores também dependem de vínculo; o papel não concede
acesso automático a todas as unidades.

## Multitenant: referência a id de outro NPJ no corpo

**O que acontece.** Ao criar um caso, uma orientação, uma senha da fila ou um
lembrete, a API grava os ids recebidos no corpo (`ids_clientes`,
`id_orientador`, `atendidos_ids`, `id_atendido`, `id_usuario`...) sem conferir
se são do NPJ da requisição. Um admin de outro NPJ que mande ids da DAJ cria um
registro dele apontando para um atendido ou usuário da DAJ.

**O que não acontece.** Nada da DAJ é lido nem alterado: toda leitura filtra o
tenant, então o registro criado aparece sem o cliente ou o orientador
estrangeiro (`tests/api/test_tenant_vazamento.py`).

**Como resolver.** A M3 (FKs compostas `(tenant_id, x_id)`, PR 5 de
`docs/plano-multitenant.md`) recusa a referência no banco, mas como
`IntegrityError` (500). Para responder 400/404, os services precisam conferir
cada id referenciado com o repositório, que já filtra o tenant. O teste
`test_criacao_com_referencia_a_outro_npj_e_recusada` está marcado `xfail`
estrito e passa a falhar, pedindo a remoção da marca, quando isso for feito.

## Correções já entregues

Os itens abaixo não são mais limitações do código atual:

| Item | Situação verificada |
|---|---|
| Histórico do plantão desaparecia após o prazo | O fim das inscrições preserva escala, marcações e confirmações. Cancelamento é explícito. |
| Configuração única sobrescrevia períodos anteriores | Cada escala tem nome, unidade, dias, janela de inscrição e histórico próprios. Criar uma não substitui as anteriores. |
| [#183 — múltiplos anexos de evento](https://github.com/gestaolegalufmg/gestaolegal/issues/183) | Criação aceita vários anexos; edição acrescenta arquivos e permite gerenciar os existentes. |
| [#190 — arquivos privados em pasta pública](https://github.com/gestaolegalufmg/gestaolegal/issues/190) | Raiz privada, downloads autenticados e bloqueio dos caminhos estáticos. |
| [#205 — número longo de processo](https://github.com/gestaolegalufmg/gestaolegal/issues/205) | Número como texto de até 25 caracteres, preservando pontuação e zeros iniciais. |
| [#366 — atalho Plantão com 404](https://github.com/gestaolegalufmg/gestaolegal/issues/366) | O atalho usa uma rota existente, que redireciona para a listagem de escalas. |

As mudanças de plantão estão descritas em [Escalas de plantão](escalas-plantao.md).
Os registros antigos são agrupados por unidade como legado, somente para
consulta; o modelo anterior não permite recuperar com certeza a escala
original de cada marcação. O aceite de uso pela DAJ continua a ser confirmado
no [#315](https://github.com/gestaolegalufmg/gestaolegal/issues/315).

Para receber as correções, instalações existentes precisam aplicar as migrations
e, no caso dos arquivos, migrar o acervo e conferir o volume privado e a
configuração do proxy. Veja o
[Manual de Instalação](https://github.com/gestaolegalufmg/gestaolegal/wiki/Manual-de-Instalação).

Na revisão de 07/09/2026, passaram 206 testes de eventos, processos, bloqueio
estático, armazenamento e migração de anexos, plantão, presença e relatórios.
Foram usados SQLite em memória e arquivos temporários. A navegação do #366
foi conferida no código, sem teste de navegador.
