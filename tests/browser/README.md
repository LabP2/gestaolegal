# Regressão do seletor de assistidos

Com o frontend local rodando, execute o teste abaixo. Todas as chamadas de API
são interceptadas e respondidas com dados sintéticos; não é necessário login e
nenhum cadastro real é criado ou alterado.

```bash
npm install --prefix /tmp/gestaolegal-browser --no-save playwright
PLAYWRIGHT_MODULE=/tmp/gestaolegal-browser/node_modules/playwright \
  node tests/browser/selector.cjs
```

O endereço padrão é `http://localhost:5002`; sobrescreva com `GL_BASE_URL`.
O navegador padrão é `/usr/bin/google-chrome`; sobrescreva com `CHROME_PATH`.

Verifica URL com filtros, busca, paginação de mais de 50 registros, seleção
entre páginas, confirmação, cancelamento, reabertura, respostas fora de ordem
e recuperação após falha da API. Os testes de API em
`tests/api/test_atendido_api.py` verificam CPF com/sem máscara, isolamento por
unidade, fichas legadas duplicadas e criação de caso com um assistido novo.

## Dados jurídicos de PJ (#114)

Com o mesmo frontend local, execute:

```bash
PLAYWRIGHT_MODULE=/tmp/gestaolegal-browser/node_modules/playwright \
  node tests/browser/pessoa-juridica.cjs
```

As opções `GL_BASE_URL` e `CHROME_PATH` são as mesmas do seletor. O teste usa
somente respostas sintéticas e intercepta as gravações. Cobre conversão,
edição, campos de nomes conforme a quantidade, “Outros”, mudança para MEI,
conteúdo enviado à API, visualização e ausência da seção em pessoa física.
Os testes de API em `tests/api/test_dados_juridicos_pj_api.py` cobrem também
validação, persistência, leitura de texto legado e isolamento entre unidades.

## Suíte npm do frontend

```bash
cd web
npm ci
npm test
npm run check
npm run build
```

`npm test` inicia seu próprio Vite em `127.0.0.1:5302` e usa o Chrome instalado
em `/usr/bin/google-chrome` (ou `CHROME_PATH`). Essa porta precisa estar livre.
Não requer API, MySQL ou credenciais: as requisições da aplicação recebem
respostas sintéticas no navegador. As gravações são interceptadas e mantidas
somente durante cada teste, sem alterar o banco local nem a produção.

Cobre edição e recarregamento de casos, parceiros, atendidos, orientações e
usuários; normalização de caso legado; parte sem triagem; validação de enum
legado; erro de gravação sem perder o rascunho; troca de usuário por navegação
SPA; preservação de CPF legado vazio/nulo/inválido e validação de correções;
mensagens específicas de erro403; cabeçalhos JSON/multipart e exceções com/sem `captureStackTrace`.
Executa também os testes existentes `selector.cjs` e `pessoa-juridica.cjs`.
O teste isolado do cliente HTTP empacota o código real com esbuild e substitui
apenas os módulos de ambiente do SvelteKit e a seleção da unidade.

O resultado dessa suíte comprova o comportamento do frontend com os contratos
simulados; não substitui o ensaio de integração com o banco restaurado e DJEN.


## Login, paginação, formulários e arquivos

```bash
PLAYWRIGHT_MODULE=/tmp/gestaolegal-browser/node_modules/playwright \
GL_BASE_URL=http://localhost:5401 node tests/browser/front-check.cjs
```

Intercepta toda a API com dados sintéticos. Verifica login recusado e aceito,
paginação no contrato `PaginatedResult.to_dict()` (`items`, `total`, `page` e `per_page` no mesmo nível), navegação de volta, edição de
atendido/caso/orientação/assistência judiciária, upload multipart e download.
Não acessa banco real. Também pode ser executado contra a imagem Nginx de produção
alterando `GL_BASE_URL` para a porta onde o contêiner está publicado.

## Regressões da auditoria de navegação e CRUD

```bash
PLAYWRIGHT_MODULE=/tmp/gestaolegal-browser/node_modules/playwright \
GL_BASE_URL=http://localhost:5402 node tests/browser/audit-regressions.cjs
```

Usa API sintética. Verifica que o diálogo de processo carrega e preserva os dados,
que alternar entre edição e criação não mistura registros, que processos inativos
não reaparecem após recarregar, que o administrador pode reativar atendidos e que
o breadcrumb de Plantão aponta para uma página existente. A busca real por e-mail
e a autorização/isolamento da reativação são cobertos pelos testes de API.
