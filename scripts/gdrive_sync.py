"""
gdrive_sync.py — Download / upload sainhe.db depuis Google Drive.

Usage:
    python scripts/gdrive_sync.py download
    python scripts/gdrive_sync.py upload

Variables d'environnement requises:
    GDRIVE_SA_KEY   : contenu JSON du compte de service Google
    GDRIVE_FILE_ID  : ID du fichier sainhe.db sur Drive
    DB_PATH         : chemin local de la DB (défaut: db/sainhe.db)
"""

import io
import json
import logging
import os
import sys
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [gdrive] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

SCOPES   = ["https://www.googleapis.com/auth/drive"]
FILE_ID  = os.environ["GDRIVE_FILE_ID"].strip().lstrip("﻿")
DB_PATH  = Path(os.environ.get("DB_PATH", "db/sainhe.db"))


def _service():
    sa_info = json.loads(os.environ["GDRIVE_SA_KEY"].lstrip("﻿"))
    creds   = service_account.Credentials.from_service_account_info(sa_info, scopes=SCOPES)
    return build("drive", "v3", credentials=creds)


def download():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    svc     = _service()
    request = svc.files().get_media(fileId=FILE_ID)
    with open(DB_PATH, "wb") as fh:
        dl = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = dl.next_chunk()
    size_mb = DB_PATH.stat().st_size / 1_048_576
    log.info("DB téléchargée → %s (%.2f MB)", DB_PATH, size_mb)


def upload():
    svc   = _service()
    media = MediaFileUpload(str(DB_PATH), mimetype="application/x-sqlite3", resumable=True)
    svc.files().update(fileId=FILE_ID, media_body=media).execute()
    size_mb = DB_PATH.stat().st_size / 1_048_576
    log.info("DB uploadée → Drive (%.2f MB)", size_mb)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "download":
        download()
    elif cmd == "upload":
        upload()
    else:
        print("Usage: gdrive_sync.py download|upload")
        sys.exit(1)
