

def swallowed(logger, where: str, exc: BaseException) -> None:
    """Log what a broad `except Exception` is about to discard. PROGRAMMING ERRORS LOUD.

    THE FAILURE THIS ANSWERS (2026-08-28). `reflect_tick` wraps its body in
    `except Exception` and returns None, which is also what it returns on a quiet night.
    A refactor left a name unimported, every tick raised NameError, and the whole
    conclusion lane was dead for five and a half hours while the suite stayed green. The
    operator noticed before any instrument did.

    A broad handler is often right here — Home Assistant restarts, the daemon goes away,
    a store is mid-write — and none of that should cost her a turn. But NameError,
    AttributeError, TypeError and ImportError are not the world being unreliable. They are
    the code being wrong, they never fix themselves, and they must not be indistinguishable
    from "nothing happened".

    So the shape stays and the volume changes: environment at debug, our own bugs at
    warning, with the type named so it is greppable. G-KAIROS-LOUD holds the large
    handlers to using it.
    """
    if isinstance(exc, (NameError, AttributeError, TypeError, ImportError)):
        logger.warning("[kairos] %s swallowed a %s: %s", where, type(exc).__name__, exc)
    else:
        logger.debug("[kairos] %s: %s: %s", where, type(exc).__name__, exc)
