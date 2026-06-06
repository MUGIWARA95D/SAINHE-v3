"""
gdrive_backup_code.py — Backup complet du code SAINHE vers Google Drive.

Crée deux fichiers horodatés dans un dossier Drive dédié :
  - sainhe-v4-YYYY-MM-DD.bundle  : git bundle complet (toutes branches + historique)
  - sainhe-v4-YYYY-MM-DD.zip     : snapshot des sources (sans .git, sans output/)

Usage:
    python scripts/gdrive_backup_code.py

Variables d'environnement requises:
    GDRIVE_SA_KEY            : contenu JSON du compte de service Google
    GDRIVE_BACKUP_FOLDER_ID  : ID du dossier Drive de destination

Comment obtenir GDRIVE_BACKUP_FOLDER_ID :
    1. Créer un dossier "SAINHE Backups" sur Google Drive
    2. Ouvrir le dossier → l'URL contient  .../folders/<ID>
    3. Partager le dossier avec l'email du service account
       (visible dans GDRIVE_SA_KEY → "client_email")
"""

import io
import json
import logging
import os
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [backup] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

SCOPES    = ["https://www.googleapis.com/auth/drive"]
REPO_ROOT = Path(__file__).resolve().parent.parent
TODAY     = datetime.now(timezone.utc).strftime("%Y-%m-%d")

EXCLUDE_DIRS  = {".git", "__pycache__", "output", "db", ".venv", "venv", "node_modules", ".mypy_cache"}
EXCLUDE_FILES = {".env", "sainhe.db"}


def _service():
    folder_id = os.environ.get("GDRIVE_BACKUP_FOLDER_ID", "").strip()
    if not folder_id:
        raise RuntimeError("GDRIVE_BACKUP_FOLDER_ID env var is not set")
    sa_raw = os.environ.get("GDRIVE_SA_KEY", "")
    if not sa_raw:
        raise RuntimeError("GDRIVE_SA_KEY env var is not set")
    sa_info = json.loads(sa_raw.lstrip("﻿"))
    creds   = service_account.Credentials.from_service_account_info(sa_info, scopes=SCOPES)
    svc     = build("drive", "v3", credentials=creds)
    return svc, folder_id


def _upload(svc, folder_id: str, local_path: Path, mime: str):
    name = local_path.name
    meta = {"name": name, "parents": [folder_id]}
    media = MediaFileUpload(str(local_path), mimetype=mime, resumable=True)
    f = svc.files().create(body=meta, media_body=media, fields="id,name,size").execute()
    size_mb = int(f.get("size", 0)) / 1_048_576
    log.info("Uploadé → Drive : %s (%.2f MB)  id=%s", f["name"], size_mb, f["id"])


def create_git_bundle(dest: Path):
    """git bundle create — inclut toutes les branches et l'historique complet."""
    result = subprocess.run(
        ["git", "bundle", "create", str(dest), "--all"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git bundle failed: {result.stderr}")
    log.info("Git bundle créé : %s (%.2f MB)", dest.name, dest.stat().st_size / 1_048_576)


def create_zip(dest: Path):
    """Zip des sources — exclut .git, output/, db/, .env, __pycache__."""
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in sorted(REPO_ROOT.rglob("*")):
            if path.is_dir():
                continue
            rel = path.relative_to(REPO_ROOT)
            parts = rel.parts
            if any(p in EXCLUDE_DIRS for p in parts):
                continue
            if path.name in EXCLUDE_FILES:
                continue
            zf.write(path, rel)
    log.info("Zip créé : %s (%.2f MB)", dest.name, dest.stat().st_size / 1_048_576)


def main():
    svc, folder_id = _service()

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        # 1. Git bundle
        bundle_path = tmp / f"sainhe-v4-{TODAY}.bundle"
        create_git_bundle(bundle_path)
        _upload(svc, folder_id, bundle_path, "application/octet-stream")

        # 2. Source zip
        zip_path = tmp / f"sainhe-v4-{TODAY}.zip"
        create_zip(zip_path)
        _upload(svc, folder_id, zip_path, "application/zip")

    log.info("Backup terminé — 2 fichiers uploadés sur Google Drive.")


if __name__ == "__main__":
    main()
