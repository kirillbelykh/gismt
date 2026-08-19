"""Product model"""
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from app.db.base import Base


class Product(Base):
    """Product model - linked only to orders"""
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    gtin = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)  # Упрощенное название
    package_capacity = Column(Integer, default=10, nullable=False)
    color = Column(String, nullable=True)
    venchik = Column(String, nullable=True)
    size = Column(String, nullable=True)
    units_per_pack = Column(Integer, nullable=True)

    # Relationships
    orders = relationship("Order", back_populates="product")

    def __repr__(self):
        return f"<Product(id={self.id}, gtin={self.gtin}, name={self.name})>"