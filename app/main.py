"""
Punto de entrada del servicio G8 — Pago Simulado y Notificaciones.

Por ahora expone un endpoint de salud (/health) para que Render tenga
algo real que desplegar mientras el equipo construye los endpoints
definidos en docs/G8_Contratos.yaml.
"""

from fastapi import FastAPI, Header, HTTPException, Body
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone

# Inicialización de la aplicación FastAPI
app = FastAPI(
    title="Grupo 8 - Payment & Notifications API",
    version="1.1.0",
    description="Mock API para la fase E2 del Mini-Marketplace Cloud."
)

# Modelos Base (Usamos 'alias' para recibir y enviar camelCase pero programar en snake_case)
class CreatePaymentRequest(BaseModel):
    order_id: str = Field(alias="orderId", example="ORD-20260611-001")
    user_id: str = Field(alias="userId", example="e9d8c7b6-a543-2109-8765-fedcba098765")
    amount: int = Field(example=59990)
    currency: str = Field(example="CLP")
    method: str = Field(example="MERCADOPAGO")

class PaymentResponse(BaseModel):
    payment_id: str = Field(alias="paymentId")
    order_id: str = Field(alias="orderId")
    user_id: str = Field(alias="userId")
    amount: int
    currency: str
    method: str
    status: str
    idempotency_key: str = Field(alias="idempotencyKey")
    correlation_id: Optional[str] = Field(None, alias="correlationId")
    failure_reason: Optional[str] = Field(None, alias="failureReason")
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")

    class Config:
        populate_by_name = True # Permite instanciar usando los nombres en snake_case

# Endpoint Asignado: Iniciar Pago (Mock)
@app.post("/v1/payments", response_model=PaymentResponse, status_code=201, tags=["Payments"])
def create_payment(
    request: CreatePaymentRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id"),
    authorization: Optional[str] = Header(None)
):
    """
    Mock del endpoint para iniciar un pago.
    Valida la existencia del Idempotency-Key y retorna un pago simulado aprobado.
    """
    
    # Validamos que el header obligatorio venga en la petición
    if not idempotency_key:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "MISSING_IDEMPOTENCY_KEY",
                "message": "El header Idempotency-Key es obligatorio para esta operación."
            }
        )

    # Generamos timestamps simulados
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Retornamos el Mock exacto que pide el YAML
    return PaymentResponse(
        payment_id="PAY-a1b2c3d4-e5f6-7890-1234-56789abcdef0",
        order_id=request.order_id,
        user_id=request.user_id,
        amount=request.amount,
        currency=request.currency,
        method=request.method,
        status="APPROVED", # Estado simulado fijo para el E2
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        failure_reason=None,
        created_at=now,
        updated_at=now
    )
