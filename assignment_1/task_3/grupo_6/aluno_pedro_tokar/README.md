# Como rodar

*As instruções abaixo são pensadas para ambientes Linux.*

-------------------

## Pré-requisitos

- terraform instalado
- AWS CLI instalado

## Tratamento das credenciais do banco

As credenciais do banco de dados não são hardcoded, e devem ser fornecidas antes
da execução de qualquer um desses passos.

Para acesso às credenciais pelos scripts python, é necessário definir as
variáveis em um arquivo de ambiente. Na raiz do projeto, crie um arquivo chamado
`.env` com o seguinte conteúdo:

```env
DB_USER="admin_user"
DB_PASSWORD="sua_senha_segura"
```

Para que o terraform leia as credenciais, é necessário que elas sejam passadas
em um arquivo `tfvars` ou que sejam fornecidas direto na execução dos comandos.
Para a primeira opção, crie um arquivo `terraform.tfvars` na pasta 
`terraform_config` com a seguinte estrutura:

```tf
db_username  = "admin_user"
db_password  = "sua_senha_segura"
```

Caso opte por seguir a segunda opção, não crie nenhum arquivo. Qaudno os
comandos do terraform forem executados, eles irão solicitar a senha do banco.
O nome o banco será o valor default `admin_user`.

## Provisionamento

O provisionamento é feito inteiramente pela ferramenta `terraform`. Para que o
terraform consiga se conectar com a AWS e aplicar mudanças nela, é necessário
fornecer as credenciais de acesso à AWS. O terraform usa as credenciais do
mesmo jeito que a AWS CLI usa: elas devem ser armazenadas no arquivo 
`~/aws/credentials`.

Com as credenciais configuradas, vá para o diretório `terraform_config`:

```bash
$ cd terraform_config/
```

De lá, rode os comandos que inciam o terraform e executam o plano:

```bash
$ terraform init
$ terraform plan
$ terraform apply
```

Quando o comando `terraform plan` for executado, o terraform mostrará qual
o plano de execução para poder levantar a infraestrutura na AWS. Caso o plano
faça sentido, execute o comando `terraform apply` e digite `yes` quando ele
pedir confirmação. Após isso, o banco irá ser criado na AWS (e essa
operação pode levar até 5 minutos).

> O terraform é uma ferramenta madura para o gerenciamento de infraestrutura
em nuvem, e verifica automaticamente quais serviços já existem na AWS antes
de iniciar a execução. Assim, os casos de infraestrutura que já existe ou que
de alguma forma diverge da definida irão ser tratados pelo terraform, sem
necessidade de intervenção manual.

Após o provisionamento, retorne para a pasta raiz da solução:

```bash
$ cd ..
```

## Load

Com o banco criado, o próximo passo é popular ele. Para poder usar o script
python, crie um ambiente virtual da forma que preferir e instale os requisitos
nele usando o comando:

```bash
$ pip install -r requirements.txt
```

Agora é necessário baixar o certificado SSL da AWS para poder fazer a conexão 
segura com o banco. Felizmente o download pode ser feito por um comando simples 
fornecido pela própria AWS:

```bash
$ curl -o global-bundle.pem https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem
```

Com o certificado no mesmo diretório que o script python e a pasta `data` e 
com o ambiente virtual configurado, basta rodar o script python que irá enviar
as instruções SQL para o banco:

```bash
$ python scripts/populate.py --endpoint_url=$(terraform -chdir=terraform_config output -raw db_endpoint)
```

Se todos os passos tiverem sido executados corretamente, o banco irá estar
populado. Esse script usa o próprio output do terraform para obter o endpoint
do banco RDS que foi provisionado.

## Validação

Para verificar se tudo está certo, basta executar (com o mesmo ambiente virtual)
o script de verificação:

```bash
$ python scripts/verify_rds.py --endpoint_url=$(terraform -chdir=terraform_config output -raw db_endpoint)
```

Se tudo estiver certo, todas as tabelas terão entradas.

## ETL

O provisionamento irá criar um Job do Glue na AWS, e esse Job irá executar o 
arquivo `glue_etl.py`. Para executar o job e verificar se ele consegue executar com status "Succeeded", existem duas opções:

### Opção automática

Para disparar o pipeline e monitorar o progresso em tempo real direto de um
terminal em sua máquina local, execute o script `run_etl.py`:

```bash
$ python scripts/run_etl.py --job_name="classicmodels_etl_to_star_schema"
```

Este script inicializa o cliente do AWS Glue, dispara o job
`classicmodels_etl_to_star_schema`, monitora o ciclo de vida da execução via um
polling a cada 30 segundos e encerra com um código de saída que indica se a
operação deu certo (0 para sucesso e 1 para falha).

### Opção manual

- Acesse o painel da AWS e escolha a região de criação dos recursos;
- Acesse o console do serviço Glue;
- No painel lateral, escolha a opção "Visual ETL"
- O job criado estará listado nesta página. Selecione ele;
- Será possível inspecionar o que o job faz. Aperte em run para executar;
- Vá em "Runs" para acompanhar o status de execução. Após um tempo,
o script deve sair do status de "Running" para "Succeeded".

## Verificação de resultados

Após o Job do AWS Glue finalizar com o status "Succeeded", você pode validar se os dados foram modelados e salvos corretamente por dois caminhos:

### Opção automática

Execute o script `verify_s3.py` para realizar uma varredura completa e programática sobre os dados salvos no S3:

```Bash
$ python scripts/verify_s3.py --bucket_name=$(terraform -chdir=terraform_config output -raw datalake_bucket)
```

Este script automatiza as checagens baseadas nos seguintes critérios de
aceitação:

1. Existência Estrutural: Garante que as pastas das 5 entidades (`fact_orders`,
`dim_customers`, `dim_products`, `dim_dates`, `dim_countries`) existem no bucket
S3 e contêm dados populados.

2. Integridade Referencial: Valida se todos os registros de chaves
(`customer_id` e `product_id`) na tabela fato possuem correspondência exata nas
dimensões mapeadas.

3. Validação de Regra de Negócio: Verifica de forma exata se o cálculo do campo
`sales_amount` condiz perfeitamente com a regra matemática 
`quantity_ordered * price_each`.

### Opção manual

- Acesse o painel da AWS e o console do serviço S3;
- Logo na tela inicial haverá uma lista de buckets. Selecione o bucket adequado (o nome vai começar com `classicmodels-datalake`);
- Navegue até a pasta `output/`. Nela, deverão existir as seguintes pastas:
   - `fact_orders/`
   - `dim_customers/`
   - `dim_products/`
   - `dim_dates/`
   - `dim_countries/`
- Entre em qualquer uma dessas pastas e verifique se há arquivos gerados com a extensão `.parquet`.

## Dashboard analítico

Com todos os passos e scripts executados, o data lake estará pronto para análises. Uma entrada é criada no 
catálogo de dados do AWS Glue, e pode ser acessada por diversas ferramentas de análise, incluindo o Amazon Athena.
O notebook [`dashboard.ipynb`](./dashboard.ipynb) contém um dashboard de exemplo que lê desses dados.

Esse notebook foi pensado para ser executado no mesmo ambiente em que o terraform foi executado, e usa o
comando `terraform output` para obter dados da infraestrutura na AWS. É necessário sobreescrever esses dados
no notebook caso o ambiente do terraform não esteja disponível. O notebook depende das bibliotecas listadas
no arquivo `requirements.txt` para executar corretamente.
