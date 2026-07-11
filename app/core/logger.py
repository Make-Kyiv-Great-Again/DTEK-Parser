import json
import logging
import logging.config
import contextvars
from datetime import datetime, timezone

request_context = contextvars.ContextVar("request_context", default={})

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        ctx = request_context.get()
        if ctx:
            log_record.update({
                "request_id": ctx.get("request_id"),
                "ip_address": ctx.get("ip_address"),
                "client_name": ctx.get("client_name")
            })
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_record, ensure_ascii=False)

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": JSONFormatter,
        },
    },
    "handlers": {
        "stdout": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "stream": "ext://sys.stdout",
        },
    },
    "loggers": {
        "root": {
            "handlers": ["stdout"],
            "level": "INFO",
        },
        "uvicorn": {
            "handlers": ["stdout"],
            "level": "INFO",
            "propagate": False,
        },
        "uvicorn.access": {
            "handlers": ["stdout"],
            "level": "WARNING",
            "propagate": False,
        },
        "uvicorn.error": {
            "handlers": ["stdout"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

def setup_logging():
    logging.config.dictConfig(LOGGING_CONFIG)
