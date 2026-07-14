import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from app.database.supabase_client import supabase
from app.schemas.payments import (
    ConfirmPaymentRequest,
    CreatePaymentRequest,
    ErrorResponse,
    PaginationResponse,
    PaymentIdempotentResponse,
    PaymentListResponse,
    PaymentResponse,
)
from app.services.mercadopago_service import mercadopago_service
from app.services.payment_event_publisher import (
    payment_event_publisher,
)
from app.services.payment_notification_service import (
    payment_notification_service,
)
from app.services.payment_service import payment_service

logger = logging.getLogger(__name__)

# Creamos el router. El prefix nos ahorra escribir /v1/payments en cada ruta.
router = APIRouter(prefix="/v1/payments", tags=["Payments"])

def _publish_payment_event_safely(
    payment: dict[str, Any],
    source: str,
) -> Optional[dict[str, str]]:
    """
    Intenta publicar el evento sin romper el flujo principal del pago.

    Si Pub/Sub falla, el pago permanece creado o actualizado y
    el error queda registrado en los logs de Render.
    """

    try:
        result = payment_event_publisher.publish_payment_status(
            payment=payment,
            source=source,
        )

        logger.info(
            "Evento publicado correctamente: %s",
            result,
        )

        return result

    except Exception:
        logger.exception(
            "No se pudo publicar el evento del pago %s.",
            payment.get("payment_id"),
        )

        return None

def _unauthorized_response(correlation_id: Optional[str]) -> JSONResponse:
    """Respuesta estándar para requests sin token de autorización."""
    body = ErrorResponse(
        code="UNAUTHORIZED_ACCESS",
        message="Token JWT ausente, inválido o expirado.",
        correlation_id=correlation_id,
    )
    return JSONResponse(status_code=401, content=body.model_dump(by_alias=True))

