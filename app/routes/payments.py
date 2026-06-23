import math
from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Optional, List
from datetime import datetime, timezone
from pydantic import BaseModel

# Importamos los modelos desde nuestra nueva carpeta schemas
from app.schemas.payments import (
    CreatePaymentRequest,
    PaymentResponse,
    PaymentListResponse,
    PaginationResponse,
    ErrorResponse,
    ConfirmPaymentRequest,
    PaymentIdempotentResponse
)
from app.services.payments_mock import MOCK_PAYMENTS

# Creamos el router. El prefix nos ahorra escribir /v1/payments en cada ruta.
router = APIRouter(prefix="/v1/payments", tags=["Payments"])

@router.post("", response_model=PaymentResponse, status_code=201, responses={
    200: {"model": PaymentIdempotentResponse, "description": "Respuesta idempotente."},
    400: {"model": ErrorResponse, "description": "Datos inválidos o Idempotency-Key ausente."},
    401: {"model": ErrorResponse, "description": "No autenticado."},
    422: {"model": ErrorResponse, "description": "Pago no procesable."},
})
def create_payment(
    request: CreatePaymentRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key", example="11111111-2222-4333-8444-555555555555"),
    correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id", example="99999999-8888-4777-9666-555555555555"),
    authorization: Optional[str] = Header(None)
):
    """
    Mock del endpoint para iniciar un pago.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    new_payment = {
        "payment_id": "PAY-a1b2c3d4-e5f6-7890-1234-56789abcdef0",
        "order_id": request.order_id,
        "user_id": request.user_id,
        "amount": request.amount,
        "currency": request.currency,
        "method": request.method,
        "status": "APPROVED",
        "idempotency_key": idempotency_key,
        "correlation_id": correlation_id,
        "failure_reason": None,
        "created_at": now,
        "updated_at": now
    }
    
    MOCK_PAYMENTS.append(new_payment)
    
    return PaymentResponse.model_validate(new_payment)

@router.patch("/{payment_id}/confirm", responses={
    200: {"model": PaymentResponse, "description": "Pago confirmado o idempotente."},
    400: {"model": ErrorResponse, "description": "Acción inválida o estado incorrecto."},
    401: {"model": ErrorResponse, "description": "No autenticado."},
    404: {"model": ErrorResponse, "description": "Pago no encontrado."},
})
def confirm_payment(
    payment_id: str, 
    body: ConfirmPaymentRequest,
    authorization: Optional[str] = Header(
        None, 
        description="Para probar el mock, escribe cualquier cosa aquí, ej: Bearer 123"
    ),
    correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id"),
):
    """
    Mock del endpoint para confirmar o rechazar un pago.
    Garantiza idempotencia si el pago ya está en estado final.
    """
    if not authorization:
        return _unauthorized_response(correlation_id)

    # Buscamos el pago en la lista global MOCK_PAYMENTS
    pago = next((p for p in MOCK_PAYMENTS if p["payment_id"] == payment_id), None)

    if pago is None:
        raise HTTPException(status_code=404, detail={
            "code": "PAYMENT_NOT_FOUND",
            "message": "El pago solicitado no existe."
        })

    if body.action not in ["APPROVE", "REJECT"]:
        raise HTTPException(status_code=400, detail={
            "code": "INVALID_ACTION",
            "message": "La acción debe ser APPROVE o REJECT."
        })

    # Lógica de idempotencia intacta
    if pago["status"] in ["APPROVED", "REJECTED"]:
        return JSONResponse(status_code=200, content={
            "paymentId": pago["payment_id"],
            "status": pago["status"],
            "idempotent": True,
            "message": "Pago ya se encuentra en estado final. No se reprocesó."
        })

    # Actualizamos el pago en memoria
    if body.action == "APPROVE":
        pago["status"] = "APPROVED"
        pago["failure_reason"] = None
    elif body.action == "REJECT":
        pago["status"] = "REJECTED"
        pago["failure_reason"] = body.reason or "Fondos insuficientes."

    pago["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return PaymentResponse.model_validate(pago)

def _unauthorized_response(correlation_id: Optional[str]) -> JSONResponse:
    body = ErrorResponse(
        code="UNAUTHORIZED_ACCESS",
        message="Token JWT ausente, inválido o expirado.",
        correlation_id=correlation_id,
    )
    return JSONResponse(status_code=401, content=body.model_dump(by_alias=True))

@router.get("/{payment_id}", response_model=PaymentResponse, responses={
    401: {"model": ErrorResponse, "description": "No autenticado."},
    403: {"model": ErrorResponse, "description": "Sin permisos."},
    404: {"model": ErrorResponse, "description": "Pago no encontrado."},
})
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

    return PaymentResponse.model_validate(record)

@router.get("", response_model=PaymentListResponse, responses={
    400: {"model": ErrorResponse, "description": "orderId ausente o inválido."},
    401: {"model": ErrorResponse, "description": "No autenticado."},
    404: {"model": ErrorResponse, "description": "Pago no encontrado."},
})
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
    items = [PaymentResponse.model_validate(p) for p in filtered[start:end]]

    pagination = PaginationResponse(
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
    )

    return PaymentListResponse(data=items, pagination=pagination)