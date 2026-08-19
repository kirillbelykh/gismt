from typing import Dict, Any
from fastapi.templating import Jinja2Templates
from app.core.logging import get_logger

logger = get_logger(__name__)


class HTMLResponseService:
    """Сервис для генерации HTML ответов"""

    def __init__(self, templates: Jinja2Templates):
        self.templates = templates

    def render_error(self, title: str, message: str, details: str = None) -> str:
        """Рендеринг HTML с ошибкой"""
        context = {
            "title": title,
            "message": message,
            "details": details
        }

        error_html = f"""
        <div class="result error">
            <h3>❌ {title}</h3>
            <p>{message}</p>
            {f'<details style="margin-top: 10px; font-size: 12px; color: #666;"><summary>Техническая информация</summary><p>{details}</p></details>' if details else ''}
        </div>
        """
        return error_html

    def render_validation_errors(self, field_errors: Dict[str, str]) -> str:
        """Рендеринг ошибок валидации полей"""
        error_list = "".join([f"<li>{field}: {error}</li>" for field, error in field_errors.items()])

        return f"""
        <div class="result error">
            <h3>❌ Ошибка валидации</h3>
            <p>Исправьте следующие ошибки:</p>
            <ul>
                {error_list}
            </ul>
        </div>
        """