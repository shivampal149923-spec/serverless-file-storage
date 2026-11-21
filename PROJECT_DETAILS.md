# Serverless File Storage System: Detailed Documentation

> **Note:** the working code is in the repository folders (`backend/`, `frontend/`, `infra/`). The snippets below are simplified for explanation, so the repo files are the source of truth.

This document extends the main [README](../README.md) with the design details, data model, sample code, deployment files, testing approach and learning outcomes of the project.

---

## 1. Abstract

The Serverless File Storage System is a cloud-based application that lets authenticated users securely upload, store, retrieve and delete files without any server provisioning or maintenance. It uses managed AWS services: **Amazon S3** for object storage, **AWS Lambda** for business logic, **Amazon API Gateway** for the REST interface, **Amazon DynamoDB** for file metadata and **Amazon Cognito** for authentication. Because every component is event-driven and pay-per-use, the system scales automatically and costs almost nothing when idle.

## 2. Scope

**In scope**
- User registration and login
- Upload, list, download and delete of personal files
- Metadata tracking per file
- Automated deployment through GitHub Actions

**Out of scope (current version)**
- Real-time collaboration or file editing
- File sharing between users
- Mobile-native application

## 3. Requirements

### Functional requirements

| ID | Requirement |
|---|---|
| FR1 | A user can create an account and log in |
| FR2 | A logged-in user can upload a file |
| FR3 | A user can view a list of their own files |
| FR4 | A user can download a file they own |
| FR5 | A user can delete a file they own |
| FR6 | A user must not be able to see or access another user's files |

### Non-functional requirements

| Requirement | How it is met |
|---|---|
| Scalability | Lambda and S3 scale automatically with load |
| Availability | S3 offers 99.99% availability and 11 nines durability |
| Security | Cognito auth, IAM least privilege, encryption, private bucket |
| Cost | Pay-per-request pricing, lifecycle rules |
| Maintainability | Infrastructure as Code, CI/CD, no servers to patch |

## 4. Detailed Design

### 4.1 Why pre-signed URLs?

Sending large files through API Gateway and Lambda is slow and limited by payload size (API Gateway caps payloads at about 10 MB, Lambda at 6 MB synchronous). Instead:

1. The client asks the API for permission to upload.
2. Lambda generates a **pre-signed URL**, a temporary link signed with the Lambda role's credentials.
3. The client uploads **directly to S3** using that link.

This removes the Lambda bottleneck, supports large files, and lowers cost.

### 4.2 S3 key design

Files are stored under a per-user prefix so access can be isolated:

```
s3://<bucket-name>/<user_id>/<file_id>-<original_filename>
```

Example: `s3://file-store-prod/a1b2c3/9f8e7d-report.pdf`

### 4.3 DynamoDB data model

**Table name:** `FilesTable`

| Attribute | Type | Role | Description |
|---|---|---|---|
| `user_id` | String | Partition key | Cognito user ID (`sub`) |
| `file_id` | String | Sort key | Unique ID (UUID) |
| `file_name` | String | | Original file name |
| `s3_key` | String | | Full object key in S3 |
| `size` | Number | | File size in bytes |
| `content_type` | String | | MIME type |
| `uploaded_at` | String | | ISO 8601 timestamp |

Because `user_id` is the partition key, listing a user's files is a single efficient `Query`, with no table scan.

### 4.4 Authentication flow

1. User signs up or logs in through the Cognito User Pool.
2. Cognito returns a **JWT** (ID/access token).
3. The client sends the token in the `Authorization` header.
4. API Gateway's Cognito authorizer validates it before Lambda runs.
5. Lambda reads the user's ID from the token claims, so users can never pass someone else's ID.

## 5. Sample Implementation

> These are starter examples. Adapt names, regions and error handling to your project.

### 5.1 Lambda: generate upload URL (Python)

```python
import json
import os
import uuid
from datetime import datetime, timezone

import boto3

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["TABLE_NAME"])
BUCKET = os.environ["BUCKET_NAME"]

MAX_SIZE = 50 * 1024 * 1024  # 50 MB
ALLOWED_TYPES = {"image/png", "image/jpeg", "application/pdf", "text/plain"}


def response(status, body):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }


def lambda_handler(event, context):
    user_id = event["requestContext"]["authorizer"]["claims"]["sub"]
    body = json.loads(event.get("body") or "{}")

    file_name = body.get("file_name")
    content_type = body.get("content_type")
    size = int(body.get("size", 0))

    if not file_name or content_type not in ALLOWED_TYPES:
        return response(400, {"error": "Invalid file name or type"})
    if size <= 0 or size > MAX_SIZE:
        return response(400, {"error": "File size not allowed"})

    file_id = str(uuid.uuid4())
    s3_key = f"{user_id}/{file_id}-{file_name}"

    upload_url = s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": BUCKET, "Key": s3_key, "ContentType": content_type},
        ExpiresIn=300,  # link valid for 5 minutes
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
```

