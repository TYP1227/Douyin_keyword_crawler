import logging
import sys
def setup_logging(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("dykw")
    if logger.handlers:
        return logger

    logger.setLevel(level.upper())
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


def get_logger() -> logging.Logger:
    logger = logging.getLogger("dykw")
    if not logger.handlers:
        return setup_logging()
    return logger

