# Task 2 - Pipeline ETL com AWS Glue

---

## Passo a passo

### 1. Dependências locais

```bash
pip install -r requirements.txt
```

### 2. Gerar terraform.tfvars

O script lê o `rds_credentials.json` (gerado na Task 1) e o `.env`:

```bash
# Certifique-se de que o .env está acessível e o rds_credentials.json existe
python scripts/1_setup_tfvars.py
```

> Ajuste a variável `CREDENTIALS_FILE` no topo do script se o arquivo estiver em outro local.

### 3. Provisionar a infraestrutura

```bash
terraform init
terraform plan
terraform apply
```

O Terraform irá criar:
- **S3 Bucket** para os dados Parquet e o script do Glue
- **VPC Endpoint S3** (gratuito, melhora segurança)
- **Security Group do Glue** com regras mínimas (self-referencing + egress restrito)
- **Regra de Ingress no SG do RDS** permitindo conexão do Glue
- **Glue Connection JDBC** com roteamento de rede via VPC
- **Glue Job** configurado com `LabRole` (role padrão do AWS Academy)

### 4. Exportar outputs do Terraform

```bash
terraform output -json > ../tf_outputs.json
```

O script de validação usa este arquivo para encontrar o bucket e o job name.

### 5. Executar e validar o pipeline

**Opção A — Disparar o job e validar em sequência (recomendado):**
```bash
python scripts/3_validate_etl.py --trigger
```

**Opção B — Disparar manualmente pelo console da AWS e depois validar:**
```bash
# Aguarda o run mais recente e valida
python scripts/3_validate_etl.py
```

**Opção C — Via AWS CLI:**
```bash
aws glue start-job-run --job-name classicmodels-etl-job --region us-east-1
# Acompanhe no console ou use o script de validação
python scripts/3_validate_etl.py --skip-wait
```

**Dry run (sem efeito real):**
```bash
python scripts/3_validate_etl.py --dry-run
```

---

## Esquema Estrela produzido

```
                    ┌──────────────────┐
                    │   dim_dates      │
                    │  date_key (PK)   │
                    │  full_date       │
                    │  year/quarter/   │
                    │  month/day       │
                    └────────┬─────────┘
                             │
┌─────────────┐    ┌─────────▼──────────┐    ┌──────────────────┐
│ dim_customers│    │    fact_orders     │    │  dim_products    │
│ customer_id ◄────┤ order_id           ├────► product_id       │
│ customer_name│    │ customer_id (FK)  │    │ product_name     │
│ contact_name │    │ product_id (FK)   │    │ product_line     │
│ city        │    │ order_date_key(FK)│    │ product_vendor   │
│ country     │    │ country_key (FK)  │    └──────────────────┘
└─────────────┘    │ quantity_ordered  │
                    │ price_each       │    ┌──────────────────┐
                    │ sales_amount     ├────► dim_countries    │
                    └──────────────────┘    │ country_key (PK) │
                                            │ country          │
                                            │ territory        │
                                            └──────────────────┘
```

---

## Critérios de validação (item 4.6 do enunciado)

| Critério | Como é verificado |
|---|---|
| Job finaliza com `SUCCEEDED` | `3_validate_etl.py` monitora o status via boto3 |
| Parquet de `fact_orders` e dimensões existem no S3 | Listagem de objetos S3 com verificação de tamanho > 0 |
| Fato contém registros e referencia chaves válidas | Checagem de integridade referencial (subset de chaves) |
| `sales_amount == quantity_ordered * price_each` | Comparação numérica com tolerância de 1 centavo |

---

## Segurança

- **Zero 0.0.0.0/0 em Ingress**: SG do Glue usa apenas self-referencing
- **Egress restrito**: apenas porta 443 (HTTPS para AWS APIs) e 3306 para o SG do RDS
- **Zero hardcode**: credenciais via `TF_VAR_*` / `terraform.tfvars` + `.env`
- **LabRole**: usa a role pré-existente do AWS Academy
- **VPC Endpoint S3**: tráfego S3 não sai pela internet

---
