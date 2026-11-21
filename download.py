"""GET /files/{file_id} : return a short-lived pre-signed download URL."""
import os

import boto3

from common import get_user_id, response

s3 = boto3.client("s3")
table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
BUCKET = os.environ["BUCKET_NAME"]


def lambda_handler(event, context):
    user_id = get_user_id(event)
    file_id = event["pathParameters"]["file_id"]

    # Look up by (user_id, file_id): a user can only ever find their own files.
    item = table.get_item(Key={"user_id": user_id, "file_id": file_id}).get("Item")
    if not item:
        return response(404, {"error": "File not found"})

    url = s3.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": BUCKET,
            "Key": item["s3_key"],
            "ResponseContentDisposition": f'attachment; filename="{item["file_name"]}"',
        },
        ExpiresIn=300,
    )
    return response(200, {"download_url": url, "file_name": item["file_name"]})