### 5.2 Lambda: list files

```python
import json
import os

import boto3
from boto3.dynamodb.conditions import Key

table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])


def lambda_handler(event, context):
    user_id = event["requestContext"]["authorizer"]["claims"]["sub"]
    result = table.query(KeyConditionExpression=Key("user_id").eq(user_id))
    return {
        "statusCode": 200,
        "headers": {"Access-Control-Allow-Origin": "*"},
        "body": json.dumps(result["Items"], default=str),
    }
```

### 5.3 Frontend: uploading a file

```javascript
async function uploadFile(file, token) {
  // 1. Ask the API for a pre-signed URL
  const res = await fetch(`${API_URL}/upload-url`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: token },
    body: JSON.stringify({
      file_name: file.name,
      content_type: file.type,
      size: file.size,
    }),
  });
  const { upload_url } = await res.json();

  // 2. Upload directly to S3
  await fetch(upload_url, {
    method: "PUT",
    headers: { "Content-Type": file.type },
    body: file,
  });
}
```

### 5.4 IAM policy for Lambda (least privilege)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::YOUR_BUCKET_NAME/*"
    },
    {
      "Effect": "Allow",
      "Action": ["dynamodb:PutItem", "dynamodb:Query", "dynamodb:GetItem", "dynamodb:DeleteItem"],
      "Resource": "arn:aws:dynamodb:REGION:ACCOUNT_ID:table/FilesTable"
    }
  ]
}
```

### 5.5 S3 CORS configuration (needed for browser uploads)

```json
[
  {
    "AllowedHeaders": ["*"],
    "AllowedMethods": ["PUT", "GET"],
    "AllowedOrigins": ["*"],
    "ExposeHeaders": []
  }
]
```

> For production, replace `"*"` in `AllowedOrigins` with your real frontend domain.

### 5.6 Infrastructure template (AWS SAM, starter)

```yaml
AWSTemplateFormatVersion: "2010-09-09"
Transform: AWS::Serverless-2016-10-31
Description: Serverless File Storage System

Globals:
  Function:
    Runtime: python3.12
    Timeout: 10
    Environment:
      Variables:
        TABLE_NAME: !Ref FilesTable
        BUCKET_NAME: !Ref FileBucket

Resources:
  FileBucket:
    Type: AWS::S3::Bucket
    Properties:
      BucketEncryption:
        ServerSideEncryptionConfiguration:
          - ServerSideEncryptionByDefault:
              SSEAlgorithm: AES256
      PublicAccessBlockConfiguration:
        BlockPublicAcls: true
        BlockPublicPolicy: true
        IgnorePublicAcls: true
        RestrictPublicBuckets: true
      CorsConfiguration:
        CorsRules:
          - AllowedMethods: [PUT, GET]
            AllowedOrigins: ["*"]
            AllowedHeaders: ["*"]

  FilesTable:
    Type: AWS::DynamoDB::Table
    Properties:
      BillingMode: PAY_PER_REQUEST
      AttributeDefinitions:
        - AttributeName: user_id
          AttributeType: S
        - AttributeName: file_id
          AttributeType: S
      KeySchema:
        - AttributeName: user_id
          KeyType: HASH
        - AttributeName: file_id
          KeyType: RANGE

  UserPool:
    Type: AWS::Cognito::UserPool
    Properties:
      AutoVerifiedAttributes: [email]
      UsernameAttributes: [email]

  UserPoolClient:
    Type: AWS::Cognito::UserPoolClient
    Properties:
      UserPoolId: !Ref UserPool
      GenerateSecret: false
      ExplicitAuthFlows: [ALLOW_USER_PASSWORD_AUTH, ALLOW_REFRESH_TOKEN_AUTH]

  Api:
    Type: AWS::Serverless::Api
    Properties:
      StageName: prod
      Auth:
        DefaultAuthorizer: CognitoAuth
        Authorizers:
          CognitoAuth:
            UserPoolArn: !GetAtt UserPool.Arn
      Cors:
        AllowMethods: "'GET,POST,DELETE,OPTIONS'"
        AllowHeaders: "'Content-Type,Authorization'"
        AllowOrigin: "'*'"

  UploadFunction:
    Type: AWS::Serverless::Function
    Properties:
      Handler: upload.lambda_handler
      CodeUri: backend/lambdas/
      Policies:
        - S3WritePolicy:
            BucketName: !Ref FileBucket
        - DynamoDBCrudPolicy:
            TableName: !Ref FilesTable
      Events:
        UploadApi:
          Type: Api
          Properties:
            RestApiId: !Ref Api
            Path: /upload-url
            Method: post

  ListFunction:
    Type: AWS::Serverless::Function
    Properties:
      Handler: list_files.lambda_handler
      CodeUri: backend/lambdas/
      Policies:
        - DynamoDBReadPolicy:
            TableName: !Ref FilesTable
      Events:
        ListApi:
          Type: Api
          Properties:
            RestApiId: !Ref Api
            Path: /files
            Method: get

