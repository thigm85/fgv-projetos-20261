import pymysql

conn = pymysql.connect(
    host="classicmodels-db.cluster-c5rn2caeukns.us-east-1.rds.amazonaws.com",
    user="admin",
    password="i3t8urB2mQAu4s9",
    port=3306
)

print("Conectado!")


cursor = conn.cursor()

#Ver bancos
cursor.execute("SHOW DATABASES;")
print("Bancos:", cursor.fetchall())

#Usar o banco
cursor.execute("USE classicmodels;")

#Ver tabelas
cursor.execute("SHOW TABLES;")
print("Tabelas:", cursor.fetchall())