"""GET /files : list the logged-in user's files."""
import os

import boto3
from boto3.dynamodb.conditions import Key

from common import get_user_id, response

table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])


def lambda_handler(event, context):
    user_id = get_user_id(event)
    result = table.query(KeyConditionExpression=Key("user_id").eq(user_id))
    items = sorted(result["Items"], key=lambda i: i["uploaded_at"], reverse=True)
    return response(200, items)
