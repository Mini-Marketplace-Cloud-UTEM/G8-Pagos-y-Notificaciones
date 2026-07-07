import base64
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List

from fastapi import APIRouter, HTTPException, Request, status

from google.cloud import pubsub_v1
from google.oauth2 import service_account

from app.db import get_supabase

router = APIRouter(
    prefix="/v1/integrations/g6",
    tags=["Integrations - G6"]
)


SUPPORTED_G6_EVENTS = {
    "SHIPMENT_CREATED",
    "SHIPMENT_IN_TRANSIT",
    "SHIPMENT_DELIVERED",
    "SHIPMENT_CANCELLED",
    "SHIPMENT_FAILED",
    "SHIPMENT_RETURNED",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def decode_pubsub_or_raw_event(body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Acepta:
    1) Evento directo desde Postman.
    2) Evento envuelto por GCP Pub/Sub Push.
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
            return json.loads(decoded)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "INVALID_PUBSUB_DATA",
                    "message": f"No se pudo decodificar message.data como JSON: {str(exc)}"
                }
            )

    return body


def get_value(payload: Dict[str, Any], camel_key: str, snake_key: Optional[str] = None):
    """
    G6 confirmó camelCase, pero dejamos snake_case como respaldo.
    """
    if camel_key in payload:
        return payload.get(camel_key)

    if snake_key and snake_key in payload:
        return payload.get(snake_key)

    return None


def resolve_user_id(payload: Dict[str, Any]) -> str:
    """
    G6 actualmente no envía userId en su contrato.
    Para E4 podemos usar:
    1. userId si viene en payload.
    2. G6_DEFAULT_USER_ID desde Render como fallback temporal.
    """

    user_id = get_value(payload, "userId", "user_id")

    if user_id:
        return user_id

    default_user_id = os.getenv("G6_DEFAULT_USER_ID")

    if default_user_id:
        return default_user_id

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "code": "MISSING_USER_ID",
            "message": (
                "El evento de G6 no contiene userId. "
                "Configura G6_DEFAULT_USER_ID en Render o coordina con G6/G5 para resolver userId desde orderId."
            )
        }
    )


def build_title_and_body(event_type: str, payload: Dict[str, Any]) -> Dict[str, str]:
    shipment_id = get_value(payload, "shipmentId", "shipment_id")
    order_id = get_value(payload, "orderId", "order_id")
    customer_name = get_value(payload, "customerName", "customer_name")
    city = get_value(payload, "city")
    new_status = get_value(payload, "newStatus", "new_status")
    previous_status = get_value(payload, "previousStatus", "previous_status")
    package_index = get_value(payload, "packageIndex", "package_index")
    total_packages = get_value(payload, "totalPackages", "total_packages")

    order_text = order_id or "tu pedido"
    shipment_text = shipment_id or "tu despacho"

    if event_type == "SHIPMENT_CREATED":
        return {
            "title": "Tu despacho fue creado",
            "body": f"El despacho {shipment_text} del pedido {order_text} fue registrado correctamente."
        }

    if event_type == "SHIPMENT_IN_TRANSIT":
        return {
            "title": "Tu pedido va en camino",
            "body": f"El despacho {shipment_text} del pedido {order_text} ya está en tránsito."
        }

    if event_type == "SHIPMENT_DELIVERED":
        if package_index is not None and total_packages is not None:
            try:
                package_index_int = int(package_index)
                total_packages_int = int(total_packages)

                if package_index_int < total_packages_int:
                    return {
                        "title": "Entrega parcial realizada",
                        "body": (
                            f"Tu caja {package_index_int} de {total_packages_int} del pedido {order_text} "
                            f"fue entregada correctamente. El resto sigue en camino."
                        )
                    }

                if package_index_int == total_packages_int:
                    return {
                        "title": "Pedido completado",
                        "body": (
                            f"Tu pedido {order_text} fue entregado completamente. "
                            f"Última caja recibida: {package_index_int} de {total_packages_int}."
                        )
                    }

            except ValueError:
                pass

        return {
            "title": "Tu pedido fue entregado",
            "body": f"El despacho {shipment_text} del pedido {order_text} fue entregado exitosamente."
        }

    if event_type == "SHIPMENT_CANCELLED":
        return {
            "title": "Despacho cancelado",
            "body": f"El despacho {shipment_text} del pedido {order_text} fue cancelado."
        }

    if event_type == "SHIPMENT_FAILED":
        return {
            "title": "Problema con tu despacho",
            "body": f"No se pudo completar el despacho {shipment_text} del pedido {order_text}."
        }

    if event_type == "SHIPMENT_RETURNED":
        return {
            "title": "Despacho devuelto",
            "body": f"El despacho {shipment_text} del pedido {order_text} fue devuelto al centro de distribución."
        }

    return {
        "title": "Actualización de despacho",
        "body": f"El pedido {order_text} tuvo una actualización de estado: {new_status or event_type}."
    }


