# 环节：对象存储适配层；用途：把会话原文和运行快照压缩后存入私有 Bucket，并校验读取内容。
"""S3-compatible, content-addressed JSON objects; database rows keep only references."""

import asyncio
import gzip
import hashlib
import json


class S3JsonStore:
    def __init__(
        self,
        bucket: str,
        endpoint: str,
        region: str,
        access_key: str,
        secret_key: str,
        encryption_key: str = "",
    ):
        import boto3
        from cryptography.fernet import Fernet

        if not encryption_key:
            raise ValueError("BUCKET_ENCRYPTION_KEY is required for Bucket storage")
        self.bucket = bucket
        self.cipher = Fernet(encryption_key.encode("ascii"))
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

    async def put(self, kind: str, identifier: str, value: dict) -> dict:
        """先上传不可变对象，再让数据库提交引用；重试不会覆盖旧内容。"""

        def upload():
            raw = json.dumps(
                value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            digest = hashlib.sha256(raw).hexdigest()
            identity = hashlib.sha256(identifier.encode("utf-8")).hexdigest()[:24]
            key = f"v1/{kind}/{identity}/{digest}.json.gz"
            body = self.cipher.encrypt(gzip.compress(raw, mtime=0))
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=body,
                ContentType="application/octet-stream",
            )
            return {"__object_store_v1__": True, "key": key, "sha256": digest, "encrypted": True}

        return await asyncio.to_thread(upload)

    async def get(self, reference: dict) -> dict:
        def download():
            response = self.client.get_object(Bucket=self.bucket, Key=reference["key"])
            body = response["Body"].read()
            if reference.get("encrypted"):
                body = self.cipher.decrypt(body)
            raw = gzip.decompress(body)
            if hashlib.sha256(raw).hexdigest() != reference["sha256"]:
                raise ValueError("Bucket object checksum mismatch")
            return json.loads(raw)

        return await asyncio.to_thread(download)

    async def delete(self, reference: dict) -> None:
        await asyncio.to_thread(self.client.delete_object, Bucket=self.bucket, Key=reference["key"])

    async def ping(self) -> None:
        await asyncio.to_thread(
            self.client.list_objects_v2, Bucket=self.bucket, Prefix="v1/", MaxKeys=1
        )
