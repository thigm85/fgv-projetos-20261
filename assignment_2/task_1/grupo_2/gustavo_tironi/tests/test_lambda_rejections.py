"""
Testa cenários de rejeição da Lambda gateway.

Envia payloads inválidos diretamente para a Lambda via boto3.invoke
e verifica que a resposta é {"status": "rejected"} com erros esperados.

Não toca o RDS — se a Lambda funcionar como gate, nada é inserido.

Pós-teste: rodar SELECT no RDS para confirmar que NENHUM dos orderNumber
de teste (9990001..9990005) existe em orders.
"""

import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import boto3

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import envlocal

envlocal.load()

REGION = os.environ.get("AWS_REGION", "us-east-1")
FUNCTION = os.environ["LAMBDA_ORDER_GATEWAY"]

lc = boto3.client("lambda", region_name=REGION)


def invoke(payload: dict) -> dict:
    resp = lc.invoke(FunctionName=FUNCTION, Payload=json.dumps(payload).encode("utf-8"))
    return json.loads(resp["Payload"].read())


# Reusa orderNumbers altos para não colidir com simulate normal
FUTURE = (date.today() + timedelta(days=365)).isoformat()
PAST = "2000-01-01"

CASES = [
    {
        "name": "details vazio",
        "payload": {
            "order": {
                "orderNumber": 9990001, "orderDate": FUTURE, "requiredDate": FUTURE,
                "status": "In Process", "comments": "test", "customerNumber": 103,
            },
            "details": [],
        },
        "expect_error_contains": "orderdetails vazio",
    },
    {
        "name": "customerNumber inexistente",
        "payload": {
            "order": {
                "orderNumber": 9990002, "orderDate": FUTURE, "requiredDate": FUTURE,
                "status": "In Process", "comments": "test", "customerNumber": 999999,
            },
            "details": [{"productCode": "S10_1678", "quantityOrdered": 1, "priceEach": 10.0, "orderLineNumber": 1}],
        },
        "expect_error_contains": "customerNumber=999999 não existe",
    },
    {
        "name": "productCode inexistente",
        "payload": {
            "order": {
                "orderNumber": 9990003, "orderDate": FUTURE, "requiredDate": FUTURE,
                "status": "In Process", "comments": "test", "customerNumber": 103,
            },
            "details": [{"productCode": "FAKE_PRODUCT", "quantityOrdered": 1, "priceEach": 10.0, "orderLineNumber": 1}],
        },
        "expect_error_contains": "productCode=FAKE_PRODUCT não existe",
    },
    {
        "name": "orderDate <= watermark",
        "payload": {
            "order": {
                "orderNumber": 9990004, "orderDate": PAST, "requiredDate": PAST,
                "status": "In Process", "comments": "test", "customerNumber": 103,
            },
            "details": [{"productCode": "S10_1678", "quantityOrdered": 1, "priceEach": 10.0, "orderLineNumber": 1}],
        },
        "expect_error_contains": "estritamente posterior ao watermark",
    },
    {
        "name": "quantityOrdered=0",
        "payload": {
            "order": {
                "orderNumber": 9990005, "orderDate": FUTURE, "requiredDate": FUTURE,
                "status": "In Process", "comments": "test", "customerNumber": 103,
            },
            "details": [{"productCode": "S10_1678", "quantityOrdered": 0, "priceEach": 10.0, "orderLineNumber": 1}],
        },
        "expect_error_contains": "quantityOrdered=0 inválido",
    },
]


def main() -> int:
    print(f"Testando rejeições contra Lambda: {FUNCTION}")
    print("=" * 60)
    failures = 0
    for c in CASES:
        result = invoke(c["payload"])
        status = result.get("status")
        errors = result.get("errors") or []
        joined = "; ".join(errors)

        ok = status == "rejected" and c["expect_error_contains"] in joined
        marker = "[ok]  " if ok else "[FAIL]"
        print(f"{marker} {c['name']}")
        print(f"       status={status} errors={joined}")
        if not ok:
            failures += 1

    print("=" * 60)
    print(f"RESULTADO: {len(CASES) - failures}/{len(CASES)} passaram")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
