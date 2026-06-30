# Research Report Download + OSS Upload Design Spec

Date: 2026-06-30

## Overview

在已有的 `/api/research` 搜索接口基础上，新增研报 PDF 下载 + 阿里云 OSS 上传能力。调用者传入搜索结果中的研报元数据列表，接口同步逐个下载 PDF 并上传到 OSS，返回每篇的 oss_url。

内部 pipeline 接口，不面向前端。

## API Endpoint

### POST /api/research/download

**Request:**
```json
{
  "code": "301095",
  "reports": [
    {
      "info_code": "AP202606241823819112",
      "publish_date": "2026-06-24",
      "org_name": "中邮证券",
      "title": "EDA/PDA工具体系完善"
    }
  ]
}
```

- `code` (required, str): 6 位股票代码，用于构造 OSS 路径 `reports/{code}/`
- `reports` (required, list): 研报元数据列表，每条包含 info_code + 文件名所需信息

**Response:**
```json
{
  "total": 2,
  "success": 2,
  "failed": 0,
  "results": [
    {
      "info_code": "AP202606241823819112",
      "filename": "2026-06-24_中邮证券_EDA_PDA工具体系完善.pdf",
      "oss_url": "https://bucket.oss-cn-xxx.aliyuncs.com/reports/301095/2026-06-24_中邮证券_EDA_PDA工具体系完善.pdf",
      "status": "ok"
    }
  ]
}
```

**status 取值:**
- `ok` — 下载+上传成功
- `exists` — OSS 上已有同名文件，跳过下载，直接返回已有 url
- `failed` — 失败，附 `error` 字段说明原因

## Architecture

### File Structure

```
backend/app/
└── services/oss_service.py   # 新建：通用 OSS 上传封装
```

修改：
- `services/research_service.py` — 新增 download_and_upload_reports()
- `routers/research.py` — 新增 POST /download
- `config.py` — 新增 OSS 环境变量
- `requirements.txt` — 新增 oss2
- `.env.example` — 新增 OSS 配置模板

### oss_service.py

通用 OSS 上传服务，职责单一：

```python
def upload_bytes(data: bytes, object_key: str) -> str:
    """上传字节流到 OSS，返回公开访问 URL"""

def object_exists(object_key: str) -> bool:
    """检查 OSS 上是否已有该文件"""

def get_public_url(object_key: str) -> str:
    """拼接公开访问 URL"""
```

从 config 读取：OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET, OSS_ENDPOINT, OSS_BUCKET。

### research_service.py 新增

```python
def download_and_upload_reports(reports: list[dict], code: str) -> list[dict]:
    """
    逐个下载 PDF → 上传 OSS。
    复用 _em_get 限流（每篇间隔 1s+）。
    流程：
    1. 构造 filename: {publish_date}_{org}_{title_sanitized}.pdf
    2. 检查 OSS 是否已存在 → 是则跳过，返回 status=exists
    3. 用 _em_get 下载 PDF（带 Referer header）
    4. 校验（status=200, content >= 1KB）
    5. 调 oss_service.upload_bytes() 上传
    6. 返回结果
    """
```

### OSS 路径规则

```
reports/{code}/{publish_date}_{org_name}_{title_sanitized}.pdf
```

例：`reports/301095/2026-06-24_中邮证券_EDA_PDA工具体系完善.pdf`

title 中的 `\/:*?"<>|` 替换为 `_`，截断 80 字符。

## Config Changes

`app/config.py` 新增：
```python
OSS_ACCESS_KEY_ID = os.getenv("OSS_ACCESS_KEY_ID", "")
OSS_ACCESS_KEY_SECRET = os.getenv("OSS_ACCESS_KEY_SECRET", "")
OSS_ENDPOINT = os.getenv("OSS_ENDPOINT", "")
OSS_BUCKET = os.getenv("OSS_BUCKET", "")
```

`.env.example` 新增：
```
OSS_ACCESS_KEY_ID=
OSS_ACCESS_KEY_SECRET=
OSS_ENDPOINT=oss-cn-shanghai.aliyuncs.com
OSS_BUCKET=your-bucket-name
```

`requirements.txt` 新增：
```
oss2
```

## Error Handling

| Scenario | Behavior |
|----------|----------|
| OSS 配置缺失（任一为空） | 503 + `{"detail": "OSS not configured"}` |
| PDF 下载 403 | 单条 `status: "failed"`, `error: "pdf_download_403"` |
| PDF 下载超时 | 单条 `status: "failed"`, `error: "pdf_download_timeout"` |
| PDF 内容 < 1KB | 单条 `status: "failed"`, `error: "pdf_invalid"` |
| OSS 上传失败 | 单条 `status: "failed"`, `error: "oss_upload_error"` |
| OSS 已存在同名文件 | 跳过下载，`status: "exists"`, 返回已有 oss_url |
| code 格式非法 | 422 (FastAPI validation) |
| reports 列表为空 | 422 (FastAPI validation) |

## Change Summary

1. **New** `app/services/oss_service.py` — 通用 OSS 上传
2. **Modify** `app/services/research_service.py` — 新增 download_and_upload_reports()
3. **Modify** `app/routers/research.py` — 新增 POST /download
4. **Modify** `app/config.py` — 加 4 个 OSS 环境变量
5. **Modify** `.env.example` — 加 OSS 配置模板
6. **Modify** `requirements.txt` — 加 oss2
