"""
app/services/payments_mock.py

Datos estáticos (falsos) usados por el Mock API de la Entrega E2 para
las consultas de pagos (GET by id, GET list paginado).

No hay base de datos real todavía: esta lista en memoria simula la
tabla "payments". Las keys usan snake_case porque PaymentResponse
tiene populate_by_name=True y puede construirse directamente con
PaymentResponse(**record).
"""

MOCK_PAYMENTS = [
    {
        "payment_id": "PAY-a1b2c3d4-e5f6-7890-1234-56789abcdef0",
        "order_id": "ORD-20260611-001",
        "user_id": "e9d8c7b6-a543-2109-8765-fedcba098765",
        "amount": 59990,
        "currency": "CLP",
        "method": "MERCADOPAGO",
        "status": "APPROVED",
        "idempotency_key": "11111111-2222-4333-8444-555555555555",
        "correlation_id": "99999999-8888-4777-9666-555555555555",
        "failure_reason": None,
        "created_at": "2026-06-15T20:00:00Z",
        "updated_at": "2026-06-15T20:00:01Z",
    },
    {
        "payment_id": "PAY-b2c3d4e5-f6a7-8901-2345-67890abcdef1",
        "order_id": "ORD-20260611-001",
        "user_id": "e9d8c7b6-a543-2109-8765-fedcba098765",
        "amount": 59990,
        "currency": "CLP",
        "method": "MERCADOPAGO",
        "status": "REJECTED",
        "idempotency_key": "22222222-3333-4444-8555-666666666666",
        "correlation_id": "99999999-8888-4777-9666-555555555556",
        "failure_reason": "Fondos insuficientes.",
        "created_at": "2026-06-15T19:55:00Z",
        "updated_at": "2026-06-15T19:55:02Z",
    },
    {
        "payment_id": "PAY-c3d4e5f6-a7b8-9012-3456-78901abcdef2",
        "order_id": "ORD-20260612-002",
        "user_id": "f0e1d2c3-b4a5-6789-0123-456789abcdef",
        "amount": 15000,
        "currency": "CLP",
        "method": "TRANSBANK",
        "status": "PENDING",
        "idempotency_key": "33333333-4444-4555-8666-777777777777",
        "correlation_id": None,
        "failure_reason": None,
        "created_at": "2026-06-16T10:00:00Z",
        "updated_at": "2026-06-16T10:00:00Z",
    },
]