def build_g6_notification(event: Dict[str, Any]) -> Dict[str, Any]:
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

    if event_type not in SUPPORTED_G6_EVENTS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "UNSUPPORTED_EVENT_TYPE",
                "message": "El eventType recibido no está soportado para eventos G6.",
                "details": [
                    {
                        "field": "eventType",
                        "message": f"Valor recibido: {event_type}"
                    }
                ],
                "correlationId": correlation_id
            }
        )

    shipment_id = get_value(payload, "shipmentId", "shipment_id")
    order_id = get_value(payload, "orderId", "order_id")

    missing_fields = []

    if not shipment_id:
        missing_fields.append("payload.shipmentId")

    if not order_id:
        missing_fields.append("payload.orderId")

    if missing_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_G6_PAYLOAD",
                "message": "El payload del evento G6 no contiene todos los campos requeridos.",
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

    user_id = resolve_user_id(payload)
    text = build_title_and_body(event_type, payload)

    return {
        "notification_id": f"NTF-{uuid.uuid4()}",
        "user_id": user_id,
        "event_id": event_id,
        "event_type": event_type,
        "title": text["title"],
        "body": text["body"],
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

    supabase = get_supabase()

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

    notification = build_g6_notification(event)

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
    
def get_gcp_credentials():
    raw_json = os.getenv("GCP_SERVICE_ACCOUNT_JSON")

    if not raw_json:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "MISSING_GCP_CREDENTIALS",
                "message": "Falta configurar GCP_SERVICE_ACCOUNT_JSON en Render."
            }
        )

    try:
        service_account_info = json.loads(raw_json)
        return service_account.Credentials.from_service_account_info(service_account_info)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "INVALID_GCP_CREDENTIALS",
                "message": f"No se pudo leer GCP_SERVICE_ACCOUNT_JSON: {str(exc)}"
            }
        )


def get_pubsub_subscriber():
    credentials = get_gcp_credentials()
    return pubsub_v1.SubscriberClient(credentials=credentials)


def get_subscription_path(subscriber: pubsub_v1.SubscriberClient) -> str:
    project_id = os.getenv("GCP_PROJECT_ID")
    subscription_id = os.getenv("GCP_PUBSUB_SUBSCRIPTION_ID")

    if not project_id or not subscription_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "MISSING_GCP_CONFIG",
                "message": "Faltan GCP_PROJECT_ID o GCP_PUBSUB_SUBSCRIPTION_ID en Render."
            }
        )

    return subscriber.subscription_path(project_id, subscription_id)


def decode_pubsub_pull_message(message_data: bytes) -> Dict[str, Any]:
    try:
        decoded = message_data.decode("utf-8")
        return json.loads(decoded)
    except Exception as exc:
        raise ValueError(f"No se pudo decodificar el mensaje Pub/Sub como JSON: {str(exc)}")


@router.post("/pull-once")
async def pull_g6_events_once(max_messages: int = 5):
    subscriber = get_pubsub_subscriber()
    subscription_path = get_subscription_path(subscriber)

    processed: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    ack_ids: List[str] = []

    try:
        response = subscriber.pull(
            request={
                "subscription": subscription_path,
                "max_messages": max_messages,
            },
            timeout=10,
        )

        received_messages = response.received_messages

        if not received_messages:
            return {
                "message": "No había mensajes disponibles en la suscripción.",
                "processedCount": 0,
                "processed": [],
                "errors": []
            }

        for received_message in received_messages:
            ack_id = received_message.ack_id
            pubsub_message = received_message.message

            try:
                event = decode_pubsub_pull_message(pubsub_message.data)
                event_id = event.get("eventId")

                if not event_id:
                    raise ValueError("El evento no contiene eventId.")

                supabase = get_supabase()

                existing_result = (
                    supabase
                    .table("notifications")
                    .select("*")
                    .eq("event_id", event_id)
                    .execute()
                )

                existing_data = existing_result.data or []

                if existing_data:
                    existing = existing_data[0]
                    processed.append({
                        "eventId": event_id,
                        "status": "IDEMPOTENT",
                        "notificationId": existing.get("notification_id"),
                        "message": "Evento ya procesado. No se creó duplicado."
                    })
                    ack_ids.append(ack_id)
                    continue

                notification = build_g6_notification(event)

                insert_result = (
                    supabase
                    .table("notifications")
                    .insert(notification)
                    .execute()
                )

                inserted_data = insert_result.data or []

                if not inserted_data:
                    raise ValueError("Supabase no retornó la notificación creada.")

                inserted = inserted_data[0]

                processed.append({
                    "eventId": event_id,
                    "status": "CREATED",
                    "notificationId": inserted.get("notification_id"),
                    "eventType": inserted.get("event_type"),
                    "title": inserted.get("title")
                })

                ack_ids.append(ack_id)

            except Exception as exc:
                errors.append({
                    "messageId": pubsub_message.message_id,
                    "error": str(exc)
                })

        if ack_ids:
            subscriber.acknowledge(
                request={
                    "subscription": subscription_path,
                    "ack_ids": ack_ids,
                }
            )

        return {
            "subscription": subscription_path,
            "receivedCount": len(received_messages),
            "processedCount": len(processed),
            "ackedCount": len(ack_ids),
            "processed": processed,
            "errors": errors
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "PUBSUB_PULL_ERROR",
                "message": f"No se pudieron consumir eventos desde Pub/Sub: {str(exc)}"
            }
        )

    finally:
        subscriber.close()