def _create_payment_notification_safely(
    payment: dict[str, Any],
    source: str,
) -> Optional[dict[str, Any]]:
    """
    Crea la notificación sin romper el pago si Supabase
    presenta un error temporal.
    """

    try:
        result = payment_notification_service.create_from_payment(
            payment=payment,
            source=source,
        )

        logger.info(
            "Notificación de pago procesada correctamente: %s",
            result,
        )

        return result

    except Exception:
        logger.exception(
            "No se pudo crear la notificación del pago %s.",
            payment.get("payment_id"),
        )

        return None

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
    Crea un pago nuevo en Supabase y una preferencia de pago en Mercado Pago.
    Verifica idempotencia antes de crear.
    Responsabilidad: Compañero 1.
    """
    try:
        payment = payment_service.create_payment(
            request=request,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
        )

        if payment.get("_idempotent"):
            return JSONResponse(
                status_code=200,
                content={
                    "paymentId": payment["payment_id"],
                    "status": payment["status"],
                    "idempotent": True,
                    "checkoutUrl": payment.get("checkout_url"),
                    "message": "Pago ya iniciado con este idempotencyKey.",
                },
            )

        _publish_payment_event_safely(
            payment=payment,
            source="payment-created",
        )

        _create_payment_notification_safely(
            payment=payment,
            source="payment-created",
        )

        return PaymentResponse.model_validate(payment)

    except ValueError as exc:
        code = str(exc)

        messages = {
            "INVALID_CURRENCY": "Solo se acepta CLP en la versión actual del servicio.",
            "INVALID_PAYMENT_METHOD": "En la versión actual solo se acepta MERCADOPAGO.",
        }

        raise HTTPException(
            status_code=400,
            detail={
                "code": code,
                "message": messages.get(code, "Datos inválidos para crear el pago."),
            },
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "PAYMENT_CREATION_ERROR",
                "message": f"Error al crear el pago: {str(exc)}",
            },
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

    if not update_result.data:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "PAYMENT_UPDATE_ERROR",
                "message": "No se pudo actualizar el pago.",
            },
        )

    updated_payment = update_result.data[0]

    _publish_payment_event_safely(
        payment=updated_payment,
        source="manual-confirmation",
    )

    _create_payment_notification_safely(
        payment=updated_payment,
        source="manual-confirmation",
    )

    return PaymentResponse.model_validate(updated_payment)

def _map_mercadopago_status(provider_status: Optional[str]) -> str:
    if provider_status == "approved":
        return "APPROVED"

    if provider_status in ["rejected", "cancelled"]:
        return "REJECTED"

    return "PENDING"

@router.post("/webhooks/mercadopago")
async def receive_mercadopago_webhook(request: Request):
    """
    Recibe notificaciones de Mercado Pago.

    Soporta:
    - Webhook real con body JSON.
    - Simulación de Mercado Pago con query params tipo data.id=123456&type=payment.
    """

    try:
        payload = await request.json()
    except Exception:
        payload = {}

    query_params = request.query_params

    data = payload.get("data") or {}

    provider_payment_id = (
        data.get("id")
        or query_params.get("data.id")
        or query_params.get("id")
    )

    event_type = payload.get("type") or query_params.get("type")

    if not provider_payment_id:
        return {
            "received": True,
            "processed": False,
            "message": "Webhook recibido, pero no contenía data.id.",
        }

    if str(provider_payment_id) == "123456":
        return {
            "received": True,
            "processed": False,
            "test": True,
            "eventType": event_type,
            "providerPaymentId": str(provider_payment_id),
            "message": "Notificación de prueba recibida correctamente. No se actualizó ningún pago real.",
        }

    try:
        mp_payment = mercadopago_service.get_payment(str(provider_payment_id))

        payment_id = mp_payment.get("external_reference")
        provider_status = mp_payment.get("status")
        internal_status = _map_mercadopago_status(provider_status)

        if not payment_id:
            return {
                "received": True,
                "processed": False,
                "providerPaymentId": str(provider_payment_id),
                "message": "Mercado Pago no retornó external_reference para asociar el pago.",
            }

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        update_payload = {
            "provider_payment_id": str(provider_payment_id),
            "provider_status": provider_status,
            "status": internal_status,
            "updated_at": now,
        }

        if internal_status == "APPROVED":
            update_payload["confirmed_at"] = now
            update_payload["failure_reason"] = None

        if internal_status == "REJECTED":
            update_payload["rejected_at"] = now
            update_payload["failure_reason"] = (
                mp_payment.get("status_detail")
                or "Pago rechazado por Mercado Pago."
            )

        update_result = (
            supabase.table("payments")
            .update(update_payload)
            .eq("payment_id", payment_id)
            .execute()
        )

        if not update_result.data:
            return {
                "received": True,
                "processed": False,
                "providerPaymentId": str(provider_payment_id),
                "paymentId": payment_id,
                "message": (
                    "Webhook recibido, pero no se encontró "
                    "el pago en Supabase."
                ),
            }

        updated_payment = update_result.data[0]

        event_result = _publish_payment_event_safely(
            payment=updated_payment,
            source="mercadopago-webhook",
        )

        notification_result = _create_payment_notification_safely(
            payment=updated_payment,
            source="mercadopago-webhook",
        )

        return {
            "received": True,
            "processed": True,
            "paymentId": payment_id,
            "providerPaymentId": str(provider_payment_id),
            "providerStatus": provider_status,
            "status": internal_status,
            "eventPublished": event_result is not None,
            "eventId": (
                event_result.get("eventId")
                if event_result
                else None
            ),
            "eventMessageId": (
                event_result.get("messageId")
                if event_result
                else None
            ),
            "notificationCreated": (
                notification_result is not None
            ),
            "notificationId": (
                notification_result.get("notificationId")
                if notification_result
                else None
            ),
            "message": "Webhook procesado correctamente.",
        }

    except Exception as exc:
        error_text = str(exc)

        if "404" in error_text or "not_found" in error_text.lower() or "not found" in error_text.lower():
            return {
                "received": True,
                "processed": False,
                "providerPaymentId": str(provider_payment_id),
                "message": "Webhook recibido, pero el pago no existe en Mercado Pago. Probablemente es una simulación.",
                "error": error_text,
            }

        raise HTTPException(
            status_code=500,
            detail={
                "code": "MERCADOPAGO_WEBHOOK_ERROR",
                "message": f"No se pudo procesar el webhook de Mercado Pago: {error_text}",
            },
        )