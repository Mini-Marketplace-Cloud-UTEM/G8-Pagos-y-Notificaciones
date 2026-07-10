from pydantic import BaseModel, Field
from typing import Optional, List

class CreatePaymentRequest(BaseModel):
    order_id: str = Field(alias="orderId", example="ORD-20260611-001")
    user_id: str = Field(alias="userId", example="e9d8c7b6-a543-2109-8765-fedcba098765")
    amount: int = Field(example=59990)
    currency: str = Field(example="CLP")
    method: str = Field(example="MERCADOPAGO")

    class Config:
        populate_by_name = True

class PaymentResponse(BaseModel):
    payment_id: str = Field(alias="paymentId")
    order_id: str = Field(alias="orderId")
    user_id: str = Field(alias="userId")
    amount: int
    currency: str
    method: str
    status: str
    provider: str = "MERCADOPAGO"
    provider_preference_id: Optional[str] = Field(None, alias="providerPreferenceId")
    provider_payment_id: Optional[str] = Field(None, alias="providerPaymentId")
    checkout_url: Optional[str] = Field(None, alias="checkoutUrl")
    provider_status: Optional[str] = Field(None, alias="providerStatus")
    idempotency_key: str = Field(alias="idempotencyKey")
    correlation_id: Optional[str] = Field(None, alias="correlationId")
    failure_reason: Optional[str] = Field(None, alias="failureReason")
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")

    class Config:
        populate_by_name = True
        by_alias = True

class ConfirmPaymentRequest(BaseModel):
    action: str = Field(example="APPROVE")
    reason: Optional[str] = Field(None, example="Fondos insuficientes.")

class PaymentIdempotentResponse(BaseModel):
    payment_id: str = Field(alias="paymentId")
    status: str
    idempotent: bool = True
    message: str
    checkout_url: Optional[str] = Field(None, alias="checkoutUrl")

    class Config:
        populate_by_name = True
        by_alias = True

class PaginationResponse(BaseModel):
    page: int
    page_size: int = Field(alias="pageSize")
    total: int
    total_pages: int = Field(alias="totalPages")
    has_next: bool = Field(alias="hasNext")
    has_prev: bool = Field(alias="hasPrev")

    class Config:
        populate_by_name = True
        by_alias = True

class PaymentListResponse(BaseModel):
    data: List[PaymentResponse]
    pagination: PaginationResponse

    class Config:
        populate_by_name = True
        by_alias = True

class ErrorDetail(BaseModel):
    field: Optional[str] = None
    message: Optional[str] = None

class ErrorResponse(BaseModel):
    code: str
    message: str
    details: Optional[List[ErrorDetail]] = None
    correlation_id: Optional[str] = Field(None, alias="correlationId")

    class Config:
        populate_by_name = True
        by_alias = True