import hashlib
import json
from typing import List, Dict, Any, Optional
from fastapi import HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from app.workers.locks import acquire_cache_lock, release_cache_lock
from app.db.crud.camera_crud import camera_crud
from app.db.crud.box_crud import box_crud
from app.services.aggregation_service import aggregation_service
from app.services.barcode_service import barcode_service
from app.api.v1.dependencies import (
    set_cached_data,
    get_camera_last_scan,
    cache_camera_scan,
    release_cache_lock
)
from app.workers.cache import Cache
from app.core.logging import get_logger
from datetime import datetime

logger = get_logger(__name__)

class CameraService:
    """Сервис для работы с камерой и сканированием"""

    def __init__(self, db: AsyncSession, cache: Cache):
        self.db = db
        self.cache = cache

    async def scan_codes(self, codes: List[str], device_id: str) -> Dict[str, Any]:
        """
        Основная функция сканирования кодов
        """
        logger.info(f"📦 Получено {len(codes)} кодов от устройства {device_id}")

        # Получаем информацию о заказах
        result = await camera_crud.find_order_info(self.db, codes)

        # Кэшируем результат с использованием зависимости
        await cache_camera_scan(device_id, result, self.cache)

        return result

    async def scan_and_aggregate(
        self,
        codes: List[str],
        device_id: str,
        background_tasks: BackgroundTasks
    ) -> Dict[str, Any]:
        """
        Идемпотентное сканирование кодов и создание агрегации
        """
        if not codes:
            raise HTTPException(status_code=400, detail="Список кодов пуст")

        logger.info(f"📦 Получены КМ с устройства {device_id}, количество: {len(codes)}")

        # 1️⃣ Определяем заказ
        order_id_result = await camera_crud.find_order_id_by_codes(self.db, codes)

        if not order_id_result["found"]:
            raise HTTPException(
                status_code=400,
                detail=self._format_validation_error(order_id_result)
            )

        order_id = order_id_result["order_id"]
        logger.info(f"✅ Все коды принадлежат заказу ID: {order_id}")

        # 2️⃣ Lock для идемпотентности
        sorted_codes = sorted(codes)
        codes_hash = hashlib.md5(json.dumps(sorted_codes).encode()).hexdigest()
        lock_key = f"aggregation:{device_id}:{order_id}:{codes_hash}"

        await acquire_cache_lock(lock_key, self.cache, ttl=30)

        try:
            # 3️⃣ Ищем существующую коробку с ТАКИМИ ЖЕ кодами
            existing_box = await self._find_existing_box_with_exact_codes(codes, order_id)
            if existing_box:
                logger.warning(f"⚠️ Коробка {existing_box['box_id']} уже существует")
                await release_cache_lock(lock_key, self.cache)
                return self._format_existing_box_response(
                    existing_box, order_id_result, codes
                )

            # 4️⃣ Фильтруем коды, которые уже использованы в ДРУГИХ заказах
            already_used_codes = await camera_crud.get_already_used_codes_excluding_current(
                self.db, codes, order_id
            )

            valid_codes = [code for code in codes if code not in already_used_codes]

            if not valid_codes:
                logger.warning(f"⚠️ Все коды уже использованы в других заказах")
                await release_cache_lock(lock_key, self.cache)
                return {
                    "success": True,
                    "box_id": 0,
                    "sscc_code": "",
                    "order_id": order_id,
                    "total_codes_scanned": len(codes),
                    "found_codes": order_id_result["found_codes"],
                    "not_found_codes": order_id_result["not_found_codes"],
                    "warning": "Все коды уже были использованы в других заказах",
                    "print_status": "already_exists",
                    "message": "Коды уже были использованы ранее"
                }

            # 5️⃣ Создаём новую коробку
            try:
                box = await aggregation_service.create_box(
                    self.db, order_id, valid_codes
                )

                box_id = getattr(box, "id")
                sscc_code = getattr(box, "sscc")

                logger.info(f"✅ Создана новая коробка {box_id} с SSCC: {sscc_code}")

            except ValueError as e:
                logger.error(f"❌ Ошибка валидации: {e}")
                raise HTTPException(status_code=400, detail=str(e))
            except Exception as e:
                logger.error(f"❌ Ошибка при создании коробки: {e}")
                raise HTTPException(status_code=500, detail=f"Ошибка создания коробки: {str(e)}")

            # 6️⃣ Фоновые задачи
            await self._start_background_tasks(
                box_id,
                sscc_code,
                device_id,
                order_id,
                background_tasks
            )

            response = self._format_success_response(
                box_id,
                sscc_code,
                order_id,
                order_id_result,
                valid_codes
            )

            if already_used_codes:
                response["warning"] = f"Пропущено {len(already_used_codes)} уже использованных кодов в других заказах"

            return response

        except HTTPException:
            await release_cache_lock(lock_key, self.cache)
            raise
        except Exception as e:
            logger.error(f"❌ Критическая ошибка: {e}")
            await release_cache_lock(lock_key, self.cache)
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            try:
                await release_cache_lock(lock_key, self.cache)
            except Exception as e:
                logger.error(f"❌ Ошибка при снятии lock: {e}")

    async def _find_existing_box_with_exact_codes(
        self,
        codes: List[str],
        order_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Ищет существующую коробку с ТОЧНО ТАКИМИ ЖЕ кодами
        (альтернативная реализация через Python)
        """
        try:
            # Получаем все коробки заказа
            boxes = await camera_crud.get_boxes_by_order(self.db, order_id)

            # Преобразуем в множество для быстрого сравнения
            target_codes_set = set(codes)

            for box in boxes:
                # Получаем коды этой коробки
                box_codes = await camera_crud.get_box_codes(self.db, getattr(box, "id"))
                box_codes_set = set(box_codes)

                # Проверяем точное соответствие
                if box_codes_set == target_codes_set:
                    return {
                        "box_id": box.id,
                        "sscc": box.sscc,
                        "order_id": order_id,
                        "codes_count": len(box_codes)
                    }

            return None

        except Exception as e:
            logger.error(f"❌ Ошибка при поиске существующей коробки: {e}")
            return None

    async def get_last_scan(self, device_id: str) -> Optional[Dict[str, Any]]:
        """
        Получение последнего результата сканирования
        """
        return await get_camera_last_scan(device_id, self.cache)

    async def check_duplicate_codes(self, codes: List[str]) -> Dict[str, Any]:
        """
        Проверяет, какие коды уже были использованы в предыдущих коробках
        """
        already_used_codes = await camera_crud.get_already_used_codes(self.db, codes)

        return {
            "total_codes": len(codes),
            "already_used": list(already_used_codes),
            "already_used_count": len(already_used_codes),
            "new_codes": [code for code in codes if code not in already_used_codes],
            "new_codes_count": len(codes) - len(already_used_codes)
        }

    async def retry_print(self, box_id: int, background_tasks: BackgroundTasks) -> Dict[str, Any]:
        """
        Повторная печать SSCC-кода для коробки
        """
        box = await box_crud.get_box_with_sscc(self.db, box_id)

        if not box:
            raise HTTPException(status_code=404, detail=f"Коробка {box_id} не найдена")

        background_tasks.add_task(
            barcode_service.print_sscc_label_task,
            box_id,
            getattr(box, "sscc"),
            "manual_retry",
            getattr(box, "order_id")
        )

        # Кэшируем факт повторной печати
        await set_cached_data(
            f"print_retry:{box_id}:{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            {"box_id": box_id, "sscc": box.sscc, "timestamp": datetime.now().isoformat()},
            expire=86400,  # 24 часа
            cache=self.cache
        )

        return {
            "success": True,
            "message": "Задание на повторную печать SSCC отправлено",
            "box_id": box_id,
            "sscc_code": box.sscc
        }

    # Вспомогательные методы (без изменений)
    def _format_validation_error(self, order_id_result: Dict) -> str:
        """Форматирует сообщение об ошибке валидации"""
        not_found_count = len(order_id_result["not_found_codes"])
        found_count = order_id_result["found_codes"]

        error_msg = f"Не удалось создать агрегацию. "
        error_msg += f"Найдено кодов: {found_count}, не найдено: {not_found_count}. "

        if not_found_count > 0:
            error_msg += f"Не найдены коды: {', '.join(order_id_result['not_found_codes'][:3])}"
            if not_found_count > 3:
                error_msg += f" и еще {not_found_count - 3}..."

        return error_msg

    def _format_existing_box_response(
        self,
        existing_box: Dict,
        order_id_result: Dict,
        codes: List[str]
    ) -> Dict[str, Any]:
        """Форматирует ответ для существующей коробки"""
        return {
            "success": True,
            "box_id": existing_box["box_id"],
            "sscc_code": existing_box["sscc"],
            "order_id": order_id_result["order_id"],
            "total_codes_scanned": len(codes),
            "found_codes": order_id_result["found_codes"],
            "not_found_codes": order_id_result["not_found_codes"],
            "warning": "Коробка уже была создана ранее",
            "print_status": "already_exists",
            "message": "Коробка с такими кодами уже существует"
        }

    def _format_success_response(
        self,
        box_id: int,
        sscc_code: str,
        order_id: int,
        order_id_result: Dict,
        codes: List[str]
    ) -> Dict[str, Any]:
        """Форматирует успешный ответ"""
        not_found_count = len(order_id_result["not_found_codes"])

        return {
            "success": True,
            "box_id": box_id,
            "sscc_code": sscc_code,
            "order_id": order_id,
            "total_codes_scanned": len(codes),
            "found_codes": order_id_result["found_codes"],
            "not_found_codes": order_id_result["not_found_codes"],
            "warning": f"Не найдено {not_found_count} кодов" if not_found_count > 0 else None,
            "print_status": "sent_to_printer",
            "message": "Коробка успешно создана и отправлена на печать"
        }

    async def _start_background_tasks(
        self,
        box_id: int,
        sscc_code: str,
        device_id: str,
        order_id: int,
        background_tasks: BackgroundTasks
    ):
        """Запускает фоновые задачи"""
        # Отчет
        from app.workers.tasks import send_apply_report
        send_apply_report(box_id)

        # Печать
        background_tasks.add_task(
            barcode_service.print_sscc_label_task,
            box_id,
            sscc_code,
            device_id,
            order_id
        )

# Фабрика для создания сервиса
def get_camera_service(db: AsyncSession, cache: Cache) -> CameraService:
    return CameraService(db, cache)