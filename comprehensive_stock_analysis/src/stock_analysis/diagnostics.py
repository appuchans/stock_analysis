"""Crash forensics for long-running entry points.

Motivation: a web-UI run died mid-analysis on 2026-08-11 leaving nothing in
``logs/crew_output.log`` but the *downstream* errors — every stage failing with
``cannot schedule new futures after shutdown``. The process exit itself left no
trace, because:

* ``LOG_LEVEL`` defaults to ``ERROR`` in ``.env``, so no lifecycle record was
  ever emitted;
* uvicorn logs through its own dictConfig to the console, not our file handler;
* an unhandled exception in a *thread* prints to stderr and is otherwise lost;
* a hard crash (segfault/abort) produces no Python-level output at all.

This module closes all four gaps so the next occurrence is diagnosable from the
log file alone. Everything here is best-effort: diagnostics must never be the
reason a process fails to start.
"""

import atexit
import faulthandler
import logging
import os
import signal
import sys
import threading
from pathlib import Path
from typing import Optional

_logger = logging.getLogger("stock_analysis.lifecycle")

# Kept open for the process lifetime — faulthandler writes to this fd directly
# from a signal handler, so it must not be garbage-collected or buffered away.
_fault_log = None
_installed = False


def _fault_log_path(log_path: Path) -> Path:
    return log_path.with_name(log_path.stem + "_faults.log")


def install(log_path: Path, role: str = "web") -> None:
    """Install crash diagnostics. Safe to call once per process; repeat calls
    are no-ops so an import-order surprise can't double-register handlers."""
    global _fault_log, _installed
    if _installed:
        return
    _installed = True

    _install_faulthandler(log_path)
    _install_excepthooks()
    _install_signal_logging()
    _install_exit_logging(role)

    _logger.info(
        "process start: role=%s pid=%s python=%s cwd=%s",
        role,
        os.getpid(),
        sys.version.split()[0],
        os.getcwd(),
    )


def _install_faulthandler(log_path: Path) -> None:
    """Catch segfaults/aborts, which produce no Python traceback at all."""
    global _fault_log
    try:
        path = _fault_log_path(log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        _fault_log = open(path, "a", buffering=1, encoding="utf-8")
        faulthandler.enable(file=_fault_log, all_threads=True)
        # SIGABRT/SIGSEGV/SIGFPE/SIGBUS/SIGILL are covered by enable(). Add
        # SIGTERM so a kill leaves a full all-thread stack dump showing exactly
        # what the analysis worker was doing when it went down.
        if hasattr(faulthandler, "register") and hasattr(signal, "SIGTERM"):
            faulthandler.register(signal.SIGTERM, file=_fault_log, all_threads=True)
    except Exception as exc:  # pragma: no cover - diagnostics must never block
        _logger.debug("faulthandler unavailable: %s", exc)


def _install_excepthooks() -> None:
    """Log unhandled exceptions from the main thread *and* worker threads.

    ``threading.excepthook`` matters most here: the analysis runs in a
    JobManager worker, and without this an exception there only ever reaches
    stderr.
    """

    def _main_hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            _logger.warning("interrupted by KeyboardInterrupt (Ctrl-C)")
        else:
            _logger.critical("unhandled exception", exc_info=(exc_type, exc, tb))
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = _main_hook

    def _thread_hook(args):
        if issubclass(args.exc_type, SystemExit):
            return
        _logger.critical(
            "unhandled exception in thread %s",
            getattr(args.thread, "name", "?"),
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    try:
        threading.excepthook = _thread_hook
    except Exception:  # pragma: no cover - Python < 3.8
        pass


def _install_signal_logging() -> None:
    """Record which signal ended the process, then honour the default action.

    Distinguishing SIGINT (Ctrl-C) from SIGTERM (kill / supervisor) from SIGHUP
    (terminal closed) is the difference between "the user stopped it" and "the
    OS or a parent process did" — the exact question left unanswerable last
    time.
    """
    for name in ("SIGTERM", "SIGINT", "SIGHUP", "SIGQUIT"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            previous = signal.getsignal(sig)
        except (ValueError, OSError):  # pragma: no cover
            continue

        def _handler(signum, frame, _prev=previous, _name=name):
            _logger.critical(
                "received %s (signal %s) — process is going down", _name, signum
            )
            # Installing this handler replaces faulthandler's own SIGTERM
            # registration, so dump the stacks explicitly. This is the part
            # that shows what the analysis worker was mid-way through when the
            # process was told to die — the question the last incident could
            # not answer.
            if _fault_log is not None:
                try:
                    print(
                        f"--- {_name} received; all-thread stack dump ---",
                        file=_fault_log,
                        flush=True,
                    )
                    faulthandler.dump_traceback(file=_fault_log, all_threads=True)
                except Exception:
                    pass
            for h in logging.getLogger().handlers:
                try:
                    h.flush()
                except Exception:
                    pass
            if callable(_prev):
                _prev(signum, frame)
            elif _prev == signal.SIG_DFL:
                signal.signal(signum, signal.SIG_DFL)
                os.kill(os.getpid(), signum)

        try:
            signal.signal(sig, _handler)
        except (ValueError, OSError):  # not in main thread / unsupported
            continue


def _install_exit_logging(role: str) -> None:
    """A final record on every exit path, so the log always shows the process
    ending rather than simply stopping mid-line."""

    def _on_exit():
        _logger.info("process exit: role=%s pid=%s", role, os.getpid())
        for h in logging.getLogger().handlers:
            try:
                h.flush()
            except Exception:
                pass

    atexit.register(_on_exit)


def attach_uvicorn_logging(level: Optional[int] = None) -> None:
    """Route uvicorn's loggers through the root handlers (our file handler).

    uvicorn installs its own dictConfig with ``propagate: False``, so by
    default its startup/shutdown lines and any event-loop traceback go to the
    console only — invisible in the persistent log. Call this *after*
    ``uvicorn.run`` has configured logging (i.e. from the app's lifespan hook).
    """
    for name in ("uvicorn", "uvicorn.error", "asyncio"):
        lg = logging.getLogger(name)
        lg.propagate = True
        if level is not None:
            lg.setLevel(level)

    # uvicorn.access logs a line per request — one page load is ~17 lines of
    # static assets, which would bury the lifecycle records this module exists
    # to preserve. Let it propagate only at WARNING+; uvicorn.error is the
    # logger that actually carries startup/shutdown lines and tracebacks.
    access = logging.getLogger("uvicorn.access")
    access.propagate = True
    access.setLevel(logging.WARNING)
