# Roteiro de testes — dados jurídicos de PJ (#114)

Referência: [issue #114](https://github.com/LabP2/gestaolegal/issues/114).

## Preparação

- Acesse o ambiente local em <http://localhost:5001> e entre como administrador.
- Use um atendido fictício com **PJ Constituída = Sim** e outro com **PJ Constituída = Não**.
- Preencha os demais campos obrigatórios durante os testes.
- O banco deve estar na migration `e2f3a4b5c6d7` ou posterior.

## Testes manuais

| Teste | Ação | Resultado esperado |
|---|---|---|
| 1. Converter em assistido | Clique em **Tornar Assistido** do atendido com PJ constituída. | A seção **Dados Jurídicos** começa por **Enquadramento**. |
| 2. Informar sócios | Selecione **Microempresa**, informe quantidade **2** e nomes **Ana Teste** e **João Teste**. | Aparecem exatamente dois campos de nomes. |
| 3. Salvar e consultar | Selecione situação **Ativa**, salve e abra o perfil. Recarregue a página. | Os dados permanecem salvos. A ordem é enquadramento, sócios e situação perante a Receita Federal. |
| 4. Alterar quantidade | Edite, aumente para **3**, preencha o terceiro nome e depois reduza para **2**. Salve. | O terceiro campo desaparece; os dois primeiros nomes são preservados. O perfil mostra dois sócios. |
| 5. Validar “Outros” | Selecione **Outros**, deixe a especificação vazia e tente salvar. Depois preencha **Associação**, salve e confira no perfil. | O formulário exige **Especifique o enquadramento da PJ** antes de salvar. Após preencher, o perfil apresenta a especificação e a mantém ao recarregar. |
| 6. Mudar para MEI | Edite o cadastro com sócios e selecione **Microempreendedor Individual**. Salve e recarregue. | Quantidade, nomes dos sócios e especificação de “Outros” desaparecem. Os sócios anteriores deixam de aparecer no perfil. |
| 7. Sair de MEI | Edite novamente e selecione **Microempresa**. | Os nomes anteriores não reaparecem. É necessário informar os sócios novamente. |
| 8. Validar nomes | Deixe um nome vazio ou somente com espaços e tente salvar. | O formulário bloqueia o envio e pede o nome do sócio. |
| 9. Conferir pessoa física | Abra **Tornar Assistido** do atendido com **PJ Constituída = Não**. | A seção **Dados Jurídicos** não aparece. |

## Registro da execução

Para cada cenário, registre **passou** ou **falhou**. Em caso de falha, anote
o número do teste, a ação realizada e o resultado observado. Use somente dados
fictícios nas evidências.

## Verificação automatizada

- API: `tests/api/test_dados_juridicos_pj_api.py`.
- Migration: `tests/database/test_dados_juridicos_pj_migration.py`.
- Navegador: `tests/browser/pessoa-juridica.cjs`; instruções em [tests/browser/README.md](../tests/browser/README.md).
