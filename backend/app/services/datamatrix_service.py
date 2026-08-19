import io
import tempfile
import os
import shutil
from typing import List
from fastapi.responses import Response
from fastapi import HTTPException
from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from pystrich.datamatrix import DataMatrixEncoder
import logging
from reportlab.lib.utils import ImageReader

logger = logging.getLogger(__name__)

class DataMatrixPDFGenerator:
    def __init__(self):
        self.temp_dir = tempfile.mkdtemp(prefix="datamatrix_")
        logger.debug(f"Создана временная директория: {self.temp_dir}")

    def __del__(self):
        """Очистка временных файлов при уничтожении объекта"""
        self.cleanup()

    def generate_datamatrix_png(self, code: str, size_px: int = 200) -> io.BytesIO:
        """
        Генерация DataMatrix в PNG (in-memory, быстро).
        Возвращает BytesIO.
        """
        try:
            encoder = DataMatrixEncoder(code)

            # pyStrich отдаёт PNG bytes напрямую
            png_bytes = encoder.get_imagedata()

            buffer = io.BytesIO(png_bytes)
            buffer.seek(0)
            return buffer

        except Exception as e:
            logger.error(f"Ошибка генерации DataMatrix для кода: {e}")
            return self._create_error_png(code, size_px)

    def _create_placeholder_png(self, code: str, size_px: int) -> io.BytesIO:
        """Создает заглушку если pyStrich не установлен"""
        img = Image.new('RGB', (size_px, size_px), color='white')
        draw = ImageDraw.Draw(img)

        # Рамка
        draw.rectangle([0, 0, size_px-1, size_px-1], outline='black', width=2)

        # Текст
        try:
            font_size = max(10, size_px // 15)
            try:
                font = ImageFont.truetype("Arial", font_size)
            except:
                font = ImageFont.load_default()

            text = "NO\nPYSTRICH"
            bbox = draw.multiline_textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            x = (size_px - text_width) // 2
            y = (size_px - text_height) // 2
            draw.multiline_text((x, y), text, fill='black', font=font, align='center')
        except Exception:
            # Простой текст если шрифт не доступен
            text = "NO PYSTRICH"
            x = size_px // 2 - 40
            y = size_px // 2 - 5
            draw.text((x, y), text, fill='black')

        # Сохраняем в буфер
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        return buffer

    def _create_error_png(self, code: str, size_px: int) -> io.BytesIO:
        """Создает изображение с ошибкой"""
        img = Image.new('RGB', (size_px, size_px), color='red')
        draw = ImageDraw.Draw(img)

        # Белый текст
        try:
            font_size = max(10, size_px // 15)
            try:
                font = ImageFont.truetype("Arial", font_size)
            except:
                font = ImageFont.load_default()

            text = "ERROR"
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            x = (size_px - text_width) // 2
            y = (size_px - text_height) // 2
            draw.text((x, y), text, fill='white', font=font)
        except:
            text = "ERROR"
            x = size_px // 2 - 20
            y = size_px // 2 - 5
            draw.text((x, y), text, fill='white')

        # Сохраняем в буфер
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        return buffer

    def create_minimal_pdf_response(
        self,
        codes: List[str],
        order_id: int,
        order_name: str = ""
    ) -> Response:
        """
        Генерирует PDF:
        - 1 DataMatrix = 1 страница
        - Размер страницы: 30x20 мм (этикетка)
        """
        if not codes:
            raise HTTPException(status_code=400, detail="Нет кодов для генерации PDF")

        logger.info(
            f"Создание PDF этикеток 30x20 мм: {len(codes)} кодов, заказ {order_id}"
        )

        buffer = io.BytesIO()

        LABEL_W = 30 * mm
        LABEL_H = 20 * mm

        # ВАЖНО: ReportLab не поддерживает setCropBox, размер страницы фиксируем через setPageSize
        c = canvas.Canvas(buffer, pagesize=(LABEL_W, LABEL_H))
        c._pagesize = (LABEL_W, LABEL_H)
        # c._doc.setCropBox(0, 0, LABEL_W, LABEL_H)  # Удалено согласно инструкции

        for idx, code in enumerate(codes):
            if idx > 0:
                c.showPage()  # строго 1 код = 1 страница
                c.setPageSize((LABEL_W, LABEL_H))

            png_buffer = self.generate_datamatrix_png(code, size_px=800)
            image = ImageReader(png_buffer)

            MARGIN = 1 * mm
            DM_SIZE = 18 * mm  # 30x20 мм этикетка с отступами по 1 мм

            x = (LABEL_W - DM_SIZE) / 2
            y = (LABEL_H - DM_SIZE) / 2

            c.drawImage(
                image,
                x,
                y,
                width=DM_SIZE,
                height=DM_SIZE,
                preserveAspectRatio=True,
                mask="auto"
            )

        c.save()
        buffer.seek(0)

        return Response(
            content=buffer.getvalue(),
            media_type="application/pdf",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="order_{order_id}_datamatrix_30x20.pdf"'
                )
            }
        )

    def create_codes_csv_response(
        self,
        codes: List[str],
        order_id: int
    ) -> Response:
        """
        Создает CSV-файл со списком DataMatrix кодов.
        Формат:
        code
        XXXXX
        YYYYY
        """
        if not codes:
            raise HTTPException(status_code=400, detail="Нет кодов для CSV")

        csv_content = "\n".join(codes) + "\n"
        csv_bytes = csv_content.encode("utf-8")

        filename = f"order_{order_id}_datamatrix.csv"

        return Response(
            content=csv_bytes,
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )

    def cleanup(self):
        """Очистка временных файлов"""
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
            except Exception as e:
                logger.warning(f"Ошибка очистки временной директории: {e}")


# Создаем глобальный экземпляр генератора
datamatrix_generator = DataMatrixPDFGenerator()