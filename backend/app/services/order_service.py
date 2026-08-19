"""Order service"""
from typing import List, Optional, Tuple, Dict, Any
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.crud.order_crud import order_crud
from app.db.crud.product_crud import product_crud
from app.db.crud.batch_crud import batch_crud
from app.db.crud.marking_code_crud import marking_code_crud
from app.db.models.order import Order, OrderStatus
from app.db.models.marking_code import MarkingCode
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from app.services.code_parse_service import extract_sntin
from app.services.crpt_client_service import CRPTClient
from app.core.logging import get_logger

logger = get_logger(__name__)


class OrderService:
    """Service for managing orders"""

    def __init__(self):
        self.crpt_client = CRPTClient()

    async def create_order(
        self,
        db: AsyncSession,
        product_id: int,
        gtin: str,
        quantity: int,
        name: str,
    ) -> Order:
        """
        Create order in database

        Args:
            db: Database session
            product_id: Product ID
            gtin: GTIN
            quantity: Quantity of codes to order
            batch_number: Batch number
            prod_date: Production date (YYYY-MM-DD)
            exp_date: Expiration date (YYYY-MM-DD)
            name: Product name

        Returns:
            Created order
        """
        return await order_crud.create(
            db=db,
            product_id=product_id,
            name=name,
            gtin=gtin,
            qty=quantity,
            status=OrderStatus.ORDERING,
        )

    async def handle_order_from_web_form(
        self,
        db: AsyncSession,
        nomenclature_service,
        quantity: int,
        batch_number: str,
        prod_date: date,
        exp_date: date,
        gtin: Optional[str] = None,
        simpl_name: Optional[str] = None,
        size: Optional[str] = None,
        units_per_pack: Optional[int] = None,
        color: Optional[str] = None,
        venchik: Optional[str] = None,
        order_name: Optional[str] = None,
    ) -> Tuple[Optional[Order], Optional[str], Optional[str]]:
        """
        Create order from web form data with product lookup in nomenclature

        Args:
            db: Database session
            nomenclature_service: Service for product lookup in Excel
            quantity: Quantity of codes
            batch_number: Batch number
            prod_date: Production date
            exp_date: Expiration date
            gtin: GTIN (optional)
            simpl_name: Simplified name (optional)
            size: Size (optional)
            units_per_pack: Units per pack (optional)
            color: Color (optional)
            venchik: Venchik (optional)
            order_name: Custom order name (optional)

        Returns:
            Tuple: (order object, error_message, success_html_response)
            If error occurs: (None, error_message, None)
            If success: (order, None, html_response)
        """
        try:
            final_gtin = None
            final_name = None
            final_product_name = None

            # Поиск товара в номенклатуре
            product_info = nomenclature_service.find_product_info(
                gtin=gtin,
                simpl_name=simpl_name,
                size=size,
                units_per_pack=str(units_per_pack) if units_per_pack else None,
                color=color,
                venchik=venchik
            )

            if product_info:
                final_gtin = product_info['gtin']
                final_product_name = product_info['full_name']
                final_units_per_pack = int(product_info['units_per_pack']) if product_info['units_per_pack'].isdigit() else 1
                final_color = product_info['color']
                final_venchik = product_info['venchik']
                final_size = product_info['size']


                # Если упрощенное название не указано в форме, берем из Excel
                if not simpl_name and product_info.get('simpl_name'):
                    simpl_name = product_info['simpl_name']

                logger.info(f"Товар найден в номенклатуре: {final_product_name}, GTIN: {final_gtin}")

            # Если товар не найден - возвращаем ошибку
            if not final_gtin:
                error_html = self._create_error_html("GTIN не найден в номенклатуре!")
                return None, "GTIN не найден в номенклатуре", error_html

            # Определяем название ЗАКАЗА (order_name)
            if order_name:
                final_name = self._determine_order_name(
                    order_name)
            else:
                error_html = self._create_error_html("Не указан номер заказа!")
                return None, "Не указан номер заказа", error_html

            # Получаем или создаём продукт в БД
            product = await product_crud.get_or_create_by_gtin(
                db=db,
                name=final_product_name, # type: ignore
                gtin=final_gtin,
                package_capacity=final_units_per_pack, # type: ignore
                color=final_color, # type: ignore
                venchik=final_venchik,  # type: ignore
                size=final_size # type: ignore
            )


            product_id = getattr(product, "id")

            # Создаем заказ
            order = await self.create_order(
                db=db,
                product_id=product_id,
                gtin=final_gtin,
                quantity=quantity,
                name=final_name # type: ignore
            )
            # Получаем или создаём партию
            await batch_crud.get_or_create(
                db=db,
                batch_number=batch_number,
                prod_date=prod_date,
                exp_date=exp_date,
                order_id=getattr(order, "id")
            )
            # Формируем HTML-ответ об успехе
            success_html = self._create_success_html(order, final_name, final_product_name, final_gtin, quantity) # type: ignore

            return order, None, success_html

        except Exception as e:
            logger.exception(f"Ошибка создания заказа из веб-формы: {e}")
            error_html = self._create_error_html(str(e))
            return None, str(e), error_html

    async def delete_order(
        self,
        db: AsyncSession,
        order_id: int,
    ) -> bool:
        """Delete order by ID"""
        return await order_crud.delete(db, order_id)

    async def close_order(
        self,
        db: AsyncSession,
        order_id: int,
    ) -> tuple[bool, str]:
        """Close order in SUZ and update local status"""
        try:
            # 1. Находим внешний ID заказа
            external_order_id = await order_crud.find_ext_order_id(db, order_id)
            if not external_order_id:
                logger.error(f"Order {order_id} не найден или не имеет external_order_id")
                return False, f"Заказ {order_id} не найден или не имеет внешнего ID"

            logger.info(f"Найден внешний ID заказа {order_id}: {external_order_id}")

            # 2. Закрываем заказ в СУЗ
            try:
                order_close_success = await self.crpt_client.close_order(str(external_order_id))
            except Exception as e:
                logger.error(f"Ошибка при закрытии заказа {order_id} в СУЗ: {e}")
                return False, f"Ошибка СУЗ: {str(e)}"

            if not order_close_success:
                logger.error(f"Не удалось закрыть заказ {order_id} в СУЗ")
                return False, "СУЗ не подтвердил закрытие заказа"

            logger.info(f"Заказ {order_id} успешно закрыт в СУЗ")

            # 3. Обновляем статус в локальной БД
            try:
                close_local_success = await order_crud.close(db, order_id)
            except Exception as e:
                logger.error(f"Ошибка при обновлении статуса заказа {order_id} в БД: {e}")
                return False, f"Ошибка БД: {str(e)}"

            if close_local_success:
                logger.info(f"Статус заказа {order_id} успешно обновлен на 'ЗАКРЫТ'")
                return True, f"Заказ {order_id} успешно закрыт"
            else:
                logger.warning(f"Заказ {order_id} закрыт в СУЗ, но не удалось обновить локальный статус")
                return False, "Заказ закрыт в СУЗ, но ошибка обновления локального статуса"

        except Exception as e:
            logger.exception(f"Непредвиденная ошибка при закрытии заказа {order_id}: {e}")
            return False, f"Непредвиденная ошибка: {str(e)}"

    def _determine_order_name(self, order_name: Optional[str]) -> Optional[str]:
        """Determine order name"""
        if order_name and order_name.strip():
            final_name = order_name.strip()
            logger.info(f"Используется указанное название заказа: {final_name}")
            return final_name



    def _create_error_html(self, error_message: str) -> str:
        """Create HTML for error response"""
        if "GTIN не найден" in error_message:
            return """
            <div class="result error">
                <h3>❌ Ошибка создания заказа</h3>
                <p><strong>GTIN не найден в номенклатуре!</strong></p>
                <p>Пожалуйста, убедитесь что:</p>
                <ul style="text-align: left; margin: 10px 0; padding-left: 20px;">
                    <li>Указан правильный GTIN</li>
                    <li>Или указаны все параметры для поиска (упрощенное название, размер, количество)</li>
                    <li>Товар присутствует в файле номенклатуры</li>
                </ul>
                <p>Без корректного GTIN невозможно сгенерировать коды маркировки.</p>
            </div>
            """
        else:
            return f"""
            <div class="result error">
                <h3>❌ Ошибка</h3>
                <p>{error_message}</p>
            </div>
            """

    def _create_success_html(
        self,
        order: Order,
        order_name: str,
        product_name: str,
        gtin: str,
        quantity: int,
    ) -> str:
        """Create HTML for success response"""
        return f"""
        <div class="result success">
            <h3>✅ Заказ создан успешно!</h3>
            <p><strong>Название заказа:</strong> {order_name}</p>
            <p><strong>Название товара:</strong> {product_name}</p>
            <p><strong>GTIN:</strong> {gtin}</p>
            <p><strong>Количество кодов:</strong> {quantity}</p>
            <p style="margin-top: 15px; color: #666;">
                Заказ обрабатывается в фоне. Коды будут доступны через несколько минут.
                Обновите страницу для проверки статуса.
            </p>
        </div>
        """

    async def get_order(self, db: AsyncSession, order_id: int) -> Optional[Order]:
        """Get order by ID with product relationship"""
        return await order_crud.get_by_id(db, order_id)

    async def get_product_by_order(
        self,
        db: AsyncSession,
        order_id: int,
        ) -> Optional[Any]:
        """Get product associated with order"""
        order =  await order_crud.get_by_id(db, order_id)
        if not order:
            return None
        product_id = getattr(order, "product_id")
        return await product_crud.get_by_id(db, product_id)

    async def store_codes(
        self,
        db: AsyncSession,
        order_id: int,
        codes: List[str],
    ) -> int:
        """
        Store marking codes from CRPT

        Args:
            db: Database session
            order_id: Order ID
            codes: List of raw marking codes

        Returns:
            Number of codes stored
        """
        return await marking_code_crud.create_bulk(db, order_id, codes)

    async def update_order_status(
        self,
        db: AsyncSession,
        order_id: int,
        status: OrderStatus,
    ) -> Optional[Order]:
        """Update order status"""
        return await order_crud.update_status(db, order_id, status)

    async def get_all_orders_with_products(
        self,
        db: AsyncSession,
        skip: int = 0,
        limit: int = 20,
    ) -> List[Order]:
        """Get all orders with product information"""
        return await order_crud.get_all(db, skip=skip, limit=limit, order_by="created_at_desc")

    async def get_order_codes(
        self,
        db: AsyncSession,
        order_id: int,
    ) -> List[str]:
        """Get raw marking codes for order"""
        return await marking_code_crud.get_codes_raw_by_order_id(db, order_id)

    async def count_codes_by_order(
        self,
        db: AsyncSession,
        order_id: int,
        status: Optional[str] = None,
    ) -> int:
        """Count marking codes for order"""
        from app.db.models.marking_code import MarkingCodeStatus

        status_enum = None
        if status:
            try:
                status_enum = MarkingCodeStatus(status)
            except ValueError:
                pass

        return await marking_code_crud.count_by_order_id(db, order_id, status_enum)


    async def prepare_order_for_view(
        self,
        db: AsyncSession,
        order_id: int,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[List[str]]]:
        """Prepare order data for viewing (codes and order info)"""

        order = await self.get_order(db, order_id)
        product = await self.get_product_by_order(db, order_id)

        if not order:
            return None, None

        # --- fallback статус из order.status ---
        raw_status = None
        order_status = getattr(order, "status", None)
        if order_status:
            raw_status = (
                order_status.value
                if hasattr(order_status, "value")
                else str(order_status)
            )

        # --- UI-статус через единый сервис ---
        ui_status = await self.get_order_ui_status(
            db=db,
            order_id=order.id, # type: ignore
            fallback_status=raw_status,
        )

        normalized_status = str(ui_status).upper()
        status_map = {
            "READY": "ГОТОВ",
            "PROCESSING": "В ПРОЦЕССЕ",
            "PENDING": "ОЖИДАЕТ",
            "ORDERING": "ЗАКАЗЫВАЕТСЯ",
            "ERROR": "ОШИБКА",
            "CLOSED": "ЗАКРЫТ",
            "AGGREGATING": "ВЫПОЛНЯЕТСЯ АГРЕГАЦИЯ",
            "IN_CIRCULATION": "ВВЕДЕН В ОБОРОТ",
        }
        # --- Получаем коды ---
        # показываем коды:
        # - если заказ ГОТОВ
        # - или если идет АГРЕГАЦИЯ (важно для контроля)
        codes: list[str] = []
        if normalized_status in {"READY", "AGGREGATING"}:
            codes = await self.get_order_codes(db, order_id)

        # --- Форматируем даты ---
        prod_date_str = (
            order.batch.prod_date.strftime('%d.%m.%Y')
            if order.batch and order.batch.prod_date
            else "Не указана"
        )
        exp_date_str = (
            order.batch.exp_date.strftime('%d.%m.%Y')
            if order.batch and order.batch.exp_date
            else "Не указана"
        )

        order_data = {
            "id": order.id,
            "gtin": order.gtin,
            "product_name": getattr(product, "name", "Неизвестен"),
            "name": order.name or "Без названия",
            "qty": order.qty,
            "batch_number": order.batch.batch_number if order.batch else "",
            "prod_date": prod_date_str,
            "exp_date": exp_date_str,

            # ⬇️ ВАЖНО
            "status": normalized_status,
            "status_display": status_map.get(normalized_status, normalized_status),
        }

        return order_data, codes



    async def get_order_info_by_codes(
        self,
        db: AsyncSession,
        raw_codes: List[str],
    ) -> dict:
        """
        Собирает информацию о заказе по списку DataMatrix-кодов
        """

        # 1. Извлекаем SNTIN
        sntins: list[str] = []
        for code in raw_codes:
            sntin = extract_sntin(code)
            if not sntin:
                raise ValueError(f"Неверный формат кода: {code}")
            sntins.append(sntin)

        # 2. Находим коды
        result = await db.execute(
            select(MarkingCode).where(MarkingCode.sntin.in_(sntins))
        )
        codes = result.scalars().all()

        if not codes:
            raise ValueError("Коды не найдены")

        # 3. Проверяем, что все коды из одного заказа
        order_ids = {c.order_id for c in codes}
        if len(order_ids) != 1:
            raise ValueError("Коды принадлежат разным заказам")

        order_id = order_ids.pop()

        # 4. Получаем заказ СРАЗУ с batch и product (❗ КЛЮЧЕВОЕ МЕСТО)
        stmt = (
            select(Order)
            .options(
                selectinload(Order.batch),
                selectinload(Order.product),
            )
            .where(Order.id == order_id)
        )

        result = await db.execute(stmt)
        order: Order | None = result.scalar_one_or_none()

        if not order:
            raise ValueError("Заказ не найден")

        batch = order.batch
        product = order.product

        # 5. Считаем общее количество кодов в заказе
        total_codes = await db.scalar(
            select(func.count(MarkingCode.id))
            .where(MarkingCode.order_id == order_id)
        )

        return {
            "order_id": order.id,
            "order_name": order.name or "Без названия",
            "product_name": product.name if product else "Неизвестен",
            "batch_number": batch.batch_number if batch else None,
            "prod_date": batch.prod_date.strftime("%d.%m.%Y") if batch and batch.prod_date else None,
            "exp_date": batch.exp_date.strftime("%d.%m.%Y") if batch and batch.exp_date else None,
            "total_codes": total_codes,
        }
    async def get_order_ui_status(
        self,
        db: AsyncSession,
        order_id: int,
        fallback_status: str | None = None,
    ) -> str:
        result = await db.execute(
            select(MarkingCode.status)
            .where(MarkingCode.order_id == order_id)
        )

        statuses = {
            (s.value if hasattr(s, "value") else str(s)).upper()
            for (s,) in result.fetchall()
        }

        if not statuses:
            return fallback_status or "PENDING"

        # 🟢 Все введены в оборот
        if statuses == {"IN_CIRCULATION"}:
            return "IN_CIRCULATION"

        # 🟢 ВСЕ АГРЕГИРОВАНЫ
        if statuses == {"AGGREGATED"}:
            return "AGGREGATED"

        # 🟡 Идет агрегация
        if "AGGREGATED" in statuses and "UNUSED" in statuses:
            return "AGGREGATING"

        return (fallback_status or "READY").upper()


order_service = OrderService()