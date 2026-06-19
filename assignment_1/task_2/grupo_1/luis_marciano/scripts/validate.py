import pymysql

def validate_database(host, port, user, password, database):
    connection = pymysql.connect(
        host=host,
        port=int(port),
        user=user,
        password=password,
        database=database
    )

    tables = ['customers', 'products', 'productlines', 'orders', 'orderdetails', 'payments', 'employees', 'offices']

    with connection.cursor() as cursor:
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"Tabela {table}: {count} linhas")

    connection.close()
    print("Validação concluída.")

if __name__ == "__main__":
    # Read config
    config = {}
    with open('rds_config.txt', 'r') as f:
        for line in f:
            key, value = line.strip().split('=')
            config[key] = value

    validate_database(
        config['endpoint'],
        config['port'],
        config['username'],
        config['password'],
        config['database']
    )