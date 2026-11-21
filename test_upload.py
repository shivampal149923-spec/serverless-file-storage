import json

from conftest import make_event


def test_valid_upload_returns_url_and_saves_metadata(load, aws):
    upload = load("upload")
    event = make_event(
        "user-a",
        {"file_name": "report.pdf", "content_type": "application/pdf", "size": 1000},
    )
    result = upload.lambda_handler(event, None)
    body = json.loads(result["body"])

    assert result["statusCode"] == 200
    assert "upload_url" in body
    assert aws.get_item(Key={"user_id": "user-a", "file_id": body["file_id"]}).get("Item")


def test_invalid_file_type_rejected(load):
    upload = load("upload")
    event = make_event(
        "user-a",
        {"file_name": "virus.exe", "content_type": "application/x-msdownload", "size": 10},
    )
    assert upload.lambda_handler(event, None)["statusCode"] == 400


def test_file_too_large_rejected(load):
    upload = load("upload")
    event = make_event(
        "user-a",
        {"file_name": "big.pdf", "content_type": "application/pdf", "size": 999_999_999},
    )
    assert upload.lambda_handler(event, None)["statusCode"] == 400


def test_bad_json_rejected(load):
    upload = load("upload")
    event = make_event("user-a")
    event["body"] = "not json"
    assert upload.lambda_handler(event, None)["statusCode"] == 400
