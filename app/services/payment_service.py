import uuid
from datetime import datetime, timezone
from typing import Optional
from app.database.supabase_client import supabase
from app.schemas.payments import CreatePaymentRequest, PaymentResponse

class PaymentService:
    @staticmethod
    def create_payment(
        request: CreatePaymentRequest,
        idempotency_key: str,
        correlation_id: Optional[str] = None
    ) -> dict:
        """
        Crea un nuevo pago en Supabase.
        Implementa idempotencia: si ya existe un pago con el mismo idempotency_key,
        retorna el pago existente.
        """
        
        # Verificar idempotencia: buscar si ya existe un pago con esta key
        existing_payment = supabase.table("payments") \
            .select("*") \
            .eq("idempotency_key", idempotency_key) \
            .execute()
        
        if existing_payment.data and len(existing_payment.data) > 0:
            # Ya existe un pago con este idempotency_key, retornar el existente
            existing = existing_payment.data[0]
            return {
                "payment_id": existing["payment_id"],
                "order_id": existing["order_id"],
                "user_id": existing["user_id"],
                "amount": existing["amount"],
                "currency": existing["currency"],
                "method": existing["method"],
                "status": existing["status"],
                "idempotency_key": existing["idempotency_key"],
                "correlation_id": existing["correlation_id"],
                "failure_reason": existing["failure_reason"],
                "created_at": existing["created_at"],
                "updated_at": existing["updated_at"]
            }
        
        # Generar payment_id único
        payment_id = f"PAY-{str(uuid.uuid4())}"
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        
        # Crear nuevo pago
        new_payment_data = {
            "payment_id": payment_id,
            "order_id": request.order_id,
            "user_id": request.user_id,
            "amount": request.amount,
            "currency": request.currency,
            "method": request.method,
            "status": "PENDING",
            "idempotency_key": idempotency_key,
            "correlation_id": correlation_id,
            "failure_reason": None,
            "created_at": now,
            "updated_at": now
        }
        
        # Insertar en Supabase
        result = supabase.table("payments").insert(new_payment_data).execute()
        
        if not result.data or len(result.data) == 0:
            raise Exception("Error al crear el pago en la base de datos")
        
        return new_payment_data

payment_service = PaymentService()