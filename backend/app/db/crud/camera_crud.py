from typing import Any, List, Dict, Set, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, exists, func, join, text
from app.db.models.order import Order
from app.db.models.product import Product
from app.db.models.box import Box
from app.db.models.box_item import BoxItem
from app.db.models.marking_code import MarkingCode
from app.services.code_parse_service import extract_sntin
from app.core.logging import get_logger

logger = get_logger(__name__)

class CameraCRUD:
    """CRUD операции для работы с камерой и сканированием"""

    @staticmethod
    async def find_order_info(db: AsyncSession, codes: List[str]) -> Dict:
        """
        Ищет коды в БД и возвращает информацию о заказах
        """
        if not codes:
            return {
                "orders": [],
                "total_codes": 0,
                "found_codes": 0,
                "not_found_codes": []
            }

        # Извлекаем SGTIN из кодов
        sgtins = []
        code_to_sgtin = {}

        for code in codes:
            sgtin = extract_sntin(code)
            if sgtin:
                sgtins.append(sgtin)
                code_to_sgtin[code] = sgtin
            else:
                code_to_sgtin[code] = None

        if not sgtins:
            return {
                "orders": [],
                "total_codes": len(codes),
                "found_codes": 0,
                "not_found_codes": codes
            }

        # Запрос для получения информации о заказах по SGTIN
        stmt = (
            select(
                Order.id.label("order_id"),
                Order.name.label("order_name"),
                Order.external_order_id,
                Order.gtin,
                Order.qty,
                Product.name.label("product_name"),
                MarkingCode.sntin
            )
            .join(Product, Order.product_id == Product.id)
            .join(MarkingCode, Order.id == MarkingCode.order_id)
            .where(MarkingCode.sntin.in_(sgtins))
            .distinct()
        )

        result = await db.execute(stmt)
        rows = result.all()

        # Группируем по заказам
        orders_dict: Dict[int, Dict] = {}
        found_sgtins = set()

        for row in rows:
            order_id = row.order_id

            if order_id not in orders_dict:
                orders_dict[order_id] = {
                    "order_id": order_id,
                    "order_name": row.order_name,
                    "external_order_id": row.external_order_id,
                    "gtin": row.gtin,
                    "quantity": row.qty,
                    "product_name": row.product_name,
                    "codes": []
                }

            if row.sntin not in orders_dict[order_id]["codes"]:
                orders_dict[order_id]["codes"].append(row.sntin)

            found_sgtins.add(row.sntin)

        # Подсчитываем количество найденных кодов
        for order_info in orders_dict.values():
            order_info["codes"] = list(set(order_info["codes"]))

        # Определяем какие коды не найдены
        not_found_codes = []
        for code, sgtin in code_to_sgtin.items():
            if not sgtin or sgtin not in found_sgtins:
                not_found_codes.append(code)

        return {
            "orders": list(orders_dict.values()),
            "total_codes": len(codes),
            "found_codes": len(codes) - len(not_found_codes),
            "not_found_codes": not_found_codes
        }

    @staticmethod
    async def find_order_id_by_codes(db: AsyncSession, codes: List[str]) -> Dict:
        """
        Проверяет, что все коды принадлежат одному заказу, и возвращает этот order_id.
        """
        if not codes:
            return {
                "found": False,
                "order_id": None,
                "found_codes": 0,
                "not_found_codes": []
            }

        # Извлекаем SGTIN из кодов
        sgtin_to_codes = {}
        invalid_codes = []

        for code in codes:
            sgtin = extract_sntin(code)
            if sgtin:
                if sgtin not in sgtin_to_codes:
                    sgtin_to_codes[sgtin] = []
                sgtin_to_codes[sgtin].append(code)
            else:
                invalid_codes.append(code)

        valid_sgtins = list(sgtin_to_codes.keys())

        if not valid_sgtins:
            return {
                "found": False,
                "order_id": None,
                "found_codes": 0,
                "not_found_codes": codes
            }

        # Находим order_id для каждого SGTIN
        stmt = (
            select(
                MarkingCode.sntin,
                MarkingCode.order_id
            )
            .where(MarkingCode.sntin.in_(valid_sgtins))
            .distinct()
        )

        result = await db.execute(stmt)
        rows = result.all()

        # Группируем order_id по SGTIN
        sgtin_to_order_ids = {}
        for sgtin, order_id in rows:
            if sgtin not in sgtin_to_order_ids:
                sgtin_to_order_ids[sgtin] = []
            sgtin_to_order_ids[sgtin].append(order_id)

        # Проверяем, что ВСЕ SGTIN имеют одинаковый order_id
        common_order_ids = None

        for sgtin in valid_sgtins:
            if sgtin not in sgtin_to_order_ids:
                invalid_codes.extend(sgtin_to_codes[sgtin])
                continue

            order_ids_for_sgtin = sgtin_to_order_ids[sgtin]

            if len(order_ids_for_sgtin) > 1:
                logger.warning(f"SGTIN {sgtin} привязан к нескольким заказам: {order_ids_for_sgtin}")
                invalid_codes.extend(sgtin_to_codes[sgtin])
                continue

            if common_order_ids is None:
                common_order_ids = set(order_ids_for_sgtin)
            else:
                common_order_ids = common_order_ids.intersection(set(order_ids_for_sgtin))

        if not common_order_ids:
            return {
                "found": False,
                "order_id": None,
                "found_codes": 0,
                "not_found_codes": codes
            }

        if len(common_order_ids) > 1:
            logger.error(f"Найдено несколько возможных order_id: {common_order_ids}")
            return {
                "found": False,
                "order_id": None,
                "found_codes": len(valid_sgtins) - len(invalid_codes),
                "not_found_codes": invalid_codes
            }

        common_order_id = list(common_order_ids)[0]

        # Определяем какие коды валидны
        found_codes_list = []
        not_found_codes_list = invalid_codes.copy()

        for sgtin in valid_sgtins:
            if sgtin in sgtin_to_order_ids:
                order_id_for_sgtin = sgtin_to_order_ids[sgtin][0]
                if order_id_for_sgtin == common_order_id:
                    found_codes_list.extend(sgtin_to_codes[sgtin])
                else:
                    not_found_codes_list.extend(sgtin_to_codes[sgtin])
            else:
                not_found_codes_list.extend(sgtin_to_codes[sgtin])

        # Получаем информацию о заказе
        order_info_stmt = (
            select(
                Order.id,
                Order.external_order_id,
                Order.gtin,
                Order.qty,
                Product.name.label("product_name")
            )
            .join(Product, Order.product_id == Product.id)
            .where(Order.id == common_order_id)
        )

        order_info_result = await db.execute(order_info_stmt)
        order_info = order_info_result.first()

        result_data = {
            "found": True,
            "order_id": common_order_id,
            "found_codes": len(found_codes_list),
            "not_found_codes": not_found_codes_list
        }

        if order_info:
            result_data["order_info"] = {
                "external_order_id": order_info.external_order_id,
                "gtin": order_info.gtin,
                "product_name": order_info.product_name,
                "quantity": order_info.qty
            }

        logger.info(f"Найден общий order_id {common_order_id} для {len(found_codes_list)} кодов")

        return result_data

    @staticmethod
    async def get_already_used_codes(db: AsyncSession, codes: List[str]) -> Set[str]:
        """
        Возвращает множество кодов, которые уже были использованы в предыдущих коробках
        """
        if not codes:
            return set()

        # Извлекаем SGTIN из кодов
        sgtins = []
        code_to_sgtin = {}

        for code in codes:
            sgtin = extract_sntin(code)
            if sgtin:
                sgtins.append(sgtin)
                code_to_sgtin[code] = sgtin
            else:
                code_to_sgtin[code] = None

        if not sgtins:
            return set()

        # Ищем коды, которые уже есть в box_items
        stmt = (
            select(MarkingCode.code_raw)
            .join(BoxItem, BoxItem.marking_code_id == MarkingCode.id)
            .where(MarkingCode.sntin.in_(sgtins))
            .distinct()
        )

        result = await db.execute(stmt)
        used_raw_codes = set(result.scalars().all())

        used_sgtins = set()
        if used_raw_codes:
            for raw_code in used_raw_codes:
                sgtin = extract_sntin(raw_code)
                if sgtin:
                    used_sgtins.add(sgtin)

        already_used = set()
        for code, sgtin in code_to_sgtin.items():
            if sgtin and sgtin in used_sgtins:
                already_used.add(code)

        return already_used

    @staticmethod
    async def check_existing_box_with_codes(db: AsyncSession, order_id: int, sgtins: List[str]) -> Optional[Dict]:
        """
        Проверяет, существует ли уже коробка с таким же набором SGTIN для заказа
        """
        from sqlalchemy import func

        stmt = (
            select(Box.id, Box.sscc, func.count(BoxItem.id).label('code_count'))
            .join(BoxItem, Box.id == BoxItem.box_id)
            .join(MarkingCode, BoxItem.marking_code_id == MarkingCode.id)
            .where(
                Box.order_id == order_id,
                MarkingCode.sntin.in_(sgtins)
            )
            .group_by(Box.id, Box.sscc)
            .having(func.count(BoxItem.id) == len(sgtins))
        )

        result = await db.execute(stmt)
        existing_boxes = result.all()

        if existing_boxes:
            for box_row in existing_boxes:
                box_id = box_row[0]
                sscc = box_row[1]
                code_count = box_row[2]

                if code_count == len(sgtins):
                    box_code_count_stmt = select(func.count(BoxItem.id)).where(BoxItem.box_id == box_id)
                    box_code_count_result = await db.execute(box_code_count_stmt)
                    total_codes_in_box = box_code_count_result.scalar()

                    if total_codes_in_box and total_codes_in_box == len(sgtins):
                        return {
                            "box_id": box_id,
                            "sscc": sscc,
                            "code_count": total_codes_in_box
                        }

        return None

    @staticmethod
    async def get_boxes_by_order(db: AsyncSession, order_id: int) -> List[Box]:
        """Получает все коробки для указанного заказа"""
        from app.db.models import Box

        query = select(Box).where(Box.order_id == order_id).order_by(Box.id.desc())
        result = await db.execute(query)
        boxes = result.scalars().all()
        return list(boxes)  # Преобразуем Sequence в List

    @staticmethod
    async def get_box_codes(db: AsyncSession, box_id: int) -> List[str]:
        """Получает все коды для указанной коробки через BoxItem -> MarkingCode"""
        from app.db.models import BoxItem, MarkingCode
        from sqlalchemy.orm import joinedload

        query = (
            select(MarkingCode.code_raw)
            .join(BoxItem, MarkingCode.id == BoxItem.marking_code_id)
            .where(BoxItem.box_id == box_id)
        )

        result = await db.execute(query)
        codes = [row[0] for row in result.fetchall()]
        return codes

    @staticmethod
    async def get_already_used_codes_excluding_current(
        db: AsyncSession,
        codes: List[str],
        current_order_id: int
    ) -> Set[str]:
        """
        Находит уже использованные коды ИСКЛЮЧАЯ коды из текущего заказа

        Это критически важно для сценария 5+4+1:
        - Коды из первых двух коробок (того же заказа) НЕ считаются использованными
        - Только коды из ДРУГИХ заказов считаются использованными
        """
        from sqlalchemy import text

        if not codes:
            return set()

        # Преобразуем коды в список для SQL
        codes_list = codes

        query = text("""
            SELECT DISTINCT mc.code_raw
            FROM marking_codes mc
            JOIN box_items bi ON mc.id = bi.marking_code_id
            JOIN boxes b ON bi.box_id = b.id
            WHERE mc.code_raw = ANY(:codes)
            AND b.order_id != :current_order_id
        """)

        result = await db.execute(query, {"codes": codes_list, "current_order_id": current_order_id})
        used_codes = {row[0] for row in result.fetchall()}

        return used_codes

    @staticmethod
    async def find_box_with_exact_codes(self, db: AsyncSession, codes: List[str], order_id: int) -> Optional[Dict[str, Any]]:
        """
        Ищет коробку с ТОЧНО ТАКИМИ ЖЕ кодами
        """
        if not codes:
            return None

        codes_count = len(codes)

        # Безопасный способ с параметризацией
        # Создаем массив параметров для IN
        params = {}
        placeholders = []

        for i, code in enumerate(codes):
            param_name = f"code_{i}"
            params[param_name] = code
            placeholders.append(f":{param_name}")

        in_clause = ", ".join(placeholders)

        query = text(f"""
            WITH box_code_counts AS (
                SELECT
                    b.id as box_id,
                    b.sscc,
                    b.order_id,
                    COUNT(mc.code_raw) as matched_codes,
                    COUNT(*) as total_codes_in_box
                FROM boxes b
                JOIN box_items bi ON b.id = bi.box_id
                JOIN marking_codes mc ON bi.marking_code_id = mc.id
                WHERE b.order_id = :order_id
                AND mc.code_raw IN ({in_clause})
                GROUP BY b.id, b.sscc, b.order_id
            )
            SELECT box_id, sscc, order_id, matched_codes, total_codes_in_box
            FROM box_code_counts
            WHERE matched_codes = :codes_count
            AND total_codes_in_box = :codes_count
            LIMIT 1
        """)

        params['order_id'] = order_id
        params['codes_count'] = codes_count

        try:
            result = await db.execute(query, params)
            row = result.fetchone()

            if row:
                return {
                    "box_id": row[0],
                    "sscc": row[1],
                    "order_id": row[2],
                    "matched_codes": row[3],
                    "total_codes": row[4]
                }
        except Exception as e:
            logger.error(f"❌ Ошибка при поиске коробки с точными кодами: {e}")
            # В случае ошибки возвращаем None и продолжаем

        return None

    @staticmethod
    async def find_box_with_codes(db: AsyncSession, codes: List[str]) -> Optional[Any]:
        """Находит коробку, содержащую все указанные коды"""
        from sqlalchemy import text

        codes_str = ",".join([f"'{code}'" for code in codes])

        query = text(f"""
            SELECT b.id as box_id, b.sscc, b.order_id, COUNT(bc.code) as matched_codes
            FROM boxes b
            JOIN box_codes bc ON b.id = bc.box_id
            WHERE bc.code IN ({codes_str})
            GROUP BY b.id, b.sscc, b.order_id
            HAVING COUNT(bc.code) = {len(codes)}
            LIMIT 1
        """)

        result = await db.execute(query)
        row = result.fetchone()

        if row:
            return {
                "id": row[0],
                "sscc": row[1],
                "order_id": row[2],
                "matched_codes": row[3]
            }

        return None

# Создаем экземпляр для удобного импорта
camera_crud = CameraCRUD()