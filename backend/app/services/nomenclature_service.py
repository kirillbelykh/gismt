"""Service for GTIN lookup in nomenclature Excel file"""
import os
import re
from typing import Optional, Tuple, Dict, Any
import pandas as pd
from app.core.logging import get_logger

logger = get_logger(__name__)


class NomenclatureService:
    """Service for looking up GTIN in nomenclature Excel file"""

    def __init__(self):
        # Путь к файлу номенклатуры
        default_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "data",
            "nomenclature.xlsx"
        )
        self.nomenclature_path = os.getenv("NOMENCLATURE_PATH", default_path)
        self._df: Optional[pd.DataFrame] = None

    def _load_nomenclature(self) -> pd.DataFrame:
        """Load nomenclature Excel file"""
        if self._df is not None:
            return self._df

        if not os.path.exists(self.nomenclature_path):
            logger.warning(f"Файл номенклатуры не найден: {self.nomenclature_path}")
            logger.info(f"Создайте файл или укажите путь через переменную окружения NOMENCLATURE_PATH")
            return pd.DataFrame()

        try:
            self._df = pd.read_excel(self.nomenclature_path)
            logger.info(f"Номенклатура загружена: {len(self._df)} записей из {self.nomenclature_path}")
            return self._df
        except Exception as e:
            logger.error(f"Ошибка загрузки номенклатуры: {e}")
            return pd.DataFrame()

    def load_nomenclature_data(self) -> pd.DataFrame:
        """
        Загружает данные из Excel-файла номенклатуры
        """
        try:
            if not os.path.exists(self.nomenclature_path):
                logger.error(f"Файл номенклатуры не найден: {self.nomenclature_path}")
                columns = [
                    'GTIN',
                    'Полное наименование товара',
                    'Упрощенно',
                    'Размер',
                    'Количество единиц употребления в потребительской упаковке',
                    'Цвет',
                    'венчик'
                ]
                return pd.DataFrame(columns=columns)

            df = pd.read_excel(self.nomenclature_path)

            required_cols = [
                'GTIN',
                'Полное наименование товара',
                'Упрощенно',
                'Размер',
                'Количество единиц употребления в потребительской упаковке',
                'Цвет',
                'венчик'
            ]

            for col in required_cols:
                if col not in df.columns:
                    df[col] = ""
                    logger.warning(f"Колонка '{col}' не найдена в файле, добавлена пустая колонка")

            logger.info(f"Данные номенклатуры загружены, строк: {len(df)}")
            return df

        except Exception as e:
            logger.error(f"Ошибка загрузки файла номенклатуры: {e}")
            return pd.DataFrame()

    def find_product_by_gtin(self, gtin: str) -> Optional[Dict[str, Any]]:
        """
        Поиск товара по GTIN в номенклатуре

        Args:
            gtin: GTIN код

        Returns:
            Словарь с информацией о товаре или None
        """
        try:
            if not gtin or not gtin.strip():
                return None

            gtin_clean = gtin.strip()
            if len(gtin_clean) == 13:
                gtin_clean = "0" + gtin_clean
            elif len(gtin_clean) < 13:
                gtin_clean = gtin_clean.zfill(14)

            df = self.load_nomenclature_data()
            if df.empty:
                return None

            df['GTIN'] = df['GTIN'].astype(str).str.strip()
            df['GTIN'] = df['GTIN'].str.replace(r'\D', '', regex=True)
            df['GTIN'] = df['GTIN'].apply(lambda x: x.zfill(14) if x else x)

            search_gtin = gtin_clean.zfill(14)
            match = df[df['GTIN'] == search_gtin]

            if not match.empty:
                row = match.iloc[0]
                return {
                    'gtin': search_gtin,
                    'full_name': str(row.get('Полное наименование товара', '')).strip(),
                    'simpl_name': str(row.get('Упрощенно', '')).strip(),
                    'units_per_pack': str(row.get('Количество единиц употребления в потребительской упаковке', '')).strip(),
                    'color': str(row.get('Цвет', '')).strip(),
                    'venchik': str(row.get('венчик', '')).strip(),
                    'size': str(row.get('Размер', '')).strip()
                }

            return None

        except Exception as e:
            logger.error(f"Ошибка поиска товара по GTIN {gtin}: {e}")
            return None

    def find_product_by_parameters(
        self,
        simpl_name: str,
        size: str,
        units_per_pack: str,
        color: Optional[str] = None,
        venchik: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Поиск товара по параметрам в номенклатуре

        Args:
            simpl_name: Упрощённое название товара
            size: Размер
            units_per_pack: Количество единиц в упаковке
            color: Цвет (опционально)
            venchik: Венчик (опционально)

        Returns:
            Словарь с информацией о товаре или None
        """
        try:
            df = self.load_nomenclature_data()
            if df.empty:
                return None

            simpl = simpl_name.strip().lower()
            size_input = str(size).strip().lower()
            units_str = str(units_per_pack).strip()
            color_l = color.strip().lower() if color else None
            venchik_l = venchik.strip().lower() if venchik else None

            required_cols = [
                'GTIN',
                'Полное наименование товара',
                'Упрощенно',
                'Размер',
                'Количество единиц употребления в потребительской упаковке',
                'Цвет',
                'венчик'
            ]

            for col in required_cols:
                if col not in df.columns:
                    df[col] = ""

            def extract_size_from_table(size_str):
                if not isinstance(size_str, str):
                    return ""

                size_str_lower = size_str.lower().strip()
                match = re.search(r'\(([A-Z]+)\)', size_str.upper())
                if match:
                    return match.group(1).lower()

                if "сверхбольшой" in size_str_lower or "xl" in size_str_lower:
                    return "xl"
                elif "большой" in size_str_lower or "l" in size_str_lower:
                    return "l"
                elif "средний" in size_str_lower or "m" in size_str_lower:
                    return "m"
                elif "маленький" in size_str_lower or "s" in size_str_lower:
                    return "s"

                num_match = re.search(r'(\d+[.,]?\d*)', size_str_lower)
                if num_match:
                    num_size = num_match.group(1).replace(',', '.')
                    return num_size

                return size_str_lower

            df['normalized_size'] = df['Размер'].apply(extract_size_from_table)

            def normalize_input_size(size_str):
                size_lower = size_str.lower().strip()
                size_mapping = {
                    's': 's', 'маленький': 's',
                    'm': 'm', 'средний': 'm',
                    'l': 'l', 'большой': 'l',
                    'xl': 'xl', 'сверхбольшой': 'xl'
                }

                if size_lower in size_mapping:
                    return size_mapping[size_lower]

                num_match = re.search(r'(\d+[.,]?\d*)', size_lower)
                if num_match:
                    num_size = num_match.group(1).replace(',', '.')
                    return num_size

                return size_lower

            normalized_input_size = normalize_input_size(size_input)

            cond = (
                df['Упрощенно'].astype(str).str.strip().str.lower() == simpl
            ) & (
                df['normalized_size'] == normalized_input_size
            ) & (
                df['Количество единиц употребления в потребительской упаковке'].astype(str).str.strip() == units_str
            )

            if venchik_l:
                cond &= df['венчик'].astype(str).str.strip().str.lower() == venchik_l
            if color_l:
                cond &= df['Цвет'].astype(str).str.strip().str.lower() == color_l

            matches = df[cond]
            if not matches.empty:
                row = matches.iloc[0]
                return {
                    'gtin': str(row['GTIN']).strip(),
                    'full_name': str(row['Полное наименование товара']).strip(),
                    'simpl_name': simpl_name
                }

            cond2 = (
                df['Упрощенно'].astype(str).str.strip().str.lower().str.contains(simpl, na=False)
            ) & (
                df['normalized_size'] == normalized_input_size
            ) & (
                df['Количество единиц употребления в потребительской упаковке'].astype(str).str.strip() == units_str
            )

            if venchik_l:
                cond2 &= df['венчик'].astype(str).str.strip().str.lower() == venchik_l
            if color_l:
                cond2 &= df['Цвет'].astype(str).str.strip().str.lower() == color_l

            matches2 = df[cond2]
            if not matches2.empty:
                row = matches2.iloc[0]
                return {
                    'gtin': str(row['GTIN']).strip(),
                    'full_name': str(row['Полное наименование товара']).strip(),
                    'simpl_name': simpl_name
                }

            logger.debug(f"Не найдено совпадений для: simpl={simpl}, size={normalized_input_size}, units={units_str}")
            return None

        except Exception as e:
            logger.exception("Ошибка в поиске товара по параметрам")
            return None

    def lookup_gtin(
        self,
        simpl_name: str,
        size: str,
        units_per_pack: str,
        color: Optional[str] = None,
        venchik: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Поиск GTIN и полного наименования по заданным полям.
        (Совместимость со старым кодом)
        """
        result = self.find_product_by_parameters(simpl_name, size, units_per_pack, color, venchik)
        if result:
            return result['gtin'], result['full_name']
        return None, None

    def lookup_by_gtin(self, gtin: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Поиск товара по GTIN.
        (Совместимость со старым кодом)

        Args:
            gtin: GTIN код

        Returns:
            Кортеж (Полное наименование, Упрощенное имя) или (None, None), если не найдено
        """
        result = self.find_product_by_gtin(gtin)
        if result:
            return result['full_name'], result['simpl_name']
        return None, None

    def find_product_info(
        self,
        gtin: Optional[str] = None,
        simpl_name: Optional[str] = None,
        size: Optional[str] = None,
        units_per_pack: Optional[str] = None,
        color: Optional[str] = None,
        venchik: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Универсальный поиск товара с приоритетом по GTIN

        Returns:
            Словарь с информацией о товаре или None
        """
        if gtin and gtin.strip():
            product_info = self.find_product_by_gtin(gtin)
            if product_info:
                return product_info

        if simpl_name and size and units_per_pack and color and venchik:
            return self.find_product_by_parameters(simpl_name, size, units_per_pack, color, venchik)

        return None

    def reload(self):
        """Перезагрузить номенклатуру из файла"""
        self._df = None
        self._load_nomenclature()


nomenclature_service = NomenclatureService()