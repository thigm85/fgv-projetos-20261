# Task 1: Explorando o Sistema de Origem

Aqui está a implementação da Task 1, usando Terraform para criar o RDS e scripts Python para carregar e validar os dados, seguindo o que o `rds.md` pede.

## Pré-requisitos

- Terraform (versão 1.0 ou superior)
- Credenciais da AWS configuradas via variáveis de ambiente
- Python 3.x
- Acesso à AWS (região us-east-1 por padrão)

## Configuração das Credenciais AWS

Antes de tudo, configure as credenciais da AWS. O jeito mais fácil é usar variáveis de ambiente:

- Copie o `.env.example` para `.env`.
- Preencha o `.env` com suas credenciais reais.
- No terminal, rode: `source .env`.

Exemplo:
```
export AWS_ACCESS_KEY_ID="seu_access_key"
export AWS_SECRET_ACCESS_KEY="sua_secret_key"
export AWS_DEFAULT_REGION="us-east-1"
```

Ou use `aws configure` se preferir.

Certifique-se de que sua conta tem permissões para RDS (como a política `AmazonRDSFullAccess`).

## Instalação de Dependências

Crie um ambiente virtual e instale o que precisa:
```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Lembre-se de ativar o venv sempre que for usar os scripts Python: `source venv/bin/activate`.

## Passos para Executar

1. **Configure o Terraform:**
   - O `terraform.tfvars` já tem valores padrão. Mude a senha se quiser.

2. **Inicialize o Terraform:**
   ```
   terraform init
   ```

3. **Planeje e Aplique:**
   ```
   terraform plan
   terraform apply
   ```
   Confirme quando pedir.

4. **Gere a Configuração:**
   ```
   python3 generate_config.py
   ```
   Isso cria o `rds_config.txt` com os dados de conexão.

5. **Carregue os Dados:**
   ```
   python3 load_data.py
   ```
   Carrega o banco `classicmodels` e os dados do SQL.

6. **Valide:**
   ```
   python3 validate.py
   ```
   Checa se as tabelas foram criadas e têm dados.

## Destruir Recursos

Para não gastar dinheiro à toa, destrua tudo depois:
```
terraform destroy
```

## Notas

- O RDS pode demorar uns minutos para ficar pronto.
- Garanta que a VPC permite acesso na porta 3306.
- Em produção, deixe o RDS privado e ajuste a segurança.