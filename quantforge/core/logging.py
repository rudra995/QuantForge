import contextvars
import logging
import sys
from typing import Any

import structlog
from structlog.types import EventDict, Processor

from quantforge.core.config import settings

# Global contextvar to hold the active request ID in async/sync execution flows
request_id_context: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)


def get_request_id() -> str | None:
    """Retrieve the current request ID from the execution context.

    Returns:
        The active request ID string, or None if not set.
    """
    return request_id_context.get()


def set_request_id(request_id: str | None) -> None:
    """Assign a request ID to the current execution context.

    Args:
        request_id: The request identifier to set.
    """
    request_id_context.set(request_id)


def inject_request_id_processor(
    _logger: Any, _method_name: str, event_dict: EventDict
) -> EventDict:
    """Structlog processor to inject request_id from the contextvar.

    Args:
        _logger: Instantiated logger.
        _method_name: Name of the logging method (e.g. info, debug).
        event_dict: Event dictionary containing log payload.

    Returns:
        The updated event dictionary.
    """
    req_id = get_request_id()
    if req_id is not None:
        event_dict["request_id"] = req_id
    return event_dict


class LoggingSetup:
    """Manager class to encapsulate logging setup and configuration."""

    @classmethod
    def configure(cls) -> None:
        """Configures global structlog logging.

        Applies JSON rendering in production environments and highly readable,
        colorized output during local development.
        """
        # Determine the internal logger output destination
        output_stream = sys.stdout

        # Define structural processors common to both environments
        processors: list[Processor] = [
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            inject_request_id_processor,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
        ]

        if settings.ENV == "prod":
            # Production: JSON serialization
            processors.append(structlog.processors.JSONRenderer())
        else:
            # Development: Clean colorized console rendering
            processors.append(structlog.dev.ConsoleRenderer(colors=True))

        # Map string setting config to python logging level integer
        log_level_map = {
            "debug": logging.DEBUG,
            "info": logging.INFO,
            "warning": logging.WARNING,
            "error": logging.ERROR,
            "critical": logging.CRITICAL,
        }
        numeric_level = log_level_map.get(settings.LOG_LEVEL.lower(), logging.INFO)

        structlog.configure(
            processors=processors,
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(file=output_stream),
            wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
            cache_logger_on_first_use=True,
        )


# Automatically execute setup upon initial import of this module
LoggingSetup.configure()

# Obtain a bound logger for application-wide logging operations
logger = structlog.get_logger()
