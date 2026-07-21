#!/usr/bin/env python3
"""AI Berkshire 工具层共享基础设施。

提取各 tools/*.py 中重复的通用逻辑，减少维护成本：
    - 退出码常量（统一语义：0=成功 / 1=失败 / 2=参数错误）
    - 领域异常消费（core.exceptions → 退出码映射）
    - JSON 命令行参数解析（友好报错，抛 ValidationError）
    - curl 直连封装（绕过代理、跟随跳转、自动重试、超时控制、POST/binary/自定义UA）
    - @cli_entry 装饰器（统一异常捕获 → 退出码 + 友好消息）

用法（由其他 tools/ 脚本导入）：
    from utils import EXIT_OK, EXIT_FAIL, EXIT_BAD_ARGS, load_json_arg, cli_entry
    from utils import curl_get, curl_get_json, EDGAR_UA
"""

import functools
import json
import os
import shutil
import subprocess
import sys
import time

from core.config import CURL_RETRIES, CURL_RETRY_WAIT, CURL_TIMEOUT
from core.exceptions import (
    BerkshireError,
    CalculationError,
    DataFetchError,
    ValidationError,
)

# ---------------------------------------------------------------------------
# 统一退出码语义（供调用脚本判断）
# ---------------------------------------------------------------------------

EXIT_OK = 0  # 成功 / 验证通过
EXIT_FAIL = 1  # 失败 / 验证不通过
EXIT_BAD_ARGS = 2  # 参数错误（修正命令重试，不算验证失败）

# 别名：部分工具用 VERIFY_FAIL 表达"验证不通过"（语义等同 EXIT_FAIL）
EXIT_VERIFY_FAIL = EXIT_FAIL
EXIT_UNAVAILABLE = EXIT_FAIL  # 可选依赖缺失（如 matplotlib），调用方降级

# ---------------------------------------------------------------------------
# @cli_entry 装饰器（统一异常捕获 → 退出码 + 友好消息）
# ---------------------------------------------------------------------------


def cli_entry(func):
    """CLI 入口统一异常处理装饰器。

    捕获领域异常并映射到退出码：
        - ValidationError / CalculationError → 退出码 2（参数错误）
        - DataFetchError → 退出码 1（数据获取失败）
        - 其他 BerkshireError → 退出码 1

    用法：
        @cli_entry
        def main():
            ...
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (ValidationError, CalculationError) as e:
            print(f"❌ {e}", file=sys.stderr)
            sys.exit(EXIT_BAD_ARGS)
        except DataFetchError as e:
            print(f"❌ 数据获取失败: {e}", file=sys.stderr)
            sys.exit(EXIT_FAIL)
        except BerkshireError as e:
            print(f"❌ {e}", file=sys.stderr)
            sys.exit(EXIT_FAIL)

    return wrapper


# ---------------------------------------------------------------------------
# JSON 参数解析
# ---------------------------------------------------------------------------


def load_json_arg(raw: str, what: str, example: str):
    """解析命令行 JSON 参数；失败时抛 ValidationError（由 @cli_entry 统一处理退出码）。

    Args:
        raw: 用户传入的 JSON 字符串
        what: 参数名（用于错误提示，如 "--values"）
        example: 正确格式示例（帮助用户修正）

    Returns:
        解析后的 Python 对象（dict / list / ...）

    Raises:
        ValidationError: JSON 解析失败
    """
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValidationError(
            f"{what} 不是合法 JSON: {e}\n"
            f"   正确格式示例: {example}\n"
            f"   提示: shell 中整体用单引号包裹，内部键名用双引号"
        ) from e


# ---------------------------------------------------------------------------
# curl 直连封装（全工具统一入口）
# ---------------------------------------------------------------------------

_DEFAULT_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"

# SEC EDGAR 要求 User-Agent 带联系方式（filings_fetch / masters_portfolio 共用）
EDGAR_UA = os.environ.get("EDGAR_UA", "ai-berkshire-research-skill contact@ai-berkshire.local")

# 动态查找 curl 路径（Linux/macOS 兼容）
_CURL_PATH = shutil.which("curl") or "/usr/bin/curl"


def curl_get(
    url: str,
    *,
    post_data: str = None,
    ua: str = None,
    binary: bool = False,
    timeout: int = CURL_TIMEOUT,
    retries: int = CURL_RETRIES,
):
    """统一 curl 直连封装：绕过系统代理、跟随跳转、失败自动重试。

    Args:
        url: 请求地址
        post_data: 非空时发送 POST 表单（application/x-www-form-urlencoded）
        ua: 自定义 User-Agent（缺省使用浏览器 UA）
        binary: True 时返回原始 bytes（用于下载 PDF 等二进制文件）
        timeout: 单次请求超时（秒）
        retries: 失败后重试次数（0=不重试）

    Returns:
        响应体字符串（UTF-8 解码，失败时尝试 GBK）；binary=True 时返回 bytes

    Raises:
        DataFetchError: 所有重试均失败
    """
    last_err = None
    for attempt in range(retries + 1):
        try:
            cmd = [
                _CURL_PATH,
                "-s",
                "-L",
                "--noproxy",
                "*",
                "-H",
                f"User-Agent: {ua or _DEFAULT_UA}",
                url,
            ]
            if post_data is not None:
                cmd[1:1] = [
                    "-X",
                    "POST",
                    "-d",
                    post_data,
                    "-H",
                    "Content-Type: application/x-www-form-urlencoded",
                ]
            result = subprocess.run(cmd, capture_output=True, timeout=timeout + 5)
            if result.returncode == 0 and result.stdout:
                if binary:
                    return result.stdout
                try:
                    return result.stdout.decode("utf-8")
                except UnicodeDecodeError:
                    return result.stdout.decode("gbk", errors="replace")
            last_err = DataFetchError(f"请求失败 (curl 退出码 {result.returncode}): {url}")
        except subprocess.TimeoutExpired:
            last_err = DataFetchError(f"请求超时 (>{timeout}s): {url}")
        if attempt < retries:
            time.sleep(CURL_RETRY_WAIT)
    raise last_err


def curl_get_json(
    url: str, params: dict = None, *, post_data: str = None, ua: str = None, **kwargs
):
    """用 curl 获取并解析 JSON；params 会编码为查询字符串附加到 url。"""
    from urllib.parse import urlencode

    if params:
        url = f"{url}?{urlencode(params)}"
    return json.loads(curl_get(url, post_data=post_data, ua=ua, **kwargs))
