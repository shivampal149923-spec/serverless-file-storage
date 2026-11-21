"""POST /upload-url : validate the request and return a pre-signed S3 upload URL."""
import json
import os
import re
import uuid
from datetime import datetime, timezone

import boto3

from common import get_user_id, response

s3 = boto3.client("s3")
table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
BUCKET = os.environ["BUCKET_NAME"]

MAX_SIZE = 50 * 1024 * 1024  # 50 MB
ALLOWED_TYPES = {
    "image/png",
    "image/jpeg",
    "application/pdf",
    "text/plain",
}


def clean_name(name):
    name = os.path.basename(str(name))
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)[:100]


def lambda_handler(event, context):
    user_id = get_user_id(event)

    try:
        body = json.loads(event.get("body") or "{}")
        size = int(body.get("size", 0))
    except (ValueError, TypeError):
        return response(400, {"error": "Invalid request body"})

    file_name = body.get("file_name")
    content_type = body.get("content_type")

    if not file_name or content_type not in ALLOWED_TYPES:
        return response(400, {"error": "Invalid file name or file type"})
    if size <= 0 or size > MAX_SIZE:
        return response(400, {"error": "File size not allowed (max 50 MB)"})

    file_name = clean_name(file_name)
    file_id = str(uuid.uuid4())
    s3_key = f"{user_id}/{file_id}-{file_name}"

    upload_url = s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": BUCKET, "Key": s3_key, "ContentType": content_type},
        ExpiresIn=300,  # valid for 5 minutes
    )

    table.put_item(
        Item={
            "user_id": user_id,
            "file_id": file_id,
            "file_name": file_name,
            "s3_key": s3_key,
            "size": size,
            "content_type": content_type,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    return response(200, {"file_id": file_id, "upload_url": upload_url})
