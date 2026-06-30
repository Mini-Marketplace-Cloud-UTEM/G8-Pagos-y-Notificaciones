import math
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Header, Query, Response
from fastapi.responses import JSONResponse

from app.db import get_supabase
from app.schemas.notifications import (
    TestNotificationRequest,
    Notification,
    Pagination,
    NotificationListResponse,
    NotificationIdempotentResponse,
)

# El prefix nos ahorra escribir /v1/notifications en cada ruta.
router = APIRouter(prefix="/v1/notifications", tags=["Notifications"])

# Nombre de la tabla en Supabase.
TABLE = "notifications"

# Tipos de evento soportados (según el contrato G8_Contratos.yaml).
SUPPORTED_EVENT_TYPES = [
    "ORDER_CREATED",
    "PAYMENT_APPROVED",
    "PAYMENT_REJECTED",
    "PAYMENT_PENDING",
    "SHIPMENT_DELIVERED",
    "STOCK_REJECTED",
]

# Plantillas de título y cuerpo por tipo de evento.
# El {orderId} se reemplaza con el dato que venga en el payload del evento.
NOTIFICATION_TEMPLATES = {
    "ORDER_CREATED": ("Pedido creado", "Tu pedido {orderId} fue creado correctamente."),
    "PAYMENT_APPROVED": ("¡Tu pago fue aprobado!", "El pago de tu pedido {orderId} fue procesado exitosamente."),
    "PAYMENT_REJECTED": ("Tu pago fue rechazado", "El pago de tu pedido {orderId} no pudo ser procesado."),
    "PAYMENT_PENDING": ("Tu pago está pendiente", "El pago de tu pedido {orderId} está siendo procesado."),
    "SHIPMENT_DELIVERED": ("¡Tu pedido fue entregado!", "Tu pedido {orderId} fue entregado correctamente."),
    "STOCK_REJECTED": ("Problema con el stock", "No hay stock suficiente para tu pedido {orderId}."),
}


def _error(status: int, code: str, message: str, details=None) -> JSONResponse:
    """Construye una respuesta de error con el formato estándar del contrato."""
    body = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    return JSONResponse(status_code=status, content=body)


def _is_duplicate_error(exc: Exception) -> bool:
    """True si la excepción corresponde a una violación de UNIQUE (event_id)."""
    text = str(getattr(exc, "message", "") or "") + str(exc)
    return "23505" in text or "duplicate key" in text.lower()


@router.get(
    "",
    response_model=NotificationListResponse,
    response_model_exclude_none=True,
)
def list_notifications(
    user_id: Optional[str] = Query(
        None, alias="userId", example="e9d8c7b6-a543-2109-8765-fedcba098765"
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id"),
    authorization: Optional[str] = Header(None),
):
    """
    Lista las notificaciones de un usuario desde Supabase, con paginación real.
    Si el usuario no tiene notificaciones, devuelve 404 USER_NOT_FOUND (según contrato).
    """
    if not user_id:
        return _error(400, "MISSING_USER_ID", "El parámetro userId es obligatorio.")

    start = (page - 1) * page_size
    end = start + page_size - 1

    try:
        resp = (
            get_supabase()
            .table(TABLE)
            .select("*", count="exact")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .range(start, end)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001 - error de infraestructura
        return _error(503, "DATABASE_ERROR", f"No se pudo consultar la base de datos: {exc}")

    rows = resp.data or []
    total = resp.count or 0

    # 404 — el contrato define USER_NOT_FOUND cuando el usuario no tiene notificaciones.
    if total == 0:
        return _error(
            404,
            "USER_NOT_FOUND",
            "No se encontraron notificaciones para el userId indicado.",
        )

    total_pages = math.ceil(total / page_size)

    notifications = [Notification(**row) for row in rows]
    pagination = Pagination(
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
    )
    return NotificationListResponse(data=notifications, pagination=pagination)


@router.post(
    "/test",
    status_code=201,
    responses={
        201: {"model": Notification, "description": "Notificación generada correctamente."},
        200: {
            "model": NotificationIdempotentResponse,
            "description": "Evento ya procesado anteriormente (respuesta idempotente).",
        },
    },
)
def test_notification(
    event: TestNotificationRequest,
    response: Response,
    correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id"),
    authorization: Optional[str] = Header(None),
):
    """
    Inyecta un evento de prueba y genera una notificación persistida en Supabase.
    Idempotencia real: la columna event_id tiene constraint UNIQUE, por lo que
    el mismo eventId nunca crea una notificación duplicada (responde 200).
    """
    # 400 — eventId es la clave de idempotencia, es obligatorio.
    if not event.event_id:
        return _error(400, "MISSING_EVENT_ID", "El campo eventId es obligatorio.")

    # 422 — el tipo de evento no genera notificaciones en este servicio.
    if event.event_type not in SUPPORTED_EVENT_TYPES:
        return _error(
            422,
            "UNSUPPORTED_EVENT_TYPE",
            "El eventType recibido no genera notificaciones en este servicio.",
            details=[{
                "field": "eventType",
                "message": (
                    f"Valor recibido '{event.event_type}' no está soportado. "
                    f"Valores válidos: {', '.join(SUPPORTED_EVENT_TYPES)}."
                ),
            }],
        )

    sb = get_supabase()

    # Idempotencia (1ª comprobación): ¿ya existe una notificación con este eventId?
    try:
        existing = (
            sb.table(TABLE).select("notification_id").eq("event_id", event.event_id).limit(1).execute()
        )
    except Exception as exc:  # noqa: BLE001
        return _error(503, "DATABASE_ERROR", f"No se pudo consultar la base de datos: {exc}")

    if existing.data:
        response.status_code = 200
        return NotificationIdempotentResponse(
            notification_id=existing.data[0]["notification_id"],
            event_id=event.event_id,
            idempotent=True,
            message="Evento ya procesado. No se generó notificación duplicada.",
        )

    # Construimos la notificación a partir del evento.
    payload = event.payload or {}
    # Grupo 6 (Despacho) envía el payload en snake_case (order_id); probamos ambas.
    order_id = payload.get("orderId") or payload.get("order_id") or "tu pedido"
    user_id = payload.get("userId") or payload.get("user_id") or "00000000-0000-0000-0000-000000000000"
    title, body_template = NOTIFICATION_TEMPLATES[event.event_type]

    new_row = {
        "notification_id": "NTF-" + str(uuid.uuid4()),
        "user_id": user_id,
        "event_id": event.event_id,
        "event_type": event.event_type,
        "title": title,
        "body": body_template.format(orderId=order_id),
        "channel": "DASHBOARD",
        "status": "DELIVERED",
        "payload": payload,
    }

    # Insertamos. Si entre la comprobación y el insert llegó el mismo eventId
    # (condición de carrera), el UNIQUE de la BD lo bloquea y respondemos idempotente.
    try:
        result = sb.table(TABLE).insert(new_row).execute()
    except Exception as exc:  # noqa: BLE001
        if _is_duplicate_error(exc):
            again = (
                sb.table(TABLE).select("notification_id").eq("event_id", event.event_id).limit(1).execute()
            )
            notification_id = again.data[0]["notification_id"] if again.data else new_row["notification_id"]
            response.status_code = 200
            return NotificationIdempotentResponse(
                notification_id=notification_id,
                event_id=event.event_id,
                idempotent=True,
                message="Evento ya procesado. No se generó notificación duplicada.",
            )
        return _error(503, "DATABASE_ERROR", f"No se pudo guardar la notificación: {exc}")

    created = result.data[0] if result.data else new_row
    return Notification(**created)
