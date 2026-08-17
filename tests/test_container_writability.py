"""The image must let the non-root app user CREATE files in its working directory.

COPY --chown only fixes the files it copies. /app is created by WORKDIR as root,
so without an explicit chown the app user can read everything and write nothing
new. Two runtime paths do exactly that, and both crash-looped in production on
the first non-root deploy:

  * logging.FileHandler(settings.LOG_FILE) -> /app/kinjo.log
  * celery beat's schedule database        -> /app/celerybeat-schedule

Neither is visible in a successful build, and the web container's health check
passes without them, so only an explicit assertion catches a regression here.
"""

import pathlib
import re

DOCKERFILE = pathlib.Path(__file__).resolve().parent.parent / "Dockerfile"


def _dockerfile() -> str:
    return DOCKERFILE.read_text(encoding="utf-8")


def test_image_runs_as_non_root():
    assert re.search(r"^USER\s+kinjo\s*$", _dockerfile(), re.MULTILINE)


def test_workdir_itself_is_owned_by_the_app_user():
    """chown of /app/logs and /app/data alone is NOT enough — /app must be owned too."""
    src = _dockerfile()
    assert re.search(r"chown\s+(-R\s+)?kinjo:kinjo\s+/app(\s|\|$)", src), (
        "/app itself is not chowned to the app user; celery beat and the file "
        "logger will fail with EACCES at runtime"
    )


def test_chown_happens_before_the_user_switch():
    """After USER kinjo the build can no longer change ownership."""
    src = _dockerfile()
    assert src.index("chown kinjo:kinjo /app") < src.index("USER kinjo")
