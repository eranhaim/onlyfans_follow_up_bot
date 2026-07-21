import logging
import os
import tempfile
import uuid

import boto3
from botocore.exceptions import ClientError

from app.config import settings

logger = logging.getLogger(__name__)


def _get_s3_client():
    return boto3.client(
        "s3",
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_region,
    )


def s3_ready() -> bool:
    return bool(settings.aws_access_key_id and settings.aws_secret_access_key)


def upload_video(account_id: int, filename: str, file_bytes: bytes) -> str:
    ext = os.path.splitext(filename)[1] or ".mp4"
    s3_key = f"videos/{account_id}/{uuid.uuid4().hex}{ext}"
    client = _get_s3_client()
    client.put_object(
        Bucket=settings.aws_s3_bucket,
        Key=s3_key,
        Body=file_bytes,
        ContentType=f"video/{ext.lstrip('.')}",
    )
    return s3_key


def download_video(s3_key: str) -> str:
    """Download video to a temp file and return the path."""
    client = _get_s3_client()
    ext = os.path.splitext(s3_key)[1] or ".mp4"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
    try:
        client.download_fileobj(settings.aws_s3_bucket, s3_key, tmp)
        tmp.close()
        return tmp.name
    except Exception:
        tmp.close()
        os.unlink(tmp.name)
        raise


def delete_video(s3_key: str) -> None:
    try:
        client = _get_s3_client()
        client.delete_object(Bucket=settings.aws_s3_bucket, Key=s3_key)
    except ClientError as e:
        logger.warning("Failed to delete S3 object %s: %s", s3_key, e)
