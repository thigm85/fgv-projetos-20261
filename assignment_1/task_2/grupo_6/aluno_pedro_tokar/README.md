# Como rodar

*As instruções abaixo são pensadas para ambientes Linux.*

-------------------

## Pré-requisitos

- terraform instalado
- AWS CLI instalado

## Tratamento das credenciais do banco

As credenciais do banco de dados não são hardcoded, e devem ser fornecidas antes
da execução de qualquer um desses passos.

Para acesso às credenciais pelos scripts python, é necessário colocar elas
como variáveis de ambiente do seu terminal. Para isso, execute:

```bash
$ export DB_USER="admin_user"
$ export DB_PASSWORD="sua_senha_segura"
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
$ python populate.py
```

Se todos os passos tiverem sido executados corretamente, o banco irá estar
populado. Esse script usa o próprio terraform

## Validação

Para verificar se tudo está certo, basta executar (com o mesmo ambiente virtual)
o script de verificação:

```bash
$ python verify.py
```

Se tudo estiver certo, todas as tabelas terão entradas.

## ETL

O provisionamento irá criar um Job do Glue na AWS, e esse Job irá executar o 
arquivo `glue_etl.py`. Para verificar se o provisionamento realmente criou
o job e executá-lo:

- Acesse o painel da AWS e escolha a região de criação dos recursos;
- Acesse o console do serviço Glue;
- No painel lateral, escolha a opção "Visual ETL"
- O job criado estará listado nesta página. Selecione ele;
- Será possível inspecionar o que o job faz. Aperte em run para executar;
- Vá em "Runs" para acompanhar o status de execução. Após um tempo,
o script deve sair do status de "Running" para "Succeeded".

## Verificação de resultados

Após o Job do AWS Glue finalizar com o status "Succeeded", você pode validar se os dados foram modelados e salvos corretamente dessa forma:

- Acesse o painel da AWS e o console do serviço S3;
- Logo na tela inicial haverá uma lista de buckets. Selecione o bucket adequado (o nome vai começar com `classicmodels-datalake`);
- Navegue até a pasta `output/`. Nela, deverão existir as seguintes pastas:
   - `fact_orders/`
   - `dim_customers/`
   - `dim_products/`
   - `dim_dates/`
   - `dim_countries/`
- Entre em qualquer uma dessas pastas e verifique se há arquivos gerados com a extensão `.parquet`.
