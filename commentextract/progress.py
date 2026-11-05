from contextvars import ContextVar

callback = ContextVar("processing_progress", default=None)


def stage(percent, text):
    handler = callback.get()
    if handler:
        handler(percent, text)
