"""Helpers shared by all Lambda functions."""
import json


def response(status, body):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body, default=str),
    }


def get_user_id(event):
    """User ID (Cognito 'sub') taken from the verified JWT claims."""
    return event["requestContext"]["authorizer"]["claims"]["sub"]
