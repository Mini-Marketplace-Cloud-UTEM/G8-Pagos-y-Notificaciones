import os
from typing import Any, Dict, Optional

import requests


class MercadoPagoService:
    BASE_URL = "https://api.mercadopago.com"

    def _headers(self) -> Dict[str, str]:
        access_token = os.getenv("MERCADOPAGO_ACCESS_TOKEN")

        if not access_token:
            raise RuntimeError("MERCADOPAGO_ACCESS_TOKEN no está configurado en variables de entorno.")

        return {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    def create_preference(
        self,
        payment_id: str,
        order_id: str,
        user_id: str,
        amount: int,
        currency: str,
    ) -> Dict[str, Optional[str]]:
        """
        Crea una preferencia de pago en Mercado Pago Checkout Pro.
        Devuelve el ID de preferencia y la URL de checkout.
        """

        frontend_success_url = os.getenv("FRONTEND_SUCCESS_URL")
        frontend_failure_url = os.getenv("FRONTEND_FAILURE_URL")
        frontend_pending_url = os.getenv("FRONTEND_PENDING_URL")
        webhook_url = os.getenv("MERCADOPAGO_WEBHOOK_URL")

        preference_body: Dict[str, Any] = {
            "items": [
                {
                    "id": order_id,
                    "title": f"Pedido {order_id}",
                    "quantity": 1,
                    "currency_id": currency,
                    "unit_price": float(amount),
                }
            ],
            "external_reference": payment_id,
            "metadata": {
                "payment_id": payment_id,
                "order_id": order_id,
                "user_id": user_id,
            },
        }

        if frontend_success_url and frontend_failure_url and frontend_pending_url:
            preference_body["back_urls"] = {
                "success": frontend_success_url,
                "failure": frontend_failure_url,
                "pending": frontend_pending_url,
            }
            preference_body["auto_return"] = "approved"

        if webhook_url:
            preference_body["notification_url"] = webhook_url

        response = requests.post(
            f"{self.BASE_URL}/checkout/preferences",
            headers=self._headers(),
            json=preference_body,
            timeout=15,
        )

        if response.status_code >= 400:
            raise RuntimeError(f"Mercado Pago rechazó la preferencia: {response.text}")

        data = response.json()

        return {
            "provider_preference_id": data.get("id"),
            "checkout_url": data.get("sandbox_init_point") or data.get("init_point"),
            "provider_status": "created",
        }

    def get_payment(self, provider_payment_id: str) -> Dict[str, Any]:
        """
        Consulta en Mercado Pago el estado real de un pago usando el ID enviado por webhook.
        """

        response = requests.get(
            f"{self.BASE_URL}/v1/payments/{provider_payment_id}",
            headers=self._headers(),
            timeout=15,
        )

        if response.status_code >= 400:
            raise RuntimeError(f"No se pudo consultar el pago en Mercado Pago: {response.text}")

        return response.json()


mercadopago_service = MercadoPagoService()