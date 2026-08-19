"""CRUD operations package"""

from app.db.crud.order_crud import order_crud
from app.db.crud.product_crud import product_crud
from app.db.crud.marking_code_crud import marking_code_crud
from app.db.crud.camera_crud import camera_crud
from app.db.crud.box_crud import box_crud

__all__ = [
    "order_crud",
    "product_crud",
    "marking_code_crud",
    "camera_crud",
    "box_crud"
]