Outputs:
  ApiUrl:
    Description: API Gateway endpoint
    Value: !Sub "https://${Api}.execute-api.${AWS::Region}.amazonaws.com/prod"
```

### 5.7 GitHub Actions workflow (`.github/workflows/deploy.yml`)

```yaml
name: Deploy Serverless File Storage

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - uses: aws-actions/setup-sam@v2

      - uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ap-south-1

      - name: Install test dependencies
        run: pip install pytest boto3 moto

      - name: Run tests
        run: pytest backend/tests

      - name: Build
        run: sam build --template infra/template.yaml

      - name: Deploy
        run: sam deploy --no-confirm-changeset --no-fail-on-empty-changeset --stack-name file-storage --capabilities CAPABILITY_IAM --resolve-s3
```

> Tip: for better security, use GitHub's OIDC integration with an IAM role instead of long-lived access keys.

## 6. Testing Strategy

| Type | What is tested | Tool |
|---|---|---|
| Unit tests | Lambda logic, validation, error cases | `pytest`, `moto` (mock AWS) |
| Integration tests | API Gateway + Lambda + S3 together | Postman, `curl` |
| Security tests | Unauthenticated access returns 401; user A cannot access user B's files | Postman |
| Load test (optional) | Behaviour under many concurrent uploads | Artillery / Locust |

### Sample test cases

| # | Test case | Expected result |
|---|---|---|
| 1 | Upload without a token | `401 Unauthorized` |
| 2 | Upload a `.exe` file | `400 Invalid file type` |
| 3 | Upload a file above the size limit | `400 File size not allowed` |
| 4 | Valid upload | `200` with a pre-signed URL |
| 5 | List files as user A | Only user A's files returned |
| 6 | Use an expired pre-signed URL | `403 Forbidden` from S3 |

## 7. Challenges and Solutions

| Challenge | Solution |
|---|---|
| Large files exceed Lambda/API Gateway payload limits | Use pre-signed URLs so files go directly to S3 |
| Browser upload blocked by CORS errors | Configure CORS on both S3 and API Gateway |
| Users accessing each other's files | Derive `user_id` from the verified JWT and store files under per-user prefixes |
| Lambda cold start delays | Keep functions small, use lightweight runtimes, reuse boto3 clients outside the handler |
| Leaking AWS credentials in the repo | Use GitHub Secrets or OIDC, and add a `.gitignore` |

## 8. Limitations

- Pre-signed upload URLs allow only one object per URL; multi-file upload needs several URLs
- Files above 5 GB need S3 multipart upload (not implemented)
- Lambda cold starts can add a small delay to the first request after inactivity
- Vendor lock-in to AWS services

## 9. Result and Observations

- Files upload directly to S3 regardless of Lambda payload limits
- Each user sees only their own files
- With no traffic, running cost is close to zero (S3 storage only)
- A push to `main` redeploys the whole stack automatically

## 10. Learning Outcomes

- Designing event-driven, serverless architectures
- Secure authentication with Cognito and JWT
- Applying least-privilege IAM policies
- Modelling data in DynamoDB with partition and sort keys
- Infrastructure as Code with AWS SAM
- Building CI/CD pipelines with GitHub Actions

## 11. Possible Viva / Interview Questions

1. **What does "serverless" mean?** You don't manage servers; the cloud provider runs and scales the infrastructure, and you pay per use.
2. **Why use pre-signed URLs instead of uploading through Lambda?** To avoid payload limits, reduce latency and cost, and keep Lambda out of the data path.
3. **How do you stop one user from accessing another's files?** The user ID comes from the validated JWT, files are stored under per-user prefixes, and DynamoDB queries are scoped to that user.
4. **Why DynamoDB for metadata instead of S3 alone?** DynamoDB allows fast queries (list, filter, sort) on file attributes, which S3 listing cannot do efficiently.
5. **What is a Lambda cold start?** The delay when AWS initialises a new execution environment for a function that has been idle.
6. **How is the system secured?** Cognito authentication, HTTPS, encryption at rest, blocked public bucket access, least-privilege IAM and short-lived URLs.
7. **How would you scale this to millions of users?** The services already scale automatically; add caching, CloudFront for downloads, and monitor DynamoDB and Lambda concurrency limits.

## 12. References

- [AWS Lambda Documentation](https://docs.aws.amazon.com/lambda/)
- [Amazon S3 Pre-signed URLs](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html)
- [Amazon DynamoDB Developer Guide](https://docs.aws.amazon.com/amazondynamodb/)
- [Amazon Cognito Documentation](https://docs.aws.amazon.com/cognito/)
- [AWS SAM Documentation](https://docs.aws.amazon.com/serverless-application-model/)
- [GitHub Actions Documentation](https://docs.github.com/actions)
