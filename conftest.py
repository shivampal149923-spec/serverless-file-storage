import importlib
import json
import os
import sys

import boto3
import pytest
from moto import mock_aws

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas"))

REGION = "us-east-1"
BUCKET = "test-bucket"
TABLE = "FilesTable"


@pytest.fixture
def aws(monkeypatch):
    """Fake AWS (S3 + DynamoDB) so tests never touch a real account."""
    for key, value in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "AWS_DEFAULT_REGION": REGION,
        "TABLE_NAME": TABLE,
        "BUCKET_NAME": BUCKET,
    }.items():
        monkeypatch.setenv(key, value)

    with mock_aws():
        boto3.client("s3", region_name=REGION).create_bucket(Bucket=BUCKET)
        ddb = boto3.resource("dynamodb", region_name=REGION)
        ddb.create_table(
            TableName=TABLE,
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": "user_id", "AttributeType": "S"},
                {"AttributeName": "file_id", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "user_id", "KeyType": "HASH"},
                {"AttributeName": "file_id", "KeyType": "RANGE"},
            ],
        )
        yield ddb.Table(TABLE)


@pytest.fixture
def load(aws):
    """Import a Lambda module fresh, inside the mocked AWS environment."""

    def _load(name):
        module = importlib.import_module(name)
        return importlib.reload(module)

    return _load


def make_event(user_id, body=None, file_id=None):
    event = {"requestContext": {"authorizer": {"claims": {"sub": user_id}}}}
    if body is not None:
        event["body"] = json.dumps(body)
    if file_id:
        event["pathParameters"] = {"file_id": file_id}
    return event
