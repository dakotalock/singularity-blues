"""Cloudflare R2 (S3-compatible) for voiced wavs. Optional: if unset, stay local-only."""

from __future__ import annotations

import os
from pathlib import Path

PREFIX = "tts/"


def configured() -> bool:
    return bool(
        os.environ.get("R2_ACCOUNT_ID", "").strip()
        and os.environ.get("R2_ACCESS_KEY_ID", "").strip()
        and os.environ.get("R2_SECRET_ACCESS_KEY", "").strip()
        and os.environ.get("R2_BUCKET", "").strip()
    )


def object_key(filename: str) -> str:
    return PREFIX + Path(filename).name


def _client():
    import boto3
    from botocore.config import Config

    account = os.environ["R2_ACCOUNT_ID"].strip()
    endpoint = os.environ.get("R2_ENDPOINT", "").strip() or f"https://{account}.r2.cloudflarestorage.com"
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"].strip(),
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"].strip(),
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )


def put_file(path: Path) -> bool:
    if not configured() or not path.is_file():
        return False
    try:
        _client().upload_file(str(path), os.environ["R2_BUCKET"].strip(), object_key(path.name))
        return True
    except Exception:
        return False


def get_bytes(filename: str) -> bytes | None:
    if not configured():
        return None
    name = Path(filename).name
    if not name or name != filename and "/" in filename:
        name = Path(filename).name
    try:
        obj = _client().get_object(Bucket=os.environ["R2_BUCKET"].strip(), Key=object_key(name))
        return obj["Body"].read()
    except Exception:
        return None
