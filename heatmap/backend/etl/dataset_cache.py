"""Per-worker cache for the generated heat map dataset, with cross-worker freshness.

The problem this solves (HM-3): the parsed CSV used to live in a module-level global
that was populated once and never re-read. Under the documented production command
(`uvicorn --workers 4`) that is four independent copies, and a Celery worker rebuilding
the dataset could not reach any of them. Operators had to restart the API to pick up
new data.

The contract here:

* **The manifest on disk is authoritative.** Redis is only an optimisation that lets a
  worker skip a `stat()`. This is not a stylistic preference — `cache_service` falls
  back to a *per-process* in-memory dict when Redis is unreachable, so a Redis-centred
  design would silently degrade to exactly the staleness we are removing, precisely
  when Redis is having a bad day.
* **Identity is a content hash, never mtime.** Timestamp resolution varies across
  platforms and containers, and a scheduled rebuild colliding with a manual refresh
  inside one second is realistic. `(mtime, size)` is used only as a cheap "might
  something have changed?" gate before reading the manifest.
* **Build then swap.** A reload constructs the new frame off to the side and rebinds a
  single reference on success. The previously valid frame is never cleared first, so a
  failed reload degrades to "slightly stale" rather than "no data".
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# How long a worker may serve without re-checking freshness. Keeps a burst of requests
# off the filesystem while bounding how long a worker can lag a new dataset.
REVALIDATE_INTERVAL_SECONDS = 5.0


@dataclass(frozen=True)
class LoadedDataset:
    """An immutable published snapshot.

    Frozen on purpose: once a snapshot is visible to readers it must not change under
    them. A reload publishes a *new* instance rather than mutating this one.
    """

    version: Optional[str]
    frame: pd.DataFrame
    rows: int
    loaded_at: float
    manifest: Dict[str, Any]


class DatasetCache:
    """Freshness-aware cache of one generated dataset.

    Instantiable rather than module-global so tests get isolated instances and cannot
    leak state into each other — and so a test can never race the process-wide cache.
    """

    def __init__(
        self,
        dataset_path: Callable[[], Path],
        manifest_path: Callable[[], Path],
        loader: Callable[[Path], pd.DataFrame],
        version_provider: Optional[Callable[[], Optional[str]]] = None,
        revalidate_interval: float = REVALIDATE_INTERVAL_SECONDS,
    ) -> None:
        # Paths are callables so the cache follows monkeypatched module constants in
        # tests and never pins a path captured at import time.
        self._dataset_path = dataset_path
        self._manifest_path = manifest_path
        self._loader = loader
        self._version_provider = version_provider
        self._revalidate_interval = revalidate_interval

        self._lock = threading.Lock()
        self._current: Optional[LoadedDataset] = None
        self._last_checked: float = 0.0
        self._last_manifest_version: Optional[str] = None
        self._reload_count = 0
        self._last_error: Optional[str] = None

    # -- introspection -----------------------------------------------------

    @property
    def loaded_version(self) -> Optional[str]:
        current = self._current
        return current.version if current else None

    @property
    def reload_count(self) -> int:
        return self._reload_count

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    def loaded_at(self) -> Optional[float]:
        current = self._current
        return current.loaded_at if current else None

    def invalidate(self) -> None:
        """Force the next access to re-check, without discarding what we have.

        Clearing the frame here would open a window where readers see nothing; the
        point of this cache is that such a window never exists.
        """
        self._last_checked = 0.0

    # -- freshness ---------------------------------------------------------

    def _read_manifest(self) -> Dict[str, Any]:
        path = self._manifest_path()
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as exc:
            # A corrupt manifest must not take the endpoint down; keep serving and
            # try again on the next interval.
            logger.warning("Heat map dataset manifest is unreadable: %s", exc)
            return {}

    def _active_version(self) -> Optional[str]:
        """The version the worker *should* be serving.

        Redis first when present: a hit that matches what we already hold ends the
        check with no file I/O at all. Redis never decides *what* to load — only
        whether it is worth looking at the manifest.
        """
        if self._version_provider is not None:
            try:
                published = self._version_provider()
            except Exception as exc:  # noqa: BLE001 - cache trouble is never fatal here
                logger.debug("Heat map version provider unavailable: %s", exc)
                published = None
            if published and published == self.loaded_version:
                return published

        # Read the manifest outright rather than short-circuiting on (mtime, size).
        #
        # An earlier revision used that stat pair as a "nothing moved" gate, and it was
        # wrong for the reason this module already refuses to trust mtime for identity:
        # two generations close together can land on the same timestamp and the same
        # manifest length, at which point the gate reports "unchanged" for a dataset
        # that changed. A two-worker smoke test reproduced exactly that — the second
        # worker never picked up the rebuild.
        #
        # The read is bounded by the revalidation interval, and the manifest is a few
        # hundred bytes, so the saving was negligible against a real correctness hole.
        manifest = self._read_manifest()
        version = manifest.get("version")
        self._last_manifest_version = version
        return version

    # -- read path ---------------------------------------------------------

    def get(self) -> LoadedDataset:
        """Return the current snapshot, reloading only if the active version moved."""
        now = time.monotonic()
        current = self._current

        if current is not None and (now - self._last_checked) < self._revalidate_interval:
            return current

        active = self._active_version()
        self._last_checked = now

        if current is not None and active == current.version:
            return current

        return self._reload(active)

    def get_frame(self) -> pd.DataFrame:
        return self.get().frame

    def _reload(self, expected_version: Optional[str]) -> LoadedDataset:
        with self._lock:
            # Double-checked: another thread may have loaded this exact version while
            # we waited, in which case the work is already done.
            current = self._current
            if current is not None and current.version == expected_version:
                return current

            path = self._dataset_path()
            if not path.exists():
                # Absent dataset is an operational state, not an error. Publish an
                # empty snapshot so the unavailable contract holds without raising.
                empty = LoadedDataset(
                    version=None, frame=pd.DataFrame(), rows=0,
                    loaded_at=time.time(), manifest={},
                )
                self._current = empty
                return empty

            try:
                frame = self._loader(path)
            except Exception as exc:  # noqa: BLE001 - a bad file must not blank the cache
                self._last_error = str(exc)
                logger.exception("Heat map dataset reload failed; keeping previous data")
                if current is not None:
                    return current
                empty = LoadedDataset(
                    version=None, frame=pd.DataFrame(), rows=0,
                    loaded_at=time.time(), manifest={},
                )
                self._current = empty
                return empty

            manifest = self._read_manifest()
            # Re-read the version from the manifest we actually loaded alongside, so a
            # file that changed mid-check is labelled with what is really on disk.
            loaded = LoadedDataset(
                version=manifest.get("version", expected_version),
                frame=frame,
                rows=int(len(frame)),
                loaded_at=time.time(),
                manifest=manifest,
            )
            # Single rebind: readers holding the old object keep a consistent view.
            self._current = loaded
            self._reload_count += 1
            self._last_error = None
            logger.info(
                "Heat map dataset reloaded: version=%s rows=%d",
                loaded.version, loaded.rows,
            )
            return loaded
