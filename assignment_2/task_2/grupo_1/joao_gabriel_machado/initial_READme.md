# Guia de Inicialização do Zero

### Passo 1: Preparar as Variáveis (`terraform.tfvars`)

Antes de tocar no Terraform, você precisa definir o IP e a senha.

1. Entre na pasta `terraform/`.
2. Crie ou edite o arquivo `terraform.tfvars`.
3. Adicione o seu IP público atual e as credenciais desejadas:
```hcl
db_identifier = "sales-analytics-db"
db_user       = "admin"
db_password   = "xxx.xxx.xxx"
my_ip         = "xxx.xxx.xx.xxx/32" # IP atual com /32
```

### Passo 2: Usar o Terraform e dar Apply

Com as variáveis prontas, vamos mandar a AWS criar os servidores, redes e buckets.
No terminal, dentro da pasta `terraform/`, rode os três comandos sagrados:

```bash
# Baixa os drivers/plugins da AWS
terraform init

# Valida o que será criado (mostra o que foi modificado, criado ou deletado)
# Se modificou algo não relacionado com as mudanças -> rever pasta de terraform
terraform plan

# Cria tudo na AWS
terraform apply

```

Terraform vai demorar de 3 a 5 minutos para criar o banco RDS. Depois de tudo, ele vai cuspir o endereço do banco (`rds_endpoint`) na tela e criar o seu arquivo `.env` automaticamente via `provisioner.tf`. Não precisa de mais "set" de .env. Ele já roda os comandos para popular o banco (add_data_db.py) automaticamente.

### Passo 3: O Ponto de Partida do Watermark

Com o banco criado e com os dados históricos dentro dele, agora só precisamos rodar o init_watermark.py. Ainda na pasta `sql/`, rode o comando:

```bash
python init_watermark.py
```

---

### Resumo em 4 Linhas:

```bash
cd terraform && terraform init && terraform apply # -auto-approve se certo 
cd ../sql
python init_watermark.py
```