"""DELETE /files/{file_id} : delete the file from S3 and its metadata from DynamoDB."""
import os

import boto3

from common import get_user_id, response

s3 = boto3.client("s3")
table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
BUCKET = os.environ["BUCKET_NAME"]


def lambda_handler(event, context):
    user_id = get_user_id(event)
    file_id = event["pathParameters"]["file_id"]

    item = table.get_item(Key={"user_id": user_id, "file_id": file_id}).get("Item")
    if not item:
        return response(404, {"error": "File not found"})

    s3.delete_object(Bucket=BUCKET, Key=item["s3_key"])
    table.delete_item(Key={"user_id": user_id, "file_id": file_id})
    return response(200, {"message": "File deleted"})
