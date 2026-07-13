from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from google.cloud import pubsub_v1
from google.oauth2 import service_account

logger = logging.getLogger(__name__)


class PaymentEventPublisher:
    """Publica eventos de estado de pago en Google Cloud Pub/Sub."""

    STATUS_TO_EVENT = {
        "PENDING": "PAYMENT_PENDING",
        "APPROVED": "PAYMENT_APPROVED",
        "REJECTED": "PAYMENT_REJECTED",
    }

    def __init__(self) -> None:
        self._publisher: Optional[pubsub_v1.PublisherClient] = None
        self._topic_path: Optional[str] = None

    def _get_client(self) -> tuple[pubsub_v1.PublisherClient, str]:
        """
        Crea el cliente de Pub/Sub usando las credenciales guardadas en Render.

        Se inicializa solo la primera vez para no recrear el cliente
        en cada solicitud.
        """

        if self._publisher and self._topic_path:
            return self._publisher, self._topic_path

        project_id = os.getenv("GCP_PAYMENT_PROJECT_ID")
        topic_id = os.getenv("GCP_PUBSUB_PAYMENT_TOPIC_ID")
        credentials_json = os.getenv("GCP_PAYMENT_SERVICE_ACCOUNT_JSON")

        if not project_id:
            raise RuntimeError(
                "Falta la variable GCP_PAYMENT_PROJECT_ID."
            )

        if not topic_id:
            raise RuntimeError(
                "Falta la variable GCP_PUBSUB_PAYMENT_TOPIC_ID."
            )

        if not credentials_json:
            raise RuntimeError(
                "Falta la variable GCP_PAYMENT_SERVICE_ACCOUNT_JSON."
            )

        try:
            credentials_info = json.loads(credentials_json)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "GCP_PAYMENT_SERVICE_ACCOUNT_JSON no contiene un JSON válido."
            ) from exc

        credentials = (
            service_account.Credentials.from_service_account_info(
                credentials_info
            )
        )

        self._publisher = pubsub_v1.PublisherClient(
            credentials=credentials
        )

        self._topic_path = self._publisher.topic_path(
            project_id,
            topic_id,
        )

        return self._publisher, self._topic_path

    def publish_payment_status(
        self,
        payment: dict[str, Any],
        source: str,
    ) -> dict[str, str]:
        """
        Publica PAYMENT_PENDING, PAYMENT_APPROVED o PAYMENT_REJECTED.
        """

        status = str(payment.get("status", "")).upper()
        event_type = self.STATUS_TO_EVENT.get(status)

        if not event_type:
            raise ValueError(
                f"No hay un evento configurado para el estado {status}."
            )

        payment_id = payment.get("payment_id")

        if not payment_id:
            raise ValueError(
                "El pago no contiene payment_id."
            )

        # Es determinístico: si el mismo estado se publica otra vez,
        # los consumidores pueden detectar el duplicado con eventId.
        event_id = f"EVT-{payment_id}-{status}"

        occurred_at = (
            datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )

        event = {
            "eventId": event_id,
            "eventType": event_type,
            "version": "1.0",
            "occurredAt": occurred_at,
            "producer": "g8-pagos",
            "correlationId": payment.get("correlation_id"),
            "source": source,
            "payload": {
                "paymentId": payment_id,
                "orderId": payment.get("order_id"),
                "userId": payment.get("user_id"),
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
            },
        }

        publisher, topic_path = self._get_client()

        message_data = json.dumps(
            event,
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")

        future = publisher.publish(
            topic_path,
            message_data,
            eventType=event_type,
            producer="g8-pagos",
            paymentId=str(payment_id),
            status=status,
        )

        message_id = future.result(timeout=15)

        logger.info(
            "Evento %s publicado. Message ID: %s",
            event_type,
            message_id,
        )

        return {
            "eventId": event_id,
            "eventType": event_type,
            "messageId": message_id,
            "topic": topic_path,
        }


payment_event_publisher = PaymentEventPublisher()
