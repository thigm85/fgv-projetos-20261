# Um Exemplo do Ciclo de Vida de Engenharia de Dados

Este trabalho é uma adaptação de um exercício presente no curso [Introduction to Data Engineering](https://www.coursera.org/learn/intro-to-data-engineering), que integra o DeepLearning.AI Data Engineering Professional Certificate.

Neste laboratório, você irá configurar e executar um exemplo de pipeline de dados que demonstra todas as etapas do ciclo de vida da engenharia de dados. Seu sistema de origem será um banco de dados relacional instanciado como um banco MySQL no Amazon RDS (Relational Database Service). Primeiro, você irá explorar o banco de dados de origem utilizando um conjunto de dados de exemplo, depois usará o AWS Glue para extrair, transformar e carregar (ETL) os dados no seu pipeline, armazenando-os no serviço de armazenamento de objetos da AWS, o Amazon S3. Por fim, você irá consultar os dados armazenados utilizando o Amazon Athena para montar um dashboard de visualização de dados no Jupyter Lab. Para definir e configurar os componentes deste exemplo de pipeline de dados, será utilizado o Terraform como serviço de Infraestrutura como Código (IaC).

## 1 - Introdução

Suponha que você trabalha como Engenheiro de Dados em uma loja de carros clássicos e outros meios de transporte. Essa loja armazena seus históricos de compras e as informações de seus clientes em um banco de dados relacional que contém as seguintes tabelas: customers, products, productlines, orders, orderdetails, payments, employees, offices. Neste laboratório, você usará um exemplo desse banco de dados: [MySQL Sample Database](https://www.mysqltutorial.org/mysql-sample-database.aspx)

O analista de dados do time de marketing está interessado em analisar os históricos de compras para entender, por exemplo, qual linha de produtos é mais bem-sucedida e como as vendas estão distribuídas entre os diferentes países. Embora o analista de dados possa consultar diretamente os dados no banco relacional, pode ser necessário escrever consultas complexas que podem levar muito tempo para recuperar as informações desejadas. Realizar consultas analíticas em bancos de dados de produção geralmente não é uma boa ideia, pois pode impactar o desempenho desses bancos. Seu trabalho como Engenheiro de Dados é construir um pipeline de dados que transforme os dados em uma forma mais fácil de entender e mais rápida de consultar, servindo-os para o analista de dados focar apenas na análise.

Neste laboratório, você irá explorar um exemplo de ponta a ponta que mostra a implementação das etapas do ciclo de vida de engenharia de dados na AWS.

Vamos começar explorando o sistema de origem!

## 2 - Task 1: Explorando o Sistema de Origem

O primeiro desafio é criar e popular o sistema de origem do pipeline: um banco de dados MySQL provisionado no Amazon RDS, contendo as tabelas necessárias para o laboratório.

Recomendamos organizar esse processo com scripts Python para automatizar e tornar as etapas reprodutíveis, facilitando a execução a partir do seu computador local:

- **Provisionamento do RDS:** Script para criar sua instância de banco MySQL no Amazon RDS.
- **Load de Dados:** Script para criar o banco `classicmodels` e carregar os dados de exemplo do arquivo SQL.
- **Validação:** Script para conferir se todas as tabelas foram criadas e populadas corretamente.

O uso desses scripts ajuda a evitar erros manuais, melhora a rastreabilidade e possibilita que todo o fluxo seja executado diretamente do seu ambiente local, seja via terminal, scripts ou ferramentas gráficas, conforme sua preferência.

**Fluxo sugerido:**

1. Execute o script de provisionamento para criar sua instância MySQL no RDS.
2. Use o script de carga para criar e popular o banco `classicmodels` com os dados de exemplo.
3. Execute o script de validação para garantir que as tabelas e dados estão corretos.

Você deve ser capaz de executar todas as etapas acima a partir do seu computador local, registrando e utilizando as informações essenciais de acesso ao banco (nome, usuário administrador, senha e endpoint). Nos próximos passos, esse banco será utilizado como sistema de origem para o pipeline de dados.