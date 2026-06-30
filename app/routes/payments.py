import math
from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Optional
from datetime import datetime, timezone
from app.database.supabase_client import supabase
from app.services.payment_service import payment_service

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

# Importamos el servicio de pagos (lo implementó Compañero 1)
from app.services.payment_service import payment_service

# Importamos la conexión a Supabase
from app.database.supabase_client import supabase

# Creamos el router. El prefix nos ahorra escribir /v1/payments en cada ruta.
router = APIRouter(prefix="/v1/payments", tags=["Payments"])


def _unauthorized_response(correlation_id: Optional[str]) -> JSONResponse:
    """Respuesta estándar para requests sin token de autorización."""
    body = ErrorResponse(
        code="UNAUTHORIZED_ACCESS",
        message="Token JWT ausente, inválido o expirado.",
        correlation_id=correlation_id,
    )
    return JSONResponse(status_code=401, content=body.model_dump(by_alias=True))


# ─────────────────────────────────────────────
# POST /v1/payments — Compañero 1
# Crea un pago nuevo en Supabase.
# ─────────────────────────────────────────────
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
    Crea un pago nuevo en Supabase.
    Verifica idempotencia antes de crear.
    Responsabilidad: Compañero 1.
    """
    try:
        # Verificar idempotencia: si ya existe un pago con ese idempotency_key, no crear otro
        existing_payment = (
            supabase.table("payments")
            .select("*")
            .eq("idempotency_key", idempotency_key)
            .execute()
        )

        if existing_payment.data and len(existing_payment.data) > 0:
            existing = existing_payment.data[0]
            return JSONResponse(
                status_code=200,
                content={
                    "paymentId": existing["payment_id"],
                    "status": existing["status"],
                    "idempotent": True,
                    "message": "Pago ya existe. No se creó uno nuevo."
                }
            )

        # Crear nuevo pago usando el servicio
        new_payment = payment_service.create_payment(
            request=request,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id
        )

        return PaymentResponse.model_validate(new_payment)

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "PAYMENT_CREATION_ERROR",
                "message": f"Error al crear el pago: {str(e)}"
            }
        )


# ═════════════════════════════════════════════
# COMPAÑERO 2 — Pagos parte 2
# Consulta, listado y confirmación de pagos
# conectados a Supabase.
# ═════════════════════════════════════════════

# ─────────────────────────────────────────────
# GET /v1/payments/{payment_id}
# Busca un pago específico por su ID en Supabase.
# ─────────────────────────────────────────────
@router.get("/{payment_id}", response_model=PaymentResponse, responses={
    401: {"model": ErrorResponse, "description": "No autenticado."},
    403: {"model": ErrorResponse, "description": "Sin permisos."},
    404: {"model": ErrorResponse, "description": "Pago no encontrado."},
})
def get_payment_by_id(
    payment_id: str,
    authorization: Optional[str] = Header(
        None,
        alias="Authorization",
        description="Para probar el mock, escribe cualquier cosa aquí, ej: Bearer 123"
    ),
    correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id"),
):
    """
    Consulta un pago por su ID, persistido en Supabase.
    Reemplaza la búsqueda en MOCK_PAYMENTS por una consulta real.
    """
    if not authorization:
        return _unauthorized_response(correlation_id)

    # Buscamos el pago en Supabase filtrando por payment_id
    result = (
        supabase.table("payments")
        .select("*")
        .eq("payment_id", payment_id)
        .execute()
    )

    # Si no se encontró ningún registro, devolvemos 404
    if not result.data:
        body = ErrorResponse(
            code="PAYMENT_NOT_FOUND",
            message="El pago solicitado no existe.",
            correlation_id=correlation_id,
        )
        return JSONResponse(status_code=404, content=body.model_dump(by_alias=True))

    # Devolvemos el primer (y único) resultado encontrado
    return PaymentResponse.model_validate(result.data[0])


# ─────────────────────────────────────────────
# GET /v1/payments?orderId=...
# Lista todos los pagos de un pedido con paginación real.
# ─────────────────────────────────────────────
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
        alias="Authorization",
        description="Para probar el mock, escribe cualquier cosa aquí, ej: Bearer 123"
    ),
    correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id"),
):
    """
    Lista los pagos de un pedido con paginación real desde Supabase.
    Reemplaza el filtrado en memoria por consultas con LIMIT y OFFSET.
    """
    if not authorization:
        return _unauthorized_response(correlation_id)

    # El parámetro orderId es obligatorio
    if not order_id:
        body = ErrorResponse(
            code="MISSING_ORDER_ID",
            message="El parámetro orderId es obligatorio.",
            correlation_id=correlation_id,
        )
        return JSONResponse(status_code=400, content=body.model_dump(by_alias=True))

    # Primero contamos el total de registros para calcular la paginación
    count_result = (
        supabase.table("payments")
        .select("payment_id", count="exact")
        .eq("order_id", order_id)
        .execute()
    )
    total = count_result.count or 0

    # Si no hay pagos para ese orderId, devolvemos 404
    if total == 0:
        body = ErrorResponse(
            code="PAYMENT_NOT_FOUND",
            message="El pago solicitado no existe.",
            correlation_id=correlation_id,
        )
        return JSONResponse(status_code=404, content=body.model_dump(by_alias=True))

    # Calculamos el rango de filas según la página solicitada (equivale a LIMIT/OFFSET)
    start = (page - 1) * page_size
    end = start + page_size - 1

    # Traemos solo los registros de esa página
    data_result = (
        supabase.table("payments")
        .select("*")
        .eq("order_id", order_id)
        .range(start, end)
        .execute()
    )

    items = [PaymentResponse.model_validate(p) for p in data_result.data]
    total_pages = math.ceil(total / page_size) if total > 0 else 1

    pagination = PaginationResponse(
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
    )

    return PaymentListResponse(data=items, pagination=pagination)


# ─────────────────────────────────────────────
# PATCH /v1/payments/{payment_id}/confirm
# Confirma o rechaza un pago, persistido en Supabase.
# Mantiene la idempotencia definida en el E1.
# ─────────────────────────────────────────────
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
        alias="Authorization",
        description="Para probar el mock, escribe cualquier cosa aquí, ej: Bearer 123"
    ),
    correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id"),
):
    """
    Confirma o rechaza un pago, ahora persistido en Supabase.
    Mantiene la misma lógica de idempotencia del E2:
    si el pago ya está en estado final, no se reprocesa.
    """
    if not authorization:
        return _unauthorized_response(correlation_id)

    # Buscamos el pago en Supabase
    result = (
        supabase.table("payments")
        .select("*")
        .eq("payment_id", payment_id)
        .execute()
    )

    # Si no existe el pago, devolvemos 404
    if not result.data:
        raise HTTPException(status_code=404, detail={
            "code": "PAYMENT_NOT_FOUND",
            "message": "El pago solicitado no existe."
        })

    pago = result.data[0]

    # Validamos que la acción sea válida
    if body.action not in ["APPROVE", "REJECT"]:
        raise HTTPException(status_code=400, detail={
            "code": "INVALID_ACTION",
            "message": "La acción debe ser APPROVE o REJECT."
        })

    # IDEMPOTENCIA: si el pago ya está en estado final, no lo reprocesamos
    if pago["status"] in ["APPROVED", "REJECTED"]:
        return JSONResponse(status_code=200, content={
            "paymentId": pago["payment_id"],
            "status": pago["status"],
            "idempotent": True,
            "message": "Pago ya se encuentra en estado final. No se reprocesó."
        })

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Preparamos los campos a actualizar según la acción recibida
    if body.action == "APPROVE":
        update_payload = {
            "status": "APPROVED",
            "failure_reason": None,
            "confirmed_at": now,
            "updated_at": now,
        }
    else:
        update_payload = {
            "status": "REJECTED",
            "failure_reason": body.reason or "Fondos insuficientes.",
            "rejected_at": now,
            "updated_at": now,
        }

    # Hacemos el UPDATE real en Supabase
    update_result = (
        supabase.table("payments")
        .update(update_payload)
        .eq("payment_id", payment_id)
        .execute()
    )

    # Devolvemos el pago con el estado actualizado
    return PaymentResponse.model_validate(update_result.data[0])
