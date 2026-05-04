import pymysql

def load_data(host, port, user, password, database, sql_file):
    connection = pymysql.connect(
        host=host,
        port=int(port),
        user=user,
        password=password,
        database=database,
        autocommit=True,
        client_flag=pymysql.constants.CLIENT.MULTI_STATEMENTS
    )

    with connection.cursor() as cursor:
        with open(sql_file, 'r') as f:
            sql = f.read()
            cursor.execute(sql)
            print("Dados carregados com sucesso.")

    connection.close()

if __name__ == "__main__":
    # Read config
    config = {}
    with open('rds_config.txt', 'r') as f:
        for line in f:
            key, value = line.strip().split('=')
            config[key] = value

    sql_file = '../../data/mysqlsampledatabase.sql'  # Adjust path
    load_data(
        config['endpoint'],
        config['port'],
        config['username'],
        config['password'],
        config['database'],
        sql_file
    )