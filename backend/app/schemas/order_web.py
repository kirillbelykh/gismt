from datetime import date
from typing import Optional, Annotated

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
    ConfigDict,
)
from app.core.logging import get_logger

logger = get_logger(__name__)


class OrderCreateForm(BaseModel):
    """Модель для создания заказа через веб-форму"""
    model_config = ConfigDict(json_encoders={date: lambda v: v.isoformat()})
    # Альтернатива через from_attributes=True, нужно только если используешь orm_mode

    quantity: Annotated[int, Field(gt=0, le=10_000, description="Количество кодов маркировки")]
    batch_number: str
    prod_date: date
    exp_date: date

    gtin: Optional[str] = Field(min_length=13, max_length=14, description="номер GTIN")
    simpl_name: str = None
    size: Optional[str] = None
    units_per_pack: Optional[int] = Field(None, gt=0)
    color: Optional[str] = None
    venchik: Optional[str] = None
    order_name: Optional[str] = None

    # Преобразование пустых строк в None для всех полей
    @field_validator('*', mode='before')
    @classmethod
    def empty_str_to_none(cls, v):
        if isinstance(v, str) and not v.strip():
            return None
        return v

    # Проверка, что срок годности позже даты производства
    @field_validator('exp_date')
    @classmethod
    def validate_exp_date(cls, v: date, info):
        # info.data доступен только в mode='after', поэтому делаем через model_validator
        # поэтому лучше вынести эту логику в model_validator (см. ниже)
        return v

    # Проверка ручных полей, если нет GTIN
    @field_validator('simpl_name', 'size', 'units_per_pack')
    @classmethod
    def validate_manual_fields(cls, v, info):
        # В field_validator info.data ещё не полностью сформирован при mode='before',
        # поэтому тоже лучше вынести в model_validator
        return v

    # Лучше всё, что зависит от нескольких полей — вынести в model_validator
    @model_validator(mode='after')
    def check_consistency(self):
        # 1. Дата окончания срока годности > даты производства
        if self.exp_date <= self.prod_date:
            raise ValueError('Дата окончания срока годности должна быть позже даты производства')

        # 2. Если нет GTIN — обязательны ручные поля
        if not self.gtin:
            missing = []
            if not self.simpl_name:
                missing.append('simpl_name')
            if not self.size:
                missing.append('size')
            if self.units_per_pack is None:
                missing.append('units_per_pack')

            if missing:
                raise ValueError(
                    f'При отсутствии GTIN необходимо заполнить поля: {", ".join(missing)}'
                )
        return self