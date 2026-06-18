# Terraform — Infraestrutura do laboratório

Provisiona toda a stack AWS necessária para as Tasks 1, 2 e 3:
RDS MySQL (origem), S3 (data lake), Glue (ETL Spark) e Athena (consultas analíticas).

## Visão geral dos recursos

| Bloco | Recursos | Função |
|---|---|---|
| **Origem (Task 1)** | `aws_db_instance.mysql`, `aws_db_subnet_group.lab`, `aws_security_group.rds` | RDS MySQL `db.t3.micro` com schema `classicmodels`. Acesso liberado para seu IP público (auto-detectado via `checkip.amazonaws.com`). |
| **Credenciais** | `aws_secretsmanager_secret.db_secret` | JSON com `username/password/host/port/dbname`. Usado pelo Glue job e Connection. |
| **Data lake (Task 2)** | `aws_s3_bucket.data` | Bucket onde o Glue grava Parquet particionado e o script ETL. |
| **Rede do Glue** | `aws_security_group.glue` + self-rule, `aws_vpc_endpoint.s3`, `aws_vpc_endpoint.secretsmanager` | Glue precisa de SG self-referencing e endpoints VPC (S3 + Secrets Manager) para rodar dentro da VPC. |
| **ETL (Task 2)** | `aws_glue_connection.rds_conn`, `aws_glue_job.etl`, `aws_s3_object.glue_script` | Upload do script `glue/glue_job_main.py` para S3 + job Glue 4.0 com 2 workers `G.1X`. |
| **Catalog (Task 3)** | `aws_glue_catalog_database.analytics`, `aws_glue_crawler.fallback` | Database `classicmodels_analytics`. O job registra tabelas direto via `enableUpdateCatalog`. Crawler é fallback manual. |
| **Athena (Task 3)** | `aws_athena_workgroup.lab`, `aws_s3_bucket.athena_results` | Workgroup dedicado + bucket separado para resultados (lifecycle de 7 dias). |
| **Outputs** | `local_file.env` | Grava `src/.env` com todas as variáveis para os scripts Python e o notebook. |

### Decisões de design

- **IAM via `LabRole` existente** (`data.aws_iam_role.glue`) — ambiente acadêmico não permite criar roles. Lookup, não create.
- **Security groups separados** para RDS e Glue. Glue tem self-referencing rule (Glue ENIs falam entre si) + regra explícita liberando 3306 do SG do Glue para o SG do RDS.
- **VPC endpoints obrigatórios** — Glue não consegue acessar S3 nem Secrets Manager via internet quando roda dentro da VPC default. S3 vai por gateway endpoint (route table), Secrets Manager por interface endpoint (ENI na mesma AZ do RDS).
- **AZ matching** — `aws_glue_connection.physical_connection_requirements` precisa da subnet na mesma AZ do RDS, senão o job falha com erro de rede.
- **Catalog via job, crawler como fallback** — o Glue job usa `sink.enableUpdateCatalog=True` para registrar tabelas atomicamente. Crawler `classicmodels-fallback-crawler` só roda on-demand se schema drift quebrar o sink.
- **Bucket de resultados separado** com `lifecycle_configuration` (7 dias) para Athena. Mantém o data lake limpo.

## Como rodar

```bash
terraform init
terraform plan       # revisão
terraform apply      # cria tudo
```

Tempo total esperado: **~8–12 min** (RDS sozinho leva 5–7 min).

Após `apply`, os outputs aparecem no terminal e o arquivo `src/.env` é gerado automaticamente com tudo o que os scripts e o notebook precisam.

## Fluxo após `apply`

1. **Task 1** — carregar dados no RDS:
   ```bash
   python src/load.py && python src/validate.py
   ```
2. **Task 2** — executar Glue job (escreve Parquet + registra tabelas no Catalog):
   ```bash
   aws glue start-job-run --job-name classicmodels-etl-job
   python src/validate_etl.py
   ```
3. **Task 3** — abrir `notebook/dashboard.ipynb` (consome Athena).

## Cleanup

```bash
terraform destroy
```

Remove RDS, buckets (incluindo `athena_results` via `force_destroy`), Glue job, workgroup, secret e SGs.