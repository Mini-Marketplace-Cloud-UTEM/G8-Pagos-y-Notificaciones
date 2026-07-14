from __future__ import annotations

import logging
import uuid
from typing import Any

from app.db import get_supabase

logger = logging.getLogger(__name__)


class PaymentNotificationService:
    """
    Crea notificaciones de dashboard cuando cambia el estado de un pago.

    Usa un event_id determinístico para evitar notificaciones duplicadas
    cuando Mercado Pago reintenta un webhook.
    """

    TABLE = "notifications"

    STATUS_TO_EVENT = {
        "PENDING": "PAYMENT_PENDING",
        "APPROVED": "PAYMENT_APPROVED",
        "REJECTED": "PAYMENT_REJECTED",
    }

    TEMPLATES = {
        "PAYMENT_PENDING": (
            "Tu pago está pendiente",
            "El pago de tu pedido {order_id} está siendo procesado.",
        ),
        "PAYMENT_APPROVED": (
            "¡Tu pago fue aprobado!",
            "El pago de tu pedido {order_id} fue procesado exitosamente.",
        ),
        "PAYMENT_REJECTED": (
            "Tu pago fue rechazado",
            "El pago de tu pedido {order_id} no pudo ser procesado.",
        ),
    }

    @staticmethod
    def _is_duplicate_error(exc: Exception) -> bool:
        """Detecta una violación UNIQUE de PostgreSQL."""

        error_text = (
            str(getattr(exc, "message", "") or "")
            + " "
            + str(exc)
        ).lower()

        return (
            "23505" in error_text
            or "duplicate key" in error_text
            or "unique constraint" in error_text
        )

    def create_from_payment(
        self,
        payment: dict[str, Any],
        source: str,
    ) -> dict[str, Any]:
        """
        Genera una notificación usando la información del pago.

        Retorna una respuesta idempotente si la notificación ya existe.
        """

        status = str(payment.get("status", "")).upper()
        event_type = self.STATUS_TO_EVENT.get(status)

        if not event_type:
            raise ValueError(
                f"No existe una notificación configurada para {status}."
            )

        payment_id = payment.get("payment_id")
        order_id = payment.get("order_id")
        user_id = payment.get("user_id")

        if not payment_id:
            raise ValueError(
                "El pago no contiene payment_id."
            )

        if not user_id:
            raise ValueError(
                "El pago no contiene user_id."
            )

        # Coincide con el eventId usado en payment_event_publisher.py.
        event_id = f"EVT-{payment_id}-{status}"

        supabase = get_supabase()

        existing = (
            supabase.table(self.TABLE)
            .select("*")
            .eq("event_id", event_id)
            .limit(1)
            .execute()
        )

        if existing.data:
            notification = existing.data[0]

            return {
                "notificationId": notification["notification_id"],
                "eventId": event_id,
                "eventType": event_type,
                "idempotent": True,
                "created": False,
            }

        title, body_template = self.TEMPLATES[event_type]

        payload = {
            "paymentId": payment_id,
            "orderId": order_id,
            "userId": user_id,
            "amount": payment.get("amount"),
            "currency": payment.get("currency"),
            "method": payment.get("method"),
            "provider": (
                payment.get("provider")
                or "MERCADOPAGO"
            ),
            "providerPreferenceId": payment.get(
                "provider_preference_id"
            ),
            "providerPaymentId": payment.get(
                "provider_payment_id"
            ),
            "providerStatus": payment.get(
                "provider_status"
            ),
            "status": status,
            "source": source,
        }

        new_notification = {
            "notification_id": f"NTF-{uuid.uuid4()}",
            "user_id": str(user_id),
            "event_id": event_id,
            "event_type": event_type,
            "title": title,
            "body": body_template.format(
                order_id=order_id or "tu pedido"
            ),
            "channel": "DASHBOARD",
            "status": "DELIVERED",
            "payload": payload,
        }

        try:
            result = (
                supabase.table(self.TABLE)
                .insert(new_notification)
                .execute()
            )

        except Exception as exc:
            # Podría llegar un webhook repetido entre la consulta y el insert.
            if self._is_duplicate_error(exc):
                duplicate = (
                    supabase.table(self.TABLE)
                    .select("*")
                    .eq("event_id", event_id)
                    .limit(1)
                    .execute()
                )

                notification_id = (
                    duplicate.data[0]["notification_id"]
                    if duplicate.data
                    else new_notification["notification_id"]
                )

                return {
                    "notificationId": notification_id,
                    "eventId": event_id,
                    "eventType": event_type,
                    "idempotent": True,
                    "created": False,
                }

            raise

        created = (
            result.data[0]
            if result.data
            else new_notification
        )

        logger.info(
            "Notificación %s creada para el pago %s.",
            event_type,
            payment_id,
        )

        return {
            "notificationId": created["notification_id"],
            "eventId": event_id,
            "eventType": event_type,
            "idempotent": False,
            "created": True,
        }


payment_notification_service = PaymentNotificationService()