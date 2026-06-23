class CFG:
    # AWS Infra
    REGION = 'us-east-1'
    SG_NAME = 'classicmodels-sg'
    
    # RDS Instance
    DB_ID = 'classicmodels-instance'
    DB_USER = 'admin'
    DB_PASS = 'SenhaForteBemDificil123456789'
    DB_CLASS = 'db.t3.micro'
    DB_ENGINE = 'mysql'
    DB_STORAGE = 20
    
    # Database & Data
    DB_NAME = 'classicmodels'
    SQL_PATH = 'assignment_1/task_1/data/mysqlsampledatabase.sql'
    
    # endpoint obtained after creating the instance
    DB_HOST = "classicmodels-instance.cswuziyho5un.us-east-1.rds.amazonaws.com"
