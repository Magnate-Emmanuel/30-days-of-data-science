from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

import requests
from rich.console import Console
from tqdm import tqdm

from .util import sha256_file, ensure_dir

console = Console()

def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def download_csv(url: str, out_path: Path, headers: Optional[Dict[str, str]] = None, max_mb: Optional[int] = None) -> Dict:
    """Stream-download a CSV to out_path with atomic rename + manifest data."""
    ensure_dir(out_path.parent)
    tmp_path = out_path.with_suffix(out_path.suffix + ".part")

    h = headers or {}
    with requests.get(url, headers=h, stream=True, timeout=120) as r:
        r.raise_for_status()
        total = r.headers.get("Content-Length")
        total_bytes = int(total) if total and total.isdigit() else None

        if max_mb is not None and total_bytes is not None:
            if total_bytes > max_mb * 1024 * 1024:
                raise RuntimeError(f"Remote file is {total_bytes/1024/1024:.1f} MB which exceeds --max-mb={max_mb}.")

        chunk = 1024 * 1024
        pbar = tqdm(total=total_bytes, unit="B", unit_scale=True, desc=f"Downloading {out_path.name}")
        bytes_written = 0

        with tmp_path.open("wb") as f:
            for part in r.iter_content(chunk_size=chunk):
                if not part:
                    continue
                f.write(part)
                bytes_written += len(part)
                pbar.update(len(part))
                if max_mb is not None and bytes_written > max_mb * 1024 * 1024:
                    raise RuntimeError(f"Download exceeded --max-mb={max_mb} MB; aborting.")
        pbar.close()

    os.replace(tmp_path, out_path)

    manifest = {
        "fetched_at_utc": _now_utc_iso(),
        "url": url,
        "path": str(out_path),
        "nbytes": out_path.stat().st_size,
        "sha256": sha256_file(out_path),
    }
    return manifest

def write_manifest(manifest: Dict, manifest_path: Path) -> None:
    ensure_dir(manifest_path.parent)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
