import base64
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request, status

from app.db import get_supabase_client

router = APIRouter(
    prefix="/v1/integrations/g6",
    tags=["Integrations - G6"]
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def decode_pubsub_or_raw_event(body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Acepta dos formatos:

    1) Evento directo, útil para Postman:
    {
      "eventId": "...",
      "eventType": "SHIPMENT_DELIVERED",
      "payload": {...}
    }

    2) Pub/Sub Push:
    {
      "message": {
        "data": "base64-del-json",
        "messageId": "...",
        "publishTime": "..."
      },
      "subscription": "..."
    }
    """

    if "message" in body and isinstance(body["message"], dict):
        message = body["message"]

        if "data" not in message:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "MISSING_PUBSUB_DATA",
                    "message": "El mensaje Pub/Sub no contiene message.data."
                }
            )

        try:
            decoded = base64.b64decode(message["data"]).decode("utf-8")
            event = json.loads(decoded)
            return event
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "INVALID_PUBSUB_DATA",
                    "message": f"No se pudo decodificar message.data como JSON: {str(exc)}"
                }
            )

    return body


def get_payload_value(payload: Dict[str, Any], camel_key: str, snake_key: Optional[str] = None):
    """
    Prioriza camelCase porque G6 confirmó payload en camelCase.
    Acepta snake_case como respaldo para no romper pruebas antiguas.
    """
    if camel_key in payload:
        return payload.get(camel_key)

    if snake_key and snake_key in payload:
        return payload.get(snake_key)

    return None


def build_shipment_notification(event: Dict[str, Any]) -> Dict[str, Any]:
    event_id = event.get("eventId")
    event_type = event.get("eventType")
    correlation_id = event.get("correlationId")
    payload = event.get("payload") or {}

    if not event_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "MISSING_EVENT_ID",
                "message": "El campo eventId es obligatorio."
            }
        )

    if event_type != "SHIPMENT_DELIVERED":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "UNSUPPORTED_EVENT_TYPE",
                "message": "Este endpoint solo procesa eventos SHIPMENT_DELIVERED desde G6.",
                "details": [
                    {
                        "field": "eventType",
                        "message": f"Valor recibido: {event_type}"
                    }
                ],
                "correlationId": correlation_id
            }
        )

    shipment_id = get_payload_value(payload, "shipmentId", "shipment_id")
    order_id = get_payload_value(payload, "orderId", "order_id")
    user_id = get_payload_value(payload, "userId", "user_id")

    missing_fields = []

    if not shipment_id:
        missing_fields.append("payload.shipmentId")

    if not order_id:
        missing_fields.append("payload.orderId")

    if not user_id:
        missing_fields.append("payload.userId")

    if missing_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_SHIPMENT_PAYLOAD",
                "message": "El payload del evento SHIPMENT_DELIVERED no contiene todos los campos requeridos.",
                "details": [
                    {
                        "field": field,
                        "message": "Campo requerido para generar la notificación."
                    }
                    for field in missing_fields
                ],
                "correlationId": correlation_id
            }
        )

    notification_id = f"NTF-{uuid.uuid4()}"

    title = "Tu pedido fue entregado"
    body = f"El pedido {order_id} asociado al envío {shipment_id} fue entregado exitosamente."

    return {
        "notification_id": notification_id,
        "user_id": user_id,
        "event_id": event_id,
        "event_type": event_type,
        "title": title,
        "body": body,
        "channel": "DASHBOARD",
        "status": "DELIVERED",
        "payload": payload,
        "created_at": now_iso()
    }


def to_api_response(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "notificationId": row.get("notification_id"),
        "userId": row.get("user_id"),
        "eventId": row.get("event_id"),
        "eventType": row.get("event_type"),
        "title": row.get("title"),
        "body": row.get("body"),
        "channel": row.get("channel"),
        "status": row.get("status"),
        "payload": row.get("payload"),
        "createdAt": row.get("created_at")
    }


@router.post("/pubsub", status_code=status.HTTP_201_CREATED)
async def receive_g6_pubsub_event(request: Request):
    """
    Endpoint de integración con G6.

    Recibe eventos SHIPMENT_DELIVERED publicados por G6.
    Puede recibir:
    - JSON directo para pruebas con Postman.
    - Formato Pub/Sub Push desde GCP.
    """

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_JSON",
                "message": "El cuerpo de la solicitud no es un JSON válido."
            }
        )

    event = decode_pubsub_or_raw_event(body)

    event_id = event.get("eventId")

    if not event_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "MISSING_EVENT_ID",
                "message": "El campo eventId es obligatorio."
            }
        )

    supabase = get_supabase_client()

    # 1. Idempotencia: si ya existe una notificación con ese event_id, no se duplica.
    try:
        existing_result = (
            supabase
            .table("notifications")
            .select("*")
            .eq("event_id", event_id)
            .execute()
        )

        existing_data = existing_result.data or []

        if len(existing_data) > 0:
            existing = existing_data[0]
            return {
                "notificationId": existing.get("notification_id"),
                "eventId": existing.get("event_id"),
                "idempotent": True,
                "message": "Evento ya procesado. No se generó notificación duplicada."
            }

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "DATABASE_ERROR",
                "message": f"No se pudo consultar la base de datos: {str(exc)}"
            }
        )

    # 2. Crear notificación desde el evento de G6.
    notification = build_shipment_notification(event)

    try:
        insert_result = (
            supabase
            .table("notifications")
            .insert(notification)
            .execute()
        )

        inserted_data = insert_result.data or []

        if len(inserted_data) == 0:
            raise Exception("Supabase no retornó la notificación creada.")

        return to_api_response(inserted_data[0])

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "NOTIFICATION_CREATION_ERROR",
                "message": f"Error al crear la notificación desde evento G6: {str(exc)}"
            }
        )