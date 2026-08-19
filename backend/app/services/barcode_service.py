import io
import os
import json
import tempfile
import subprocess
from typing import Optional, Dict, Any
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.colors import black, white
from reportlab.lib.units import mm
from app.core.logging import get_logger
from app.workers.cache import Cache
import barcode
from barcode.writer import ImageWriter
from PIL import Image

logger = get_logger(__name__)


class BarcodeService:
    """Сервис для работы со штрих-кодами и печатью"""

    @staticmethod
    def generate_sscc_barcode(sscc_code: str) -> bytes:
        """
        Генерирует SSCC штрих-код в формате GS1-128
        """
        try:
            gs1_data = f"{sscc_code}"
            code128_class = barcode.get_barcode_class('code128')

            options = {
                'module_height': 15.0,
                'module_width': 0.35,
                'font_size': 12,
                'text_distance': 5.0,
                'quiet_zone': 6.5,
                'background': 'white',
                'foreground': 'black',
                'write_text': True,
                'text': gs1_data,
            }

            barcode_obj = code128_class(gs1_data, writer=ImageWriter())

            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
                temp_path = temp_file.name

            with open(temp_path, 'wb') as f:
                barcode_obj.write(f, options=options)

            with open(temp_path, 'rb') as f:
                image_bytes = f.read()

            os.unlink(temp_path)

            logger.info(f"Сгенерирован SSCC штрих-код для: {sscc_code}")
            return image_bytes

        except Exception as e:
            logger.error(f"Ошибка генерации SSCC штрих-кода: {e}")
            raise

    @staticmethod
    def generate_simple_barcode(sscc_code: str) -> bytes:
        """
        Простая генерация штрих-кода SSCC в формате Code128
        """
        try:
            barcode_type = barcode.get_barcode_class('code128')
            data = f"(00){sscc_code}"
            code128 = barcode_type(data, writer=ImageWriter())

            options = {
                'module_height': 15.0,
                'module_width': 0.35,
                'font_size': 12,
                'text_distance': 5.0,
                'quiet_zone': 6.5,
                'write_text': True,
            }

            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
                temp_path = temp_file.name

            filename = code128.save(temp_path, options=options)

            with open(filename, 'rb') as f:
                image_bytes = f.read()

            os.unlink(filename)

            return image_bytes

        except Exception as e:
            logger.error(f"Ошибка в generate_simple_barcode: {e}")
            raise

    @staticmethod
    def create_sscc_barcode_pdf(sscc_code: str, box_id: int) -> bytes:
        """
        Создает PDF с SSCC штрих-кодом для печати
        """
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4

        c.setFillColor(white)
        c.rect(0, 0, width, height, fill=True, stroke=False)

        try:
            barcode_image_bytes = BarcodeService.generate_sscc_barcode(sscc_code)

            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
                temp_file.write(barcode_image_bytes)
                temp_path = temp_file.name


            img = Image.open(temp_path)
            img_width, img_height = img.size

            max_width = width - 40 * mm
            max_height = height - 80 * mm

            scale_factor = min(max_width / img_width, max_height / img_height)
            scaled_width = img_width * scale_factor
            scaled_height = img_height * scale_factor

            barcode_x = (width - scaled_width) / 2
            barcode_y = height - 60 * mm - scaled_height

            c.drawImage(temp_path, barcode_x, barcode_y,
                        width=scaled_width, height=scaled_height)

            os.unlink(temp_path)

        except Exception as e:
            logger.error(f"Ошибка вставки штрих-кода в PDF: {e}")
            c.setFont("Helvetica-Bold", 16)
            c.setFillColor(black)
            c.drawCentredString(width / 2, height - 100, f"SSCC: {sscc_code}")
            barcode_y = height - 120 * mm

        c.setFont("Helvetica-Bold", 24)
        c.setFillColor(black)

        formatted_sscc = ' '.join([sscc_code[i:i+4] for i in range(0, len(sscc_code), 4)])
        text_y = barcode_y - 25 * mm if 'barcode_y' in locals() else height - 150 * mm
        c.drawCentredString(width / 2, text_y, formatted_sscc)

        c.setFont("Helvetica", 12)
        c.setFillColorRGB(0.3, 0.3, 0.3)

        c.drawCentredString(width / 2, text_y - 15 * mm, f"BOX ID: {box_id}")
        c.drawCentredString(width / 2, text_y - 25 * mm,
                           f"PRINTED: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")

        c.setFont("Helvetica-Oblique", 10)
        c.setFillColorRGB(0.5, 0.5, 0.5)
        c.drawCentredString(width / 2, 20 * mm, "SSCC (Serial Shipping Container Code) - GS1 Standard")

        c.showPage()
        c.save()

        buffer.seek(0)
        return buffer.read()

    @staticmethod
    async def print_sscc_barcode_direct(box_id: int, sscc_code: str, device_id: str) -> bool:
        """
        Прямая печать штрих-кода на принтер
        """
        printer_name = "HP_LaserJet_400_MFP_M425dn__F17BD5_"

        try:
            logger.info(f"🖨️ Прямая печать штрих-кода {sscc_code} для коробки {box_id}")

            pdf_content = BarcodeService.create_sscc_barcode_pdf(sscc_code, box_id)

            with tempfile.NamedTemporaryFile(mode='wb', suffix='.pdf', delete=False) as f:
                f.write(pdf_content)
                pdf_file = f.name

            try:
                # Метод 1: lpr
                cmd_lpr = [
                    'lpr',
                    '-P', printer_name,
                    '-o', 'media=A4',
                    '-o', 'ColorModel=Gray',
                    pdf_file
                ]

                logger.info(f"Печать через lpr: {' '.join(cmd_lpr)}")
                result_lpr = subprocess.run(cmd_lpr, capture_output=True, text=True, timeout=30)

                if result_lpr.returncode == 0:
                    logger.info("✅ PDF успешно отправлен на печать через lpr")
                    os.unlink(pdf_file)
                    return True

                # Метод 2: lp
                cmd_lp = [
                    'lp',
                    '-d', printer_name,
                    '-o', 'media=A4',
                    pdf_file
                ]

                logger.info(f"Печать через lp: {' '.join(cmd_lp)}")
                result_lp = subprocess.run(cmd_lp, capture_output=True, text=True, timeout=30)

                if result_lp.returncode == 0:
                    logger.info("✅ PDF успешно отправлен на печать через lp")
                    os.unlink(pdf_file)
                    return True

                # Метод 3: Простой lpr
                cmd_simple = ['lpr', '-P', printer_name, pdf_file]
                logger.info(f"Печать через простой lpr: {' '.join(cmd_simple)}")
                result_simple = subprocess.run(cmd_simple, capture_output=True, text=True, timeout=30)

                if result_simple.returncode == 0:
                    logger.info("✅ PDF успешно отправлен на печать (простой lpr)")
                    os.unlink(pdf_file)
                    return True

                # Все методы не сработали
                error_msgs = []
                if result_lpr.stderr:
                    error_msgs.append(f"lpr: {result_lpr.stderr[:100]}")
                if result_lp.stderr:
                    error_msgs.append(f"lp: {result_lp.stderr[:100]}")
                if result_simple.stderr:
                    error_msgs.append(f"simple: {result_simple.stderr[:100]}")

                error_msg = "; ".join(error_msgs)
                logger.error(f"❌ Все методы печати не сработали: {error_msg}")

                # Сохраняем PDF для ручной печати
                save_dir = "/tmp/sscc_prints"
                os.makedirs(save_dir, exist_ok=True)
                save_file = f"{save_dir}/sscc_{box_id}_{sscc_code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

                with open(save_file, 'wb') as f:
                    f.write(pdf_content)

                logger.info(f"📁 PDF сохранен для ручной печати: {save_file}")
                logger.info(f"📋 Для ручной печати выполните:")
                logger.info(f"    open {save_file}  # для просмотра")
                logger.info(f"    lpr -P {printer_name} {save_file}  # для печати")

                return False

            finally:
                try:
                    if os.path.exists(pdf_file):
                        os.unlink(pdf_file)
                except:
                    pass

        except subprocess.TimeoutExpired:
            logger.error("⏱️ Таймаут при печати")
            return False
        except Exception as e:
            logger.error(f"❌ Общая ошибка при печати: {e}")
            return False

    @staticmethod
    async def print_sscc_label_task(box_id: int, sscc_code: str, device_id: str, order_id: Optional[int] = None):
        """
        Фоновая задача для печати ШТРИХ-КОДА SSCC
        """
        try:
            logger.info(f"🖨️ Запуск печати штрих-кода {sscc_code} для коробки {box_id}")

            success = await BarcodeService.print_sscc_barcode_direct(box_id, sscc_code, device_id)

            if success:
                logger.info(f"✅ Штрих-код {sscc_code} успешно отправлен на печать")
                await BarcodeService.save_print_log(box_id, sscc_code, True, "barcode_printed_successfully")
            else:
                logger.warning(f"⚠️ Штрих-код {sscc_code} НЕ отправлен автоматически")
                await BarcodeService.save_print_log(box_id, sscc_code, False, "print_failed_manual_required")

        except Exception as e:
            logger.error(f"❌ Критическая ошибка при печати: {e}")
            await BarcodeService.save_print_log(box_id, sscc_code, False, f"critical_error: {str(e)[:100]}")

    @staticmethod
    async def save_print_log(box_id: int, sscc_code: str, success: bool, message: str):
        """
        Сохраняет лог печати
        """
        try:
            log_entry = {
                "box_id": box_id,
                "sscc_code": sscc_code,
                "success": success,
                "message": message,
                "timestamp": datetime.now().isoformat(),
                "printer": "HP_LaserJet_400_MFP_M425dn__F17BD5_"
            }

            cache = Cache()
            log_key = f"print_log:{box_id}:{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            await cache.setex(log_key, 604800, json.dumps(log_entry))

            logger.info(f"📋 Лог печати сохранен: {log_key}")
        except Exception as e:
            logger.error(f"Ошибка сохранения лога печати: {e}")

    @staticmethod
    async def get_print_status(box_id: int, cache: Cache) -> Dict[str, Any]:
        """
        Получить статус печати для коробки
        """
        try:
            pattern = f"print_log:{box_id}:*"
            keys = await cache.keys(pattern)

            if not keys:
                return {"found": False, "message": "Логи печати не найдены"}

            keys.sort(reverse=True)
            last_key = keys[0]

            log_data = await cache.get(last_key)
            if log_data:
                log_entry = json.loads(log_data)
                return {
                    "found": True,
                    "box_id": box_id,
                    "success": log_entry["success"],
                    "message": log_entry["message"],
                    "timestamp": log_entry["timestamp"],
                    "printer": log_entry["printer"]
                }
            else:
                return {"found": False, "message": "Лог печати не найден"}

        except Exception as e:
            logger.error(f"Ошибка получения статуса печати: {e}")
            return {"found": False, "error": str(e)}

# Создаем экземпляр для удобного импорта
barcode_service = BarcodeService()