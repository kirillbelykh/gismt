"""Box schemas"""
from typing import List, Optional
from pydantic import BaseModel


class BoxScanRequest(BaseModel):
    """Box scan request schema"""
    order_id: int
    batch_id: Optional[int] = None
    raw_codes: List[str]


class BoxScanResponse(BaseModel):
    """Box scan response schema"""
    box_id: int
    sscc: str
    print_url: str

    class Config:
        from_attributes = True


class BoxStatusResponse(BaseModel):
    """Box status response schema"""
    id: int
    sscc: str
    status: str
    created_at: str

    class Config:
        from_attributes = True

class AggregationRequest(BaseModel):
    order_id: int