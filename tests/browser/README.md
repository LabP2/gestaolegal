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
