from typing import Dict, List, Set, Tuple, Optional
from fastapi import Request
from app.schemas.order_web import OrderCreateForm
from app.core.logging import get_logger
from app.services.code_parse_service import extract_sntin

logger = get_logger(__name__)


class FormValidationService:
    """Сервис для валидации и обработки данных форм"""

    @staticmethod
    async def parse_form_data(request: Request) -> Dict:
        """Парсинг данных формы"""
        form_data = await request.form()
        return dict(form_data)

    @staticmethod
    def validate_form_data(form_data: Dict) -> Tuple[Optional[OrderCreateForm], Optional[str]]:
        """Валидация данных формы"""
        try:
            # Конвертируем типы
            converted_data = {}
            for key, value in form_data.items():
                if key in ['quantity', 'units_per_pack'] and value:
                    try:
                        converted_data[key] = int(value)
                    except ValueError:
                        return None, f"Некорректное значение для поля '{key}': {value}"
                elif key in ['prod_date', 'exp_date'] and value:
                    converted_data[key] = value  # Pydantic сам преобразует строку в date
                else:
                    converted_data[key] = value

            order_form = OrderCreateForm(**converted_data)
            return order_form, None

        except ValueError as e:
            logger.warning(f"Ошибка валидации формы: {e}")
            return None, str(e)
        except Exception as e:
            logger.error(f"Непредвиденная ошибка при валидации: {e}")
            return None, "Внутренняя ошибка валидации данных"

class ValidationService:
    """Сервис для валидации кодов"""

    @staticmethod
    async def extract_sgtins(codes: List[str]) -> List[str]:
        """Извлекает SGTIN из списка кодов"""
        sgtins = []
        for code in codes:
            sgtin = extract_sntin(code)
            if sgtin:
                sgtins.append(sgtin)
        return sgtins

    @staticmethod
    async def filter_used_codes(codes: List[str], already_used_codes: Set[str]) -> List[str]:
        """Фильтрует уже использованные коды"""
        if not already_used_codes:
            return codes

        valid_codes = [code for code in codes if code not in already_used_codes]

        if len(valid_codes) != len(codes):
            from app.core.logging import get_logger
            logger = get_logger(__name__)
            logger.info(f"Используем только {len(valid_codes)} новых кодов из {len(codes)}")

        return valid_codes

validation_service = ValidationService()