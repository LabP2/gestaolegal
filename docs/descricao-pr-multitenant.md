# Multitenancy por NPJ: isolamento, administração e validação em MySQL

Descrição preparada para a publicação da branch completa. O PR remoto #425
ainda termina em `4179632` (PRs 1–2); não substituir sua descrição por este
texto antes de publicar os commits restantes e as correções locais.

---

Permite atender vários NPJs no mesmo banco, mantendo cada registro e anexo
restrito à instituição. O e-mail identifica o NPJ no login; o JWT carrega o
tenant e diferencia sessões de NPJ e de administração da plataforma.

- M1–M3 criam os tenants, acrescentam `tenant_id` obrigatório às 28 tabelas de
  negócio e impõem 53 FKs compostas. A M3 recusa referências inválidas antes
  de alterar o esquema e preserva os índices no ciclo de downgrade/upgrade.
- Os repositórios filtram o tenant. A guarda confere os parâmetros efetivos de
  cada execução e lote, os ramos de UNION e alterações de `tenant_id`; SQL
  textual e construções sem suporte são recusados. A limitação conhecida de
  não provar a semântica de OR permanece documentada no plano.
- A plataforma cria NPJ, unidade e primeiro administrador na mesma transação,
  com link de primeiro acesso. Desativação impede login, uso de JWT e consumo
  de links de senha enquanto o NPJ estiver inativo.
- Anexos ficam em `<raiz>/<tenant_id>/<categoria>`, sem leitura do layout antigo.
- Seed cria dois NPJs fictícios; reset recusa NPJs fora da lista de demonstração.
- O importador de BH/Nova Lima e seus testes exclusivos são retirados: a fusão
  já foi concluída. O histórico foi preservado na documentação e no Git.

## Validação

Resultados e limites em `docs/resultado-testes-multitenant.md`.

- Suíte Python completa e módulos de segurança em ordens inversas.
- Ensaio reproduzível em MySQL 8.0.42 descartável:
  `MULTITENANT_MYSQL_TEST=1 uv run pytest tests/database/test_multitenant_mysql.py -v`.
  Inclui G1–G5 e fluxos da API com guarda e FKs ativas, sem SMTP.
- Checks do frontend comparados com `b8f2f8d`: mesmos 21 erros de tipagem e
  dois arquivos com divergência de formatação; não foram introduzidos novos.
- Head único do Alembic: `c2d3e4f5a6b7`.

## Revisão e implantação

Revisar migrations, autenticação, filtro de tenant e contratos API/frontend.
Antes de implantar, ensaiar a migração dos anexos e as migrations no ambiente
autorizado, com backup e janela apropriados. Nenhuma operação sobre QA,
produção ou dados reais foi executada nesta revisão.
