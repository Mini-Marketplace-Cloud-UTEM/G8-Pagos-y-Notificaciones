import uuid
from datetime import datetime, timezone
from typing import Optional

from app.database.supabase_client import supabase
from app.schemas.payments import CreatePaymentRequest
from app.services.mercadopago_service import mercadopago_service


class PaymentService:
    @staticmethod
    def _payment_from_row(row: dict, idempotent: bool = False) -> dict:
        return {
            "payment_id": row["payment_id"],
            "order_id": row["order_id"],
            "user_id": row["user_id"],
            "amount": row["amount"],
            "currency": row["currency"],
            "method": row["method"],
            "status": row["status"],
            "provider": row.get("provider") or "MERCADOPAGO",
            "provider_preference_id": row.get("provider_preference_id"),
            "provider_payment_id": row.get("provider_payment_id"),
            "checkout_url": row.get("checkout_url"),
            "provider_status": row.get("provider_status"),
            "idempotency_key": row["idempotency_key"],
            "correlation_id": row.get("correlation_id"),
            "failure_reason": row.get("failure_reason"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "_idempotent": idempotent,
        }

    @staticmethod
    def create_payment(
        request: CreatePaymentRequest,
        idempotency_key: str,
        correlation_id: Optional[str] = None,
    ) -> dict:
        """
        Crea un pago en Supabase y una preferencia en Mercado Pago.
        Si el idempotency_key ya existe, retorna el pago original.
        """

        if request.currency != "CLP":
            raise ValueError("INVALID_CURRENCY")

        if request.method != "MERCADOPAGO":
            raise ValueError("INVALID_PAYMENT_METHOD")

        existing_payment = (
            supabase.table("payments")
            .select("*")
            .eq("idempotency_key", idempotency_key)
            .execute()
        )

        if existing_payment.data:
            return PaymentService._payment_from_row(existing_payment.data[0], idempotent=True)

        payment_id = f"PAY-{uuid.uuid4()}"
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        preference = mercadopago_service.create_preference(
            payment_id=payment_id,
            order_id=request.order_id,
            user_id=request.user_id,
            amount=request.amount,
            currency=request.currency,
        )

        new_payment_data = {
            "payment_id": payment_id,
            "order_id": request.order_id,
            "user_id": request.user_id,
            "amount": request.amount,
            "currency": request.currency,
            "method": request.method,
            "status": "PENDING",
            "provider": "MERCADOPAGO",
            "provider_preference_id": preference.get("provider_preference_id"),
            "provider_payment_id": None,
            "checkout_url": preference.get("checkout_url"),
            "provider_status": preference.get("provider_status"),
            "idempotency_key": idempotency_key,
            "correlation_id": correlation_id,
            "failure_reason": None,
            "created_at": now,
            "updated_at": now,
        }

        result = supabase.table("payments").insert(new_payment_data).execute()

        if not result.data:
            raise RuntimeError("Error al crear el pago en la base de datos.")

        return PaymentService._payment_from_row(result.data[0], idempotent=False)


payment_service = PaymentService()