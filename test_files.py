import json

import boto3

from conftest import BUCKET, make_event


def add_file(table, user_id, file_id, name="a.txt"):
    key = f"{user_id}/{file_id}-{name}"
    boto3.client("s3", region_name="us-east-1").put_object(Bucket=BUCKET, Key=key, Body=b"hi")
    table.put_item(
        Item={
            "user_id": user_id,
            "file_id": file_id,
            "file_name": name,
            "s3_key": key,
            "size": 2,
            "content_type": "text/plain",
            "uploaded_at": "2026-01-01T00:00:00+00:00",
        }
    )


def test_list_returns_only_own_files(load, aws):
    list_files = load("list_files")
    add_file(aws, "user-a", "1")
    add_file(aws, "user-b", "2")

    result = list_files.lambda_handler(make_event("user-a"), None)
    items = json.loads(result["body"])

    assert result["statusCode"] == 200
    assert [i["file_id"] for i in items] == ["1"]


def test_download_own_file(load, aws):
    download = load("download")
    add_file(aws, "user-a", "1")
    result = download.lambda_handler(make_event("user-a", file_id="1"), None)
    assert result["statusCode"] == 200
    assert "download_url" in json.loads(result["body"])


def test_cannot_download_other_users_file(load, aws):
    download = load("download")
    add_file(aws, "user-b", "2")
    result = download.lambda_handler(make_event("user-a", file_id="2"), None)
    assert result["statusCode"] == 404


def test_delete_removes_object_and_metadata(load, aws):
    delete = load("delete")
    add_file(aws, "user-a", "1")
    result = delete.lambda_handler(make_event("user-a", file_id="1"), None)

    assert result["statusCode"] == 200
    assert "Item" not in aws.get_item(Key={"user_id": "user-a", "file_id": "1"})
    objects = boto3.client("s3", region_name="us-east-1").list_objects_v2(Bucket=BUCKET)
    assert objects["KeyCount"] == 0


def test_cannot_delete_other_users_file(load, aws):
    delete = load("delete")
    add_file(aws, "user-b", "2")
    result = delete.lambda_handler(make_event("user-a", file_id="2"), None)
    assert result["statusCode"] == 404
