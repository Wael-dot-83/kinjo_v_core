"""
Backup manager module — provides database snapshot, config, and upload backup handling
for the KInJo platform admin panel.
"""

import os
import json
import shutil
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# Resolve paths relative to this file so it works regardless of cwd
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKUP_DIR = os.path.join(_BASE_DIR, "data", "backups")
_METADATA_FILE = os.path.join(_BACKUP_DIR, "backup_metadata.json")
_DB_PATH = os.path.join(_BASE_DIR, "data", "kinjo_fresh.db")
_UPLOADS_DIR = os.path.join(_BASE_DIR, "uploads")
_CONFIG_FILES = ["config.py", ".env", "alembic.ini"]
_RETENTION_DAYS = 30


def _ensure_backup_dir():
    os.makedirs(_BACKUP_DIR, exist_ok=True)


def _file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


class BackupManager:
    """Full-featured backup manager for database, uploads, and config files."""

    def __init__(self):
        _ensure_backup_dir()
        self.metadata: Dict[str, Any] = self._load_metadata()

    # ---- metadata persistence ------------------------------------------------

    def _load_metadata(self) -> Dict[str, Any]:
        if os.path.exists(_METADATA_FILE):
            try:
                with open(_METADATA_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                logger.warning("Corrupt backup metadata — starting fresh")
        return {}

    def _save_metadata(self):
        _ensure_backup_dir()
        with open(_METADATA_FILE, "w", encoding="utf-8") as f:
            json.dump(self.metadata, f, indent=2, default=str)

    # ---- create backups ------------------------------------------------------

    def create_database_backup(self, backup_type: str = "manual") -> Dict[str, Any]:
        _ensure_backup_dir()
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        name = f"db_{backup_type}_{ts}.sqlite3"
        dest = os.path.join(_BACKUP_DIR, name)

        if not os.path.exists(_DB_PATH):
            raise FileNotFoundError(f"Database file not found: {_DB_PATH}")

        shutil.copy2(_DB_PATH, dest)
        info = {
            "name": name,
            "type": "database",
            "backup_type": backup_type,
            "backup_path": dest,
            "size_bytes": os.path.getsize(dest),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "checksum": _file_sha256(dest),
        }
        self.metadata[name] = info
        self._save_metadata()
        return info

    def create_uploads_backup(self, backup_type: str = "manual") -> Dict[str, Any]:
        _ensure_backup_dir()
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        name = f"uploads_{backup_type}_{ts}"
        dest = os.path.join(_BACKUP_DIR, name)

        if os.path.isdir(_UPLOADS_DIR):
            shutil.make_archive(dest, "zip", _UPLOADS_DIR)
            archive = dest + ".zip"
        else:
            # No uploads directory — create empty placeholder
            archive = dest + ".zip"
            import zipfile
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("__empty__", "")

        info = {
            "name": os.path.basename(archive),
            "type": "uploads",
            "backup_type": backup_type,
            "backup_path": archive,
            "size_bytes": os.path.getsize(archive),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "checksum": _file_sha256(archive),
        }
        self.metadata[os.path.basename(archive)] = info
        self._save_metadata()
        return info

    def create_config_backup(self, backup_type: str = "manual") -> Dict[str, Any]:
        _ensure_backup_dir()
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        name = f"config_{backup_type}_{ts}.zip"
        dest = os.path.join(_BACKUP_DIR, name)

        import zipfile
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
            for cfg in _CONFIG_FILES:
                full = os.path.join(_BASE_DIR, cfg)
                if os.path.exists(full):
                    zf.write(full, cfg)

        info = {
            "name": name,
            "type": "config",
            "backup_type": backup_type,
            "backup_path": dest,
            "size_bytes": os.path.getsize(dest),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "checksum": _file_sha256(dest),
        }
        self.metadata[name] = info
        self._save_metadata()
        return info

    # ---- list / info ---------------------------------------------------------

    def list_backups(self, backup_type: Optional[str] = None) -> List[Dict[str, Any]]:
        backups = list(self.metadata.values())
        if backup_type:
            backups = [b for b in backups if b.get("type") == backup_type]
        backups.sort(key=lambda b: b.get("created_at", ""), reverse=True)
        return backups

    def get_backup_info(self, backup_name: str) -> Optional[Dict[str, Any]]:
        return self.metadata.get(backup_name)

    # ---- validate / restore --------------------------------------------------

    def validate_backup(self, backup_name: str) -> bool:
        info = self.metadata.get(backup_name)
        if not info:
            return False
        path = info.get("backup_path", "")
        if not os.path.exists(path):
            return False
        try:
            return _file_sha256(path) == info.get("checksum")
        except Exception:
            return False

    def restore_database_backup(self, backup_name: str) -> bool:
        info = self.metadata.get(backup_name)
        if not info:
            return False
        src = info.get("backup_path", "")
        if not os.path.exists(src):
            return False
        try:
            # Keep a pre-restore snapshot
            pre = _DB_PATH + ".pre_restore"
            if os.path.exists(_DB_PATH):
                shutil.copy2(_DB_PATH, pre)
            shutil.copy2(src, _DB_PATH)
            return True
        except Exception as e:
            logger.error(f"Restore failed: {e}")
            return False

    # ---- cleanup -------------------------------------------------------------

    def cleanup_old_backups(self, retention_days: int = _RETENTION_DAYS):
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        to_delete = []
        for name, info in list(self.metadata.items()):
            created = info.get("created_at", "")
            try:
                created_dt = datetime.fromisoformat(created)
            except Exception:
                continue
            # Make offset-naive for comparison if needed
            if created_dt.tzinfo is None:
                created_dt = created_dt.replace(tzinfo=timezone.utc)
            if created_dt < cutoff and info.get("backup_type") != "manual":
                to_delete.append(name)

        for name in to_delete:
            path = self.metadata[name].get("backup_path", "")
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass
            del self.metadata[name]

        if to_delete:
            self._save_metadata()
            logger.info(f"Cleaned up {len(to_delete)} old backups")


class BackupScheduler:
    """Stub backup scheduler"""
    def start_scheduler(self):
        pass

    def stop_scheduler(self):
        pass


# Global instances
backup_manager = BackupManager()
backup_scheduler = BackupScheduler()
