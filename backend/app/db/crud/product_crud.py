"""CRUD operations for Product model"""
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.db.models.product import Product
from app.core.logging import get_logger

logger = get_logger(__name__)


class ProductCRUD:
    """CRUD operations for Product model"""

    async def create(
        self,
        db: AsyncSession,
        name: str,
        gtin: str,
        package_capacity: int,
        color: str,
        venchik: str,
        size: str
    ) -> Product:
        """Create new product"""
        product = Product(
            name=name,
            gtin=gtin,
            package_capacity=package_capacity,
            color=color,
            venchik=venchik,
            size=size
        )

        db.add(product)
        await db.commit()
        await db.refresh(product)

        logger.info(f"Product created: {product.id}")
        return product

    async def get_by_id(self, db: AsyncSession, product_id: int) -> Optional[Product]:
        """Get product by ID"""
        result = await db.execute(
            select(Product).where(Product.id == product_id)
        )
        return result.scalar_one_or_none()

    async def get_by_gtin(self, db: AsyncSession, gtin: str) -> Optional[Product]:
        """Get product by GTIN"""
        result = await db.execute(
            select(Product).where(Product.gtin == gtin)
        )
        return result.scalar_one_or_none()

    async def get_or_create_by_gtin(
        self,
        db: AsyncSession,
        name: str,
        gtin: str,
        package_capacity: int,
        color: str,
        venchik: str,
        size: str
    ) -> Product:
        """Get existing product by GTIN or create new one"""
        product = await self.get_by_gtin(db, gtin)
        if not product:
            product = await self.create(db, name, gtin,
                        package_capacity, color, venchik, size)
        else:
            # Update product name if different
            product_name = getattr(product, "name")
            if product_name != name:
                product_name = name
                await db.commit()
                await db.refresh(product)
                logger.info(f"Product {product.id} updated with new name")

        return product

    async def get_all(
        self,
        db: AsyncSession,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Product]:
        """Get all products with pagination"""
        query = select(Product)
        if limit > 0:
            query = query.offset(skip).limit(limit)

        result = await db.execute(query)
        return list(result.scalars().all())

    async def update(
        self,
        db: AsyncSession,
        product_id: int,
        **kwargs
    ) -> Optional[Product]:
        """Update product fields"""
        product = await self.get_by_id(db, product_id)
        if product:
            for key, value in kwargs.items():
                if hasattr(product, key):
                    setattr(product, key, value)

            await db.commit()
            await db.refresh(product)
            logger.info(f"Product {product_id} updated")

        return product

    async def delete(self, db: AsyncSession, product_id: int) -> bool:
        """Delete product by ID"""
        product = await self.get_by_id(db, product_id)
        if product:
            await db.delete(product)
            await db.commit()
            logger.info(f"Product {product_id} deleted")
            return True
        return False


product_crud = ProductCRUD()