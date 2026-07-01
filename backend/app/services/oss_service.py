"""
OSS service — 阿里云 OSS 通用上传封装。
"""

import logging

import oss2

from app.config import (
    OSS_ACCESS_KEY_ID,
    OSS_ACCESS_KEY_SECRET,
    OSS_BUCKET,
    OSS_ENDPOINT,
)

logger = logging.getLogger(__name__)

_bucket = None


def _get_bucket() -> oss2.Bucket:
    """懒初始化 OSS Bucket 实例（模块级单例）"""
    global _bucket
    if _bucket is None:
        auth = oss2.Auth(OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET)
        _bucket = oss2.Bucket(auth, OSS_ENDPOINT, OSS_BUCKET)
    return _bucket


def is_configured() -> bool:
    """检查 OSS 配置是否完整"""
    return all([OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET, OSS_ENDPOINT, OSS_BUCKET])


def object_exists(object_key: str) -> bool:
    """检查 OSS 上是否已有该文件"""
    try:
        return _get_bucket().object_exists(object_key)
    except Exception as e:
        logger.warning("OSS object_exists check failed for %s: %s", object_key, e)
        return False


def get_public_url(object_key: str) -> str:
    """拼接公开访问 URL"""
    endpoint = OSS_ENDPOINT.replace("https://", "").replace("http://", "")
    return f"https://{OSS_BUCKET}.{endpoint}/{object_key}"


def upload_bytes(data: bytes, object_key: str) -> str:
    """
    上传字节流到 OSS（标准存储类型，可直接读取）。
    返回公开访问 URL。
    """
    bucket = _get_bucket()
    headers = {"x-oss-storage-class": "Standard"}
    bucket.put_object(object_key, data, headers=headers)
    return get_public_url(object_key)


def sign_url(object_key: str, expires: int = 3600) -> str:
    """
    生成临时签名 GET URL（用于私有 bucket 的外部读取，如 MinerU 拉取 PDF）。

    Args:
        object_key: OSS 对象路径
        expires: 过期秒数，默认 1 小时
    """
    return _get_bucket().sign_url("GET", object_key, expires)
