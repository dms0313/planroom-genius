"""Persistence layer for storing analysis history and metadata."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)


class HistoryStore:
    """Simple file-backed history store for analysis runs."""

    def __init__(self, base_dir: Optional[str] = None):
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
        default_dir = os.path.join(project_root, "data", "history")

        # Allow overrides for read-only environments such as Vercel.
        env_dir = os.environ.get("HISTORY_BASE_DIR") or os.environ.get("APP_DATA_DIR")
        preferred_dir = os.path.abspath(base_dir or env_dir or default_dir)

        self.base_dir = self._ensure_directory(preferred_dir)
        if not self.base_dir:
            tmp_fallback = os.path.join(tempfile.gettempdir(), "fire-alarm-history")
            self.base_dir = self._ensure_directory(tmp_fallback)

        if not self.base_dir:
            raise OSError("Unable to initialize HistoryStore: no writable directory available")

    def _job_dir(self, job_id: str) -> str:
        return os.path.join(self.base_dir, job_id)

    def save_entry(
        self,
        job_id: str,
        analysis_type: str,
        original_filename: str,
        results: Dict[str, Any],
        pdf_path: Optional[str] = None,
        project_name: Optional[str] = None,
    ) -> None:
        """Persist an analysis run and optional PDF for future retrieval."""

        job_dir = self._job_dir(job_id)
        os.makedirs(job_dir, exist_ok=True)

        stored_pdf_path = None
        if pdf_path and os.path.exists(pdf_path):
            stored_pdf_path = os.path.join(job_dir, "upload.pdf")
            try:
                shutil.copy2(pdf_path, stored_pdf_path)
            except Exception:
                stored_pdf_path = None

        timestamp = datetime.now().isoformat()

        # Ensure the job id is available inside the results for UI reuse
        results_with_id = {**results}
        results_with_id.setdefault("job_id", job_id)

        metadata = {
            "job_id": job_id,
            "analysis_type": analysis_type,
            "original_filename": original_filename,
            "project_name": project_name,
            "timestamp": timestamp,
            "pdf_filename": os.path.basename(stored_pdf_path) if stored_pdf_path else None,
            "stored_pdf_path": stored_pdf_path,
        }

        self._write_json(os.path.join(job_dir, "metadata.json"), metadata)
        self._write_json(os.path.join(job_dir, "results.json"), results_with_id)

    def list_entries(self) -> List[Dict[str, Any]]:
        """Return sorted metadata for all stored runs (newest first)."""

        entries: List[Dict[str, Any]] = []
        if not os.path.exists(self.base_dir):
            return entries

        for job_id in os.listdir(self.base_dir):
            job_dir = self._job_dir(job_id)
            metadata_path = os.path.join(job_dir, "metadata.json")
            if not os.path.isfile(metadata_path):
                continue
            try:
                metadata = self._read_json(metadata_path)
                if metadata:
                    entries.append(metadata)
            except Exception:
                continue

        return sorted(entries, key=lambda item: item.get("timestamp", ""), reverse=True)

    def load_entry(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Load metadata and results for a given job id."""

        job_dir = self._job_dir(job_id)
        metadata_path = os.path.join(job_dir, "metadata.json")
        results_path = os.path.join(job_dir, "results.json")

        if not os.path.isfile(metadata_path) or not os.path.isfile(results_path):
            return None

        metadata = self._read_json(metadata_path) or {}
        results = self._read_json(results_path) or {}

        stored_pdf_path = metadata.get("stored_pdf_path")
        local_pdf_path = os.path.join(job_dir, "upload.pdf")

        if stored_pdf_path and os.path.isfile(stored_pdf_path):
            pdf_path = stored_pdf_path
        elif os.path.isfile(local_pdf_path):
            # Fallback to the local file if the absolute path is invalid (migration)
            pdf_path = local_pdf_path
        else:
            pdf_path = None

        return {
            "job_id": job_id,
            "metadata": metadata,
            "results": results,
            "pdf_path": pdf_path,
            "storage_dir": job_dir,
            "analysis_type": metadata.get("analysis_type"),
            "project_name": metadata.get("project_name"),
            "original_filename": metadata.get("original_filename"),
            "timestamp": metadata.get("timestamp"),
        }

    def _write_json(self, path: str, payload: Dict[str, Any]) -> None:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

    def _read_json(self, path: str) -> Dict[str, Any]:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def update_project_name(self, job_id: str, project_name: str) -> bool:
        """Update the stored project name for a given job id."""

        metadata_path = os.path.join(self._job_dir(job_id), "metadata.json")
        if not os.path.isfile(metadata_path):
            return False

        metadata = self._read_json(metadata_path)
        metadata["project_name"] = project_name
        self._write_json(metadata_path, metadata)
        return True

    def delete_entry(self, job_id: str) -> bool:
        """Remove a stored analysis from disk."""

        job_dir = self._job_dir(job_id)
        if not os.path.isdir(job_dir):
            return False

        shutil.rmtree(job_dir, ignore_errors=True)
        return True

    def _ensure_directory(self, path: str) -> Optional[str]:
        """Return a writable directory path, or None if unavailable."""

        try:
            os.makedirs(path, exist_ok=True)
            test_path = os.path.join(path, ".write_test")
            with open(test_path, "w", encoding="utf-8") as handle:
                handle.write("ok")
            os.remove(test_path)
            return path
        except OSError as exc:
            logger.warning("HistoryStore directory not writable (%s): %s", path, exc)
            return None
