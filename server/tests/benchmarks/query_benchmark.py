"""
查询性能基准测试脚本

该模块提供独立的端到端查询基准测试，通过 HTTP 客户端直接调用
Delta Sharing Data Plane Query API，测量查询延迟。

使用方法:
    cd server
    uv run .\\tests\\benchmarks\\query_benchmark.py
    uv run .\\tests\\benchmarks\\query_benchmark.py --share my_share --schema my_schema --table my_table
    uv run .\\tests\\benchmarks\\query_benchmark.py --credential path/to/profile.share
"""

import argparse
import json
import os
import sys
import time

import httpx


def load_credential(credential_path: str) -> dict:
    """从 credential JSON 文件读取 endpoint 和 bearerToken。

    凭证文件格式与 Delta Sharing profile JSON 一致：
        {
            "shareCredentialsVersion": 1,
            "endpoint": "http://localhost:8088/delta-sharing",
            "bearerToken": "...",
            "expirationTime": "..."
        }

    Args:
        credential_path: 凭证文件路径。

    Returns:
        包含 endpoint 和 bearerToken 的字典。

    Raises:
        SystemExit: 当文件不存在或格式不正确时以非 0 退出码退出。
    """
    if not os.path.isfile(credential_path):
        print(f"[ERROR] Credential file not found: {credential_path}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(credential_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(
            f"[ERROR] Invalid JSON in credential file '{credential_path}': {e}",
            file=sys.stderr,
        )
        sys.exit(1)

    endpoint = data.get("endpoint")
    bearer_token = data.get("bearerToken")

    if not endpoint:
        print(
            f"[ERROR] Missing 'endpoint' field in credential file '{credential_path}'",
            file=sys.stderr,
        )
        sys.exit(1)

    if not bearer_token:
        print(
            f"[ERROR] Missing 'bearerToken' field in credential file '{credential_path}'",
            file=sys.stderr,
        )
        sys.exit(1)

    return {"endpoint": endpoint.rstrip("/"), "bearerToken": bearer_token}


def build_query_url(endpoint: str, share: str, schema: str, table: str) -> str:
    """构建 Query API 的完整 URL。

    Args:
        endpoint: Data Plane 端点 URL。
        share: Share 名称。
        schema: Schema 名称。
        table: 表名称。

    Returns:
        完整的 Query API URL 字符串。
    """
    return f"{endpoint}/shares/{share}/schemas/{schema}/tables/{table}/query"


def heat_up(url: str, bearer_token: str, timeout: float = 120.0) -> bool:
    """发送预热请求，触发 lazy init 逻辑。

    发送一次查询请求并忽略响应内容，确保 server 端的懒加载
    （如 DLC API 连接初始化、COS 客户端初始化等）已完成。

    Args:
        url: Query API 完整 URL。
        bearer_token: 认证 Bearer Token。
        timeout: HTTP 请求超时时间（秒）。

    Returns:
        True 表示预热成功，False 表示预热失败。
    """
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "Content-Type": "application/json",
    }

    print(f"[INFO] Warming up: POST {url}", file=sys.stderr)
    warmup_start = time.perf_counter()
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, headers=headers, json={})
        warmup_elapsed = (time.perf_counter() - warmup_start) * 1000
        if response.status_code == 200:
            print(
                f"[INFO] Warm-up completed in {warmup_elapsed:.0f} ms (status={response.status_code})",
                file=sys.stderr,
            )
            return True
        else:
            print(
                f"[WARN] Warm-up returned status {response.status_code} in {warmup_elapsed:.0f} ms",
                file=sys.stderr,
            )
            return False
    except httpx.ConnectError as e:
        print(
            f"[ERROR] Cannot connect to server at {url}: {e}",
            file=sys.stderr,
        )
        return False
    except Exception as e:
        print(
            f"[ERROR] Warm-up request failed: {e}",
            file=sys.stderr,
        )
        return False


