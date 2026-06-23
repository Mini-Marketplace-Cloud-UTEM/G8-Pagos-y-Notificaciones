from pydantic import BaseModel, Field
from typing import Optional, List, Any


# ── REQUEST ──────────────────────────────────────────────
# eventId y eventType se reciben como opcionales (no como required de
# Pydantic) para poder devolver los errores 400 MISSING_EVENT_ID y
# 422 UNSUPPORTED_EVENT_TYPE con el formato EXACTO del contrato,
# en vez del 422 genérico que Pydantic genera por defecto.
class TestNotificationRequest(BaseModel):
    event_id: Optional[str] = Field(
        None, alias="eventId", example="evt-550e8400-e29b-41d4-a716-446655440001"
    )
    event_type: Optional[str] = Field(None, alias="eventType", example="PAYMENT_APPROVED")
    version: str = Field(example="1.0")
    occurred_at: str = Field(alias="occurredAt", example="2026-06-15T20:00:00Z")
    producer: str = Field(example="g8-pagos")
    correlation_id: Optional[str] = Field(
        None, alias="correlationId", example="99999999-8888-4777-9666-555555555555"
    )
    payload: dict = Field(
        example={
            "paymentId": "PAY-a1b2c3d4-e5f6-7890-1234-56789abcdef0",
            "orderId": "ORD-20260611-001",
            "userId": "e9d8c7b6-a543-2109-8765-fedcba098765",
            "amount": 59990,
            "currency": "CLP",
        }
    )

    class Config:
        populate_by_name = True


# ── RECURSOS ─────────────────────────────────────────────
class Notification(BaseModel):
    notification_id: str = Field(alias="notificationId")
    user_id: str = Field(alias="userId")
    event_id: str = Field(alias="eventId")
    event_type: str = Field(alias="eventType")
    title: str
    body: str
    channel: str = "DASHBOARD"
    status: str
    payload: Optional[Any] = None
    created_at: str = Field(alias="createdAt")

    class Config:
        populate_by_name = True


class Pagination(BaseModel):
    page: int
    page_size: int = Field(alias="pageSize")
    total: int
    total_pages: int = Field(alias="totalPages")
    has_next: bool = Field(alias="hasNext")
    has_prev: bool = Field(alias="hasPrev")

    class Config:
        populate_by_name = True


class NotificationListResponse(BaseModel):
    data: List[Notification]
    pagination: Pagination


class NotificationIdempotentResponse(BaseModel):
    notification_id: str = Field(alias="notificationId")
    event_id: str = Field(alias="eventId")
    idempotent: bool = True
    message: str

    class Config:
        populate_by_name = True
