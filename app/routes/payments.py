import math
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional, List
from datetime import datetime, timezone
from app.schemas.payments import CreatePaymentRequest, PaymentResponse
from pydantic import BaseModel

# Importamos los modelos desde nuestra nueva carpeta schemas
from app.schemas.payments import (
    CreatePaymentRequest,
    PaymentResponse,
    PaymentListResponse,
    PaginationResponse,
    ErrorResponse,
)
from app.services.payments_mock import MOCK_PAYMENTS

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

def _unauthorized_response(correlation_id: Optional[str]) -> JSONResponse:
    body = ErrorResponse(
        code="UNAUTHORIZED_ACCESS",
        message="Token JWT ausente, inválido o expirado.",
        correlation_id=correlation_id,
    )
    return JSONResponse(status_code=401, content=body.model_dump(by_alias=True))

@router.get("/{payment_id}", response_model=PaymentResponse)
def get_payment_by_id(
    payment_id: str,
    authorization: Optional[str] = Header(
        None, 
        description="Para probar el mock, escribe cualquier cosa aquí, ej: Bearer 123"
    ),
    correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id"),
):
    """
    Mock del endpoint para consultar un pago por su ID.
    """
    if not authorization:
        return _unauthorized_response(correlation_id)

    record = next((p for p in MOCK_PAYMENTS if p["payment_id"] == payment_id), None)

    if record is None:
        body = ErrorResponse(
            code="PAYMENT_NOT_FOUND",
            message="El pago solicitado no existe.",
            correlation_id=correlation_id,
        )
        return JSONResponse(status_code=404, content=body.model_dump(by_alias=True))

    return PaymentResponse(**record)

@router.get("", response_model=PaymentListResponse)
def list_payments_by_order(
    order_id: Optional[str] = Query(None, alias="orderId"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    authorization: Optional[str] = Header(
        None,
        description="Para probar el mock, escribe cualquier cosa aquí, ej: Bearer 123"
    ),
    correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id"),
):
    """
    Mock del endpoint para listar los pagos de un pedido, con paginación.
    """
    if not authorization:
        return _unauthorized_response(correlation_id)

    if not order_id:
        body = ErrorResponse(
            code="MISSING_ORDER_ID",
            message="El parámetro orderId es obligatorio.",
            correlation_id=correlation_id,
        )
        return JSONResponse(status_code=400, content=body.model_dump(by_alias=True))

    filtered = [p for p in MOCK_PAYMENTS if p["order_id"] == order_id]

    if not filtered:
        body = ErrorResponse(
            code="PAYMENT_NOT_FOUND",
            message="El pago solicitado no existe.",
            correlation_id=correlation_id,
        )
        return JSONResponse(status_code=404, content=body.model_dump(by_alias=True))

    total = len(filtered)
    total_pages = math.ceil(total / page_size) if total > 0 else 1
    start = (page - 1) * page_size
    end = start + page_size
    items = [PaymentResponse(**p) for p in filtered[start:end]]

    pagination = PaginationResponse(
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
    )

    return PaymentListResponse(data=items, pagination=pagination)
