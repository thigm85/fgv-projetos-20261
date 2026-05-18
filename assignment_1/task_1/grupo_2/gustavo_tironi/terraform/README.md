## O que precisamos declarar

| Recurso | Função / Observação |
|---------|---------------------|
| `provider "aws"` | Define a região (e, opcionalmente, o perfil a ser usado). |
| `aws_db_subnet_group` | Obrigatório pela AWS: indica em quais sub-redes (AZs) o RDS pode ficar. |
| `aws_security_group` | Necessário para liberar acesso na porta 3306 para o seu IP. |
| `aws_db_instance` | Cria a instância MySQL propriamente dita. |

### Por que security group “personalizado”

O Security Group default (Firewall) da VPC **não** expõe o RDS para a internet. Então, para acessar pelo meu computador, precisei fazer um Security Group que libera meu IP para acesso.

## Como rodar

Pré-requisito: `terraform.tfvars` com `senha_master` e `meu_ip` (IP público, use https://checkip.amazonaws.com/).

**`terraform init`** — baixa o provider e prepara a pasta.

Saída esperada (trecho):

```text
Initializing the backend...

Initializing provider plugins...
- Reusing previous version of hashicorp/aws from the dependency lock file
- Using previously-installed hashicorp/aws v5.100.0

Terraform has been successfully initialized!
```

Vai demorar alguns segundos e então aparecer:

```text
You may now begin working with Terraform. Try running "terraform plan" to see
any changes that are required for your infrastructure. All Terraform commands
should now work.

If you ever set or change modules or backend configuration for Terraform,
rerun this command to reinitialize your working directory. If you forget, other
commands will detect it and remind you to do so if necessary.
```

**`terraform plan`** — mostra o que será criado/alterado (não muda nada na AWS).

Em conta “vazia” para esse projeto, algo como:

```text
Terraform will perform the following actions:

  # aws_db_instance.mysql will be created
  + resource "aws_db_instance" "mysql" {
      + address                               = (known after apply)
      ...
      + engine                                = "mysql"
      + engine_lifecycle_support              = (known after apply)
      + engine_version                        = "8.4.7"
      ...
      + instance_class                        = "db.t3.micro"
      ...
      + username                              = "admin"
      + vpc_security_group_ids                = (known after apply)
    }

  # aws_db_subnet_group.lab will be created
  + resource "aws_db_subnet_group" "lab"
  ...

  # aws_security_group.mysql will be created
  + resource "aws_security_group" "mysql"
  ...

Plan: 3 to add, 0 to change, 0 to destroy.

Changes to Outputs:
  + endpoint = (known after apply)
  + porta    = (known after apply)
  + usuario  = "admin"
```


Observe que o comando `terraform plan` mostra todas as ações que o Terraform pretende executar. Ele apenas exibe as mudanças necessárias, caso algum recurso já exista e esteja correto, ele não será recriado ou modificado.

**`terraform apply`** — cria de fato

Aqui, vai demorar um pouco e a saída esperada é:

```text
data.aws_vpc.default: Reading...
data.aws_vpc.default: Read complete after...
data.aws_subnets.default: Reading...
data.aws_subnets.default: Read complete after...
aws_security_group.mysql: Creating...
aws_security_group.mysql: Creation complete after..
aws_db_instance.mysql: Creating...
aws_db_instance.mysql: Still creating...
...
#aqui vai demorar um pouco, ta criadno o RDS
...
aws_db_instance.mysql: Creation complete
```

No fim, no terminal aparecem os **outputs**, por exemplo:

```text
endpoint = "lab-mysql-classicmodels.xxxx.us-east-1.rds.amazonaws.com"
porta = 3306
usuario = "admin"
```

**`terraform destroy`** — remove o que está no state (útil para encerrar o lab e custo).
