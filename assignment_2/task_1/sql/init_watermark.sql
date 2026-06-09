-- Task 1 (3.1) — Inicialização do watermark (versão SQL pura, idempotente).
-- Equivalente ao scripts/init_watermark.py. Rode no banco classicmodels.
--
-- Uso:
--   mysql -h <endpoint> -P 3306 -u admin -p classicmodels < init_watermark.sql

-- 1. Cria a tabela de controle se não existir.
CREATE TABLE IF NOT EXISTS etl_watermark (
    pipeline_name             VARCHAR(64)  NOT NULL,
    last_processed_order_date DATE,
    last_run_at               DATETIME,
    last_run_status           VARCHAR(32),
    PRIMARY KEY (pipeline_name)
) ENGINE=InnoDB DEFAULT CHARSET=latin1;

-- 2 + 3. Insere o registro inicial SOMENTE se ausente, inicializando
-- last_processed_order_date com o MAX(orderDate) atual.
-- INSERT IGNORE + PK garante idempotência: reexecução não sobrescreve
-- um watermark já avançado pela Task 2.
INSERT IGNORE INTO etl_watermark
    (pipeline_name, last_processed_order_date, last_run_at, last_run_status)
SELECT 'classicmodels_sales', MAX(orderDate), UTC_TIMESTAMP(), 'NEVER_RUN'
FROM orders;

-- Conferência:
SELECT * FROM etl_watermark WHERE pipeline_name = 'classicmodels_sales';
