"""Logging configuration"""
import logging
import sys
import os
from typing import Any
from logging.handlers import RotatingFileHandler
import structlog
from structlog.stdlib import LoggerFactory, filter_by_level
from app.core.config import settings


def configure_logging(debug: bool = False) -> None:
    """Configure structured logging with file output"""
    level = logging.DEBUG if debug else logging.INFO
    NOISE_LOGGERS = {
        "sqlalchemy.engine",
        "sqlalchemy.pool",
        "sqlalchemy.orm",
        "multipart",
        "datamatrix",
        "multipart.multipart",
        "PIL",
    }

    for logger_name in NOISE_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.ERROR)

    # Create logs directory if it doesn't exist
    log_dir = settings.LOG_DIR
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    log_file_path = os.path.join(log_dir, settings.LOG_FILE)

    # Configure SQLAlchemy logging to be less verbose
    sqlalchemy_logger = logging.getLogger('sqlalchemy.engine')
    sqlalchemy_logger.setLevel(logging.WARNING)  # Изменено с INFO на WARNING

    # Create file handler with rotation
    file_handler = RotatingFileHandler(
        log_file_path,
        maxBytes=settings.LOG_MAX_BYTES,
        backupCount=settings.LOG_BACKUP_COUNT,
        encoding='utf-8',
    )
    file_handler.setLevel(level)

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)

    # Create formatters
    if debug:
        # Human-readable format for console
        console_formatter = logging.Formatter(
            '%(asctime)s [%(levelname)-8s] %(name)s: %(message)s',
            datefmt='%H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)

        # Detailed format for file
        file_formatter = logging.Formatter(
            '%(asctime)s [%(levelname)-8s] %(name)-25s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
    else:
        # Clean format for production
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)-5s] %(name)-25s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(formatter)
        file_handler.setFormatter(formatter)

    # Add filter to console handler to hide SQL queries
    def sql_filter(record):
        # Прячем детальные SQL запросы, но оставляем важные события
        if record.name == 'sqlalchemy.engine' and record.levelno == logging.INFO:
            return False
        # Прячем отладочные сообщения от datamatrix и PIL
        if record.name in ['datamatrix', 'PIL'] and record.levelno == logging.DEBUG:
            return False
        return True

    console_handler.addFilter(sql_filter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()  # Remove default handlers
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # Configure structlog processors
    processors = [
        filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if debug:
        processors.append(structlog.dev.ConsoleRenderer())
    else:
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Log initial message
    logger = structlog.get_logger(__name__)
    logger.info(
        "Logging configured",
        log_file=log_file_path,
        level=logging.getLevelName(level),
        debug=debug,
    )


def get_logger(name: str) -> Any:
    """Get structured logger"""
    return structlog.get_logger(name)