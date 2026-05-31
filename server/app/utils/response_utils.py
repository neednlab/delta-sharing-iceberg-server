"""
NDJSON 流式响应生成工具模块

将 generate_ndjson_response 函数从 query.py 提取为可复用工具，
支持 Parquet 和 Delta 双格式的 NDJSON 流式响应生成。
"""

import json
from typing import Optional

from fastapi.responses import StreamingResponse

from app.core.delta_capabilities import (
    EndStreamAction,
    ResponseFormat,
    DeltaProtocol,
    DeltaMetadata,
    DeltaFileAction,
)
from app.models.query import Protocol, Metadata


def generate_ndjson_response(
    protocol: Protocol,
    metadata: Metadata,
    files: list,
    config,
    delta_table_version: int,
    capabilities=None,
    min_url_expiration: Optional[int] = None,
    response_format: ResponseFormat = ResponseFormat.PARQUET,
) -> StreamingResponse:
    """生成 NDJSON 格式的流式响应。

    支持 Parquet 和 Delta 两种响应格式，根据 response_format 参数动态切换。
    当 capabilities 指定 include_end_stream_action 时，在响应末尾追加
    endStreamAction 行。

    Args:
        protocol: 协议版本对象。
        metadata: 表元数据对象。
        files: 文件列表。
        config: 全局配置对象。
        delta_table_version: Delta 表版本号。
        capabilities: Delta Sharing Capabilities 对象。
        min_url_expiration: 响应中 URL 的最早过期时间戳。
        response_format: 响应格式，PARQUET 或 DELTA。

    Returns:
        StreamingResponse: NDJSON 格式的流式响应。
    """

    def generate():
        if response_format == ResponseFormat.DELTA:
            delta_protocol = DeltaProtocol()
            yield json.dumps(delta_protocol.to_delta_dict(), ensure_ascii=False) + "\n"

            delta_metadata = DeltaMetadata(
                id=metadata.id,
                size=metadata.size,
                num_files=metadata.numFiles,
            )
            yield json.dumps(delta_metadata.to_delta_dict(), ensure_ascii=False) + "\n"

            for file_data in files:
                delta_file = DeltaFileAction(
                    url=file_data.get("url"),
                    id=file_data.get("id"),
                    partition_values=file_data.get("partitionValues", {}),
                    size=file_data.get("size"),
                    stats=file_data.get("stats"),
                    version=file_data.get("version"),
                    timestamp=file_data.get("timestamp"),
                    expiration_timestamp=file_data.get("expirationTimestamp"),
                )
                yield json.dumps(delta_file.to_delta_dict(), ensure_ascii=False) + "\n"
        else:
            yield (json.dumps({"protocol": protocol.model_dump()}, ensure_ascii=False) + "\n")
            yield (json.dumps({"metaData": metadata.model_dump()}, ensure_ascii=False) + "\n")

            for file_data in files:
                yield json.dumps({"file": file_data}, ensure_ascii=False) + "\n"

        if capabilities and capabilities.include_end_stream_action:
            end_stream_action = EndStreamAction(min_url_expiration_timestamp=min_url_expiration)
            yield json.dumps(end_stream_action.to_delta_dict()) + "\n"

    response_headers = {
        "Delta-Table-Version": str(delta_table_version),
        "Content-Type": "application/x-ndjson; charset=utf-8",
    }

    if capabilities:
        response_headers["Delta-Sharing-Capabilities"] = capabilities.to_response_header()

    return StreamingResponse(
        generate(), media_type="application/x-ndjson", headers=response_headers
    )
