import logging
import re


class _RedactAuthorizationFilter(logging.Filter):
    """Reduce risk of logging bearer tokens (SE-026)."""

    _pat = re.compile(r"(?i)(authorization:\s*)(bearer\s+)(\S+)")

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        if self._pat.search(msg):
            record.msg = self._pat.sub(r"\1\2[REDACTED]", msg)
            record.args = ()
        return True


def setup_logging():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("mindweave")
    logger.addFilter(_RedactAuthorizationFilter())
    return logger


logger = setup_logging()
