from fastapi import APIRouter, Header, HTTPException
from typing import Optional
from datetime import datetime, timezone
from app.schemas.payments import CreatePaymentRequest, PaymentResponse
from pydantic import BaseModel

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

    


class ConfirmPaymentRequest(BaseModel):
    action: str
    reason: Optional[str] = None

pagos_db = {
    "PAY-a1b2c3d4-e5f6-7890-1234-56789abcdef0": {
        "paymentId":      "PAY-a1b2c3d4-e5f6-7890-1234-56789abcdef0",
        "orderId":        "ORD-20260611-001",
        "userId":         "e9d8c7b6-a543-2109-8765-fedcba098765",
        "amount":         59990,
        "currency":       "CLP",
        "method":         "MERCADOPAGO",
        "status":         "PENDING",
        "idempotencyKey": "11111111-2222-4333-8444-555555555555",
        "correlationId":  "99999999-8888-4777-9666-555555555555",
        "failureReason":  None,
        "createdAt":      "2026-06-15T20:00:00Z",
        "updatedAt":      "2026-06-15T20:00:00Z"
    }
}

@router.patch("/{paymentId}/confirm")
def confirm_payment(paymentId: str, body: ConfirmPaymentRequest):

    pago = pagos_db.get(paymentId)

    if pago is None:
        raise HTTPException(status_code=404, detail={
            "code":    "PAYMENT_NOT_FOUND",
            "message": "El pago solicitado no existe."
        })

    if body.action not in ["APPROVE", "REJECT"]:
        raise HTTPException(status_code=400, detail={
            "code":    "INVALID_ACTION",
            "message": "La acción debe ser APPROVE o REJECT."
        })

    if pago["status"] in ["APPROVED", "REJECTED"]:
        return {
            "paymentId":  pago["paymentId"],
            "status":     pago["status"],
            "idempotent": True,
            "message":    "Pago ya se encuentra en estado final. No se reprocesó."
        }

    if body.action == "APPROVE":
        pago["status"]        = "APPROVED"
        pago["failureReason"] = None
        pago["updatedAt"]     = "2026-06-15T20:00:05Z"

    elif body.action == "REJECT":
        pago["status"]        = "REJECTED"
        pago["failureReason"] = body.reason or "Fondos insuficientes."
        pago["updatedAt"]     = "2026-06-15T20:00:05Z"

    return {
        "paymentId":      pago["paymentId"],
        "orderId":        pago["orderId"],
        "userId":         pago["userId"],
        "amount":         pago["amount"],
        "currency":       pago["currency"],
        "method":         pago["method"],
        "status":         pago["status"],
        "idempotencyKey": pago["idempotencyKey"],
        "correlationId":  pago["correlationId"],
        "failureReason":  pago["failureReason"],
        "createdAt":      pago["createdAt"],
        "updatedAt":      pago["updatedAt"]
    }
