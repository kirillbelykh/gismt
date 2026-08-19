"""Service for parsing marking codes and extracting SNTIN"""
import re
from typing import Optional
from app.core.logging import get_logger

logger = get_logger(__name__)

def extract_sntin(full_code: str) -> str:
    """
    Извлекает SNTIN из полного DataMatrix кода.
    SNTIN = '01' + GTIN (14 символов) + '21' + serial (13 символов) = 31 символов
    """
    try:
        # Очищаем код от лишних символов
        full_code = full_code.strip()

        # Проверяем минимальную длину
        if len(full_code) < 31:
            return full_code

        # Извлекаем первые 31 символов
        sntin = full_code[:31]


        # Проверяем структуру
        if sntin.startswith('01') and len(sntin) == 31 and sntin[16:18] == '21':
            # Декодируем специальные символы
            import urllib.parse
            decoded_sntin = urllib.parse.unquote(sntin)
            return sntin
        else:

            # Пытаемся найти SNTIN в строке по другим признакам
            # Ищем паттерн 01 + 14 цифр GTIN
            import re
            pattern = r'01(\d{14})'
            match = re.search(pattern, full_code)

            if match:
                gtin_part = match.group(0)  # "01" + 14 цифр = 16 символов
                # Берем следующие 15 символов ('21' + 13 для серийного номера)
                start_pos = match.end()
                serial_part = full_code[start_pos:start_pos+15]
                reconstructed_sntin = gtin_part + serial_part

                if len(reconstructed_sntin) == 31 and reconstructed_sntin[16:18] == '21':
                    return reconstructed_sntin

            # Если не нашли, возвращаем первые 31 символов
            return full_code[:31]

    except Exception as e:
        logger.error(f"Ошибка извлечения SNTIN из кода {full_code[:50]}...: {e}")
        # Возвращаем первые 31 символов как запасной вариант
        return full_code[:31] if len(full_code) >= 31 else full_code


def parse_gtin_from_code(code: str) -> Optional[str]:
    """
    Extract GTIN from marking code

    Args:
        code: Marking code (raw or SNTIN)

    Returns:
        GTIN string (14 digits) or None
    """
    # Extract SNTIN first
    sntin = extract_sntin(code)

    # GTIN is after "01" prefix, 14 digits
    match = re.search(r"01(\d{14})", sntin)
    if match:
        return match.group(1)

    return None


def parse_serial_from_code(code: str) -> Optional[str]:
    """
    Extract serial number from marking code

    Args:
        code: Marking code (raw or SNTIN)

    Returns:
        Serial number string or None
    """
    # Extract SNTIN first
    sntin = extract_sntin(code)

    # Serial is after "21" prefix
    match = re.search(r"21([\x20-\x7E]{1,20})", sntin)
    if match:
        return match.group(1)

    return None
