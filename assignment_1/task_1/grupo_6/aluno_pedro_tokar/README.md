# Como rodar

*As instruções abaixo são pensadas para ambientes Linux.*

-------------------

## Provisionamento

Primeiro, vá para o diretório `terraform_config`:

```bash
$ cd terraform_config/
```

De lá, rode os comandos que inciam o terraform e executam o plano:

```bash
$ terraform init
$ terraform apply
```

Revise o plano de execução (que será bem simples) do terraform e digite `yes`
caso concorde com ele. Após isso, o banco irá ser criado na AWS (e essa
operação pode levar até 5 minutos). Você pode inspecionar o link de conexão
do banco tanto no console da AWS quanto no arquivo `terraform_config/terraform.tfstate`.

Pegue o link de conexão do banco e exporte como variável de ambiente (remova a
porta do link! Ele não deve terminar com `:3306`):

```bash
$ export DATABASEHOST=olink.da.aws.aqui.com
```

## Load

Com o banco criado, o próximo passo é popular ele. Para poder usar o script
python, crie um ambiente virtual da forma que preferir e instale os requisitos
nele usando o comando:

```bash
$ pip install -r requirements.txt
```

Agora é necessário voltar para o diretório pai e nele baixar o certificado SSL da
AWS para poder fazer a conexão segura com o banco. Felizmente o download pode ser feito por um comando simples fornecido pela própria AWS:

```bash
$ cd ..
$ curl -o global-bundle.pem https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem
```

Com o certificado no mesmo diretório que o script python e a pasta `data` e 
com o ambiente virtual configurado, basta rodar o script python que irá enviar
as instruções SQL para o banco:

```bash
$ python populate.py
```

Se todos os passos tiverem sido executados corretamente, o banco irá estar
populado.

## Validação

Para verificar se tudo está certo, basta executar (com o mesmo ambiente virtual)
o script de verificação:

```bash
python verify.py
```

Se tudo estiver certo, todas as tabelas terão entradas.
