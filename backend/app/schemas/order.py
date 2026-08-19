"""Order schemas"""
from datetime import date
from typing import Dict, Optional, List, TypedDict
from pydantic import BaseModel


class OrderCreate(BaseModel):
    """Order creation schema"""
    product_id: int
    gtin: str
    quantity: int
    batch_number: str
    prod_date: date
    exp_date: date
    name: str


class OrderResponse(BaseModel):
    """Order response schema"""
    id: int
    external_order_id: Optional[str]
    product_id: int
    batch_number: str
    prod_date: date
    exp_date: date
    qty: int
    status: str
    created_at: str

    class Config:
        from_attributes = True


class OrderWithCodes(OrderResponse):
    """Order with codes"""
    codes: Optional[List[str]] = None

# === Типы для строгой типизации ===
class OrderAggregationInfo(TypedDict):
    order_id: int
    order_name: str
    product_name: str
    codes: List[Dict[str, str]]
    codes_count: int

class VerificationResult(TypedDict):
    orders: Dict[int, OrderAggregationInfo]
    found_codes: List[str]
    not_found_codes: List[str]
    total_codes: int
    found_count: int
    not_found_count: int