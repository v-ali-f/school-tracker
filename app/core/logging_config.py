import logging

def configure_logging(app):
    if app.logger.handlers:
        return
    logging.basicConfig(level=logging.INFO)