def run_benchmark(
    url: str, bearer_token: str, rounds: int = 3, timeout: float = 120.0
) -> dict:
    """运行基准测试，记录每次端到端查询耗时。

    连续发送 rounds 次正式查询请求，使用 time.perf_counter()
    记录每次的端到端耗时（毫秒），计算并返回统计信息。

    Args:
        url: Query API 完整 URL。
        bearer_token: 认证 Bearer Token。
        rounds: 正式测试轮数，默认为 3。
        timeout: 每次 HTTP 请求的超时时间（秒）。

    Returns:
        包含 runs、average_ms、min_ms、max_ms 的字典。

    Raises:
        SystemExit: 服务不可达或 credential 无效时以非 0 退出码退出。
    """
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "Content-Type": "application/json",
    }

    runs_ms = []

    for i in range(1, rounds + 1):
        print(
            f"[INFO] Benchmark run {i}/{rounds}: POST {url}",
            file=sys.stderr,
        )
        start = time.perf_counter()
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(url, headers=headers, json={})
            elapsed_ms = (time.perf_counter() - start) * 1000
            if response.status_code == 200:
                runs_ms.append(elapsed_ms)
                print(
                    f"[INFO] Run {i}/{rounds} completed in {elapsed_ms:.0f} ms (status={response.status_code})",
                    file=sys.stderr,
                )
            else:
                print(
                    f"[ERROR] Run {i}/{rounds} returned status {response.status_code} in {elapsed_ms:.0f} ms",
                    file=sys.stderr,
                )
                # 如果某次请求失败，仍然记录耗时，但继续尝试后续轮次
                runs_ms.append(elapsed_ms)
        except httpx.ConnectError as e:
            print(
                f"[ERROR] Cannot connect to server at {url}: {e}",
                file=sys.stderr,
            )
            sys.exit(1)
        except Exception as e:
            print(
                f"[ERROR] Benchmark request failed on run {i}/{rounds}: {e}",
                file=sys.stderr,
            )
            sys.exit(1)

    if not runs_ms:
        print("[ERROR] No successful benchmark runs", file=sys.stderr)
        sys.exit(1)

    return {
        "runs": [round(r, 1) for r in runs_ms],
        "average_ms": round(sum(runs_ms) / len(runs_ms), 1),
        "min_ms": round(min(runs_ms), 1),
        "max_ms": round(max(runs_ms), 1),
    }


def main():
    """程序入口函数。

    解析命令行参数，加载 credential，执行预热和基准测试，
    最后以 JSON 格式输出结果。
    """
    parser = argparse.ArgumentParser(
        description="Delta Sharing Query API Performance Benchmark"
    )
    parser.add_argument(
        "--credential",
        default=None,
        help="Path to credential JSON file (default: client/config/local.share relative to project root)",
    )
    parser.add_argument(
        "--share",
        default="needn_share",
        help="Share name (default: needn_share)",
    )
    parser.add_argument(
        "--schema",
        default="shared_cnslk",
        help="Schema name (default: shared_cnslk)",
    )
    parser.add_argument(
        "--table",
        default="s1000",
        help="Table name (default: s1000)",
    )
    args = parser.parse_args()

    # 确定 credential 文件路径
    if args.credential:
        credential_path = args.credential
    else:
        # 默认路径为项目根目录下的 client/config/local.share
        # 脚本位于 server/tests/benchmarks/ 下，项目根目录在 ../../../
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(script_dir, "..", "..", ".."))
        credential_path = os.path.join(project_root, "client", "config", "local.share")

    # 加载 credential
    cred = load_credential(credential_path)
    endpoint = cred["endpoint"]
    bearer_token = cred["bearerToken"]

    url = build_query_url(endpoint, args.share, args.schema, args.table)

    # 预热
    warmup_ok = heat_up(url, bearer_token)
    if not warmup_ok:
        print(
            "[WARN] Warm-up failed, proceeding with benchmark anyway...",
            file=sys.stderr,
        )

    # 运行基准测试
    result = run_benchmark(url, bearer_token)

    # 输出 JSON 结果到 stdout
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
