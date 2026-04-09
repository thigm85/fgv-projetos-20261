# Notas de Aula - Task 1 (RDS)

## Troubleshooting rapido

- Execute os comandos a partir de `assignment_1/solution_task_1/` para que caminhos relativos de `scripts/` e `data/` funcionem.
- Se a instancia RDS ficar muito tempo em `creating`, valide quotas e subnet group na conta/regiao.
- Se o `mysql` falhar em conexao, confirme security group e abertura da porta `3306`.
- Em caso de erro de endpoint ausente, rode `python scripts/provision_rds.py --wait` para atualizar cache local.

## Por que usar `mysql` CLI em vez de ORM?

- Dump SQL grande costuma ser mais confiavel com `mysql` nativo para bulk load.
- Reduz complexidade e custo de manutencao quando o objetivo e reproduzir script de laboratorio.
- Mantem o passo de carga alinhado com fluxo operacional comum em equipes de dados.
