from harness.loud import swallowed as _swallowed


def swallowed(logger, where: str, exc: BaseException) -> None:
    """Log what a broad `except Exception` in HER TIME is about to discard.

    One line of shim over `harness.loud.swallowed`, which carries the reasoning and the
    incident that produced it. The rule is not kairos-specific — it was written here first
    because this is where it cost five and a half hours of silence — and the second lane to
    need it (recall's IDF table) proved the body belongs somewhere both can reach.

    G-KAIROS-LOUD holds the large handlers in this package to calling it.
    """
    _swallowed(logger, where, exc, lane="kairos")
