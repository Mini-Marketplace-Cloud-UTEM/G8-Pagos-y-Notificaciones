from fastapi import APIRouter, Header, HTTPException
from typing import Optional
from datetime import datetime, timezone
from app.schemas.payments import CreatePaymentRequest, PaymentResponse

# Importamos los modelos desde nuestra nueva carpeta schemas
from app.schemas.payments import CreatePaymentRequest, PaymentResponse

# Creamos el router. El prefix nos ahorra escribir /v1/payments en cada ruta.
router = APIRouter(prefix="/v1/payments", tags=["Payments"])

@router.post("", response_model=PaymentResponse, status_code=201)
def create_payment(
    request: CreatePaymentRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id"),
    authorization: Optional[str] = Header(None)
):
    """
    Mock del endpoint para iniciar un pago.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return PaymentResponse(
        payment_id="PAY-a1b2c3d4-e5f6-7890-1234-56789abcdef0",
        order_id=request.order_id,
        user_id=request.user_id,
        amount=request.amount,
        currency=request.currency,
        method=request.method,
        status="APPROVED",
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        failure_reason=None,
        created_at=now,
        updated_at=now
    )