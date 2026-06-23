from fastapi import APIRouter, Header, Query, Response, HTTPException
from typing import Optional
from datetime import datetime, timezone

# Importamos los modelos desde la carpeta schemas
from app.schemas.notifications import (
    TestNotificationRequest,
    Notification,
    Pagination,
    NotificationListResponse,
    NotificationIdempotentResponse,
)

# El prefix nos ahorra escribir /v1/notifications en cada ruta.
router = APIRouter(prefix="/v1/notifications", tags=["Notifications"])

# Tipos de evento soportados (según el contrato G8_Contratos.yaml).
SUPPORTED_EVENT_TYPES = [
    "ORDER_CREATED",
    "PAYMENT_APPROVED",
    "PAYMENT_REJECTED",
    "PAYMENT_PENDING",
    "SHIPMENT_DELIVERED",
    "STOCK_REJECTED",
]

# Plantillas mock de título y cuerpo por tipo de evento.
# El {orderId} se reemplaza con el dato que venga en el payload del evento.
NOTIFICATION_TEMPLATES = {
    "ORDER_CREATED": ("Pedido creado", "Tu pedido {orderId} fue creado correctamente."),
    "PAYMENT_APPROVED": ("¡Tu pago fue aprobado!", "El pago de tu pedido {orderId} fue procesado exitosamente."),
    "PAYMENT_REJECTED": ("Tu pago fue rechazado", "El pago de tu pedido {orderId} no pudo ser procesado."),
    "PAYMENT_PENDING": ("Tu pago está pendiente", "El pago de tu pedido {orderId} está siendo procesado."),
    "SHIPMENT_DELIVERED": ("¡Tu pedido fue entregado!", "Tu pedido {orderId} fue entregado correctamente."),
    "STOCK_REJECTED": ("Problema con el stock", "No hay stock suficiente para tu pedido {orderId}."),
}

# Mock en memoria SOLO para demostrar idempotencia en la fase E2.
# Mapea eventId -> notificationId ya generado. En E3 esto lo reemplaza
# el constraint UNIQUE sobre la columna eventId en la base de datos.
_processed_events: dict = {}


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
    Mock del listado de notificaciones de un usuario, con paginación.
    """
    if not user_id:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "MISSING_USER_ID",
                "message": "El parámetro userId es obligatorio.",
            },
        )

    notification = Notification(
        notification_id="NTF-b2c3d4e5-f6a7-8901-2345-67890abcdef1",
        user_id=user_id,
        event_id="evt-550e8400-e29b-41d4-a716-446655440001",
        event_type="PAYMENT_APPROVED",
        title="¡Tu pago fue aprobado!",
        body="El pago de tu pedido ORD-20260611-001 fue procesado exitosamente.",
        channel="DASHBOARD",
        status="DELIVERED",
        created_at="2026-06-15T20:00:02Z",
    )

    return NotificationListResponse(
        data=[notification],
        pagination=Pagination(
            page=page,
            page_size=page_size,
            total=1,
            total_pages=1,
            has_next=False,
            has_prev=False,
        ),
    )


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
    Mock del inyector de eventos de prueba. Genera una notificación a partir
    de un evento en el formato estándar del curso y simula idempotencia:
    si el mismo eventId llega dos veces, NO se crea una notificación duplicada.
    """
    # 400 — eventId es la clave de idempotencia, es obligatorio.
    if not event.event_id:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "MISSING_EVENT_ID",
                "message": "El campo eventId es obligatorio.",
            },
        )

    # 422 — el tipo de evento no genera notificaciones en este servicio.
    if event.event_type not in SUPPORTED_EVENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "UNSUPPORTED_EVENT_TYPE",
                "message": "El eventType recibido no genera notificaciones en este servicio.",
                "details": [
                    {
                        "field": "eventType",
                        "message": (
                            f"Valor recibido '{event.event_type}' no está soportado. "
                            f"Valores válidos: {', '.join(SUPPORTED_EVENT_TYPES)}."
                        ),
                    }
                ],
            },
        )

    # 200 — idempotencia: si el eventId ya fue procesado, no duplicamos.
    if event.event_id in _processed_events:
        response.status_code = 200
        return NotificationIdempotentResponse(
            notification_id=_processed_events[event.event_id],
            event_id=event.event_id,
            idempotent=True,
            message="Evento ya procesado. No se generó notificación duplicada.",
        )

    # 201 — generamos la notificación mock.
    notification_id = "NTF-b2c3d4e5-f6a7-8901-2345-67890abcdef1"
    _processed_events[event.event_id] = notification_id

    payload = event.payload or {}
    # Grupo 6 (Despacho) envía el payload en snake_case (order_id), por eso
    # intentamos ambas variantes antes de quedarnos sin dato.
    order_id = payload.get("orderId") or payload.get("order_id") or "tu pedido"
    user_id = payload.get("userId") or payload.get("user_id") or "00000000-0000-0000-0000-000000000000"

    title, body_template = NOTIFICATION_TEMPLATES[event.event_type]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return Notification(
        notification_id=notification_id,
        user_id=user_id,
        event_id=event.event_id,
        event_type=event.event_type,
        title=title,
        body=body_template.format(orderId=order_id),
        channel="DASHBOARD",
        status="DELIVERED",
        payload=payload,
        created_at=now,
    )
