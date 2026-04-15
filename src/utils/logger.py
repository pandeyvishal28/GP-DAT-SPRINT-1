"""
utils/logger.py
Centralized logging configuration for GP-DAT.

Sets up logging to both the console and rotating log files.
Creates separate files for general logs, error logs, and agent-only logs.
Injects the per-request correlation ID into every log record automatically.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config.settings import get_settings


class CorrelationFilter(logging.Filter):
    """
    Logging filter that injects the current request's correlation ID
    into every log record via contextvars.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        from utils.correlation import get_correlation_id

        record.correlation_id = get_correlation_id()
        return True


class AgentOnlyFilter(logging.Filter):
    """Only allow log records from agent.* loggers."""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.name.startswith("agent.")


def setup_logger() -> None:
    """
    Configures the root logger.

    - Console Output: All logs (based on LOG_LEVEL in settings).
    - File Output (app.log): All logs (Rotating, max 10MB, up to 5 backups).
    - File Output (error.log): Errors and Warnings only (Rotating).
    - File Output (agent.log): Agent-only logs (Rotating).

    Logger naming convention:
        - Agents:       agent.{type}          (e.g. agent.context_agent)
        - Services:     service.{name}        (e.g. service.llm)
        - Routers:      router.{name}         (e.g. router.generation)
        - Orchestrator: orchestrator.{component}
        - Middleware:    middleware
    """
    settings = get_settings()
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    # 1. Ensure logs directory exists
    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    # 2. Create the shared correlation filter
    correlation_filter = CorrelationFilter()

    # 3. Define formatters (now with correlation_id)
    standard_formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(correlation_id)s | %(name)-25s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    detailed_formatter = logging.Formatter(
        fmt=(
            "%(asctime)s | %(levelname)-8s | %(correlation_id)s"
            " | %(name)-25s | [%(filename)s:%(lineno)d] | %(message)s"
        ),
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 4. Create handlers

    # Console Handler (everything)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(standard_formatter)
    console_handler.addFilter(correlation_filter)

    # General File Handler (everything, rotating)
    app_file_handler = RotatingFileHandler(
        filename=str(log_dir / "app.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    app_file_handler.setLevel(log_level)
    app_file_handler.setFormatter(standard_formatter)
    app_file_handler.addFilter(correlation_filter)

    # Error File Handler (WARNING and ERROR, rotating)
    error_file_handler = RotatingFileHandler(
        filename=str(log_dir / "error.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    error_file_handler.setLevel(logging.WARNING)
    error_file_handler.setFormatter(detailed_formatter)
    error_file_handler.addFilter(correlation_filter)

    # Agent-only File Handler (agent.* loggers only, rotating)
    agent_file_handler = RotatingFileHandler(
        filename=str(log_dir / "agent.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    agent_file_handler.setLevel(log_level)
    agent_file_handler.setFormatter(standard_formatter)
    agent_file_handler.addFilter(correlation_filter)
    agent_file_handler.addFilter(AgentOnlyFilter())

    # 5. Configure Root Logger
    root_logger = logging.getLogger()

    # Clear any existing handlers to prevent duplicate logs
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    root_logger.setLevel(log_level)

    root_logger.addHandler(console_handler)
    root_logger.addHandler(app_file_handler)
    root_logger.addHandler(error_file_handler)
    root_logger.addHandler(agent_file_handler)

    # Silence noisy third-party loggers
    for noisy in ("httpx", "httpcore", "urllib3", "openai", "langchain", "langsmith"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
