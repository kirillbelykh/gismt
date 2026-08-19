from typing import List, Optional
from pydantic import BaseModel

class ScanRequest(BaseModel):
    codes: List[str]
    device_id: str = "scanner_app"

class OrderScanInfo(BaseModel):
    order_id: int
    order_name: Optional[str]
    external_order_id: Optional[str]
    product_name: str
    gtin: str
    quantity: int
    codes: List[str] = []  # Список SGTIN кодов (не полных кодов)

class ScanResponse(BaseModel):
    orders: List[OrderScanInfo]
    total_codes: int
    found_codes: int
    not_found_codes: List[str]

class AggregationTestRequest(BaseModel):
    codes: List[str]
    device_id: str = "scanner_app"