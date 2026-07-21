"""领域异常层次 — 零外部依赖。

统一的异常类型，便于调用方按类型精确处理。
继承关系保持与标准库兼容（CalculationError 继承 ValueError）。

用法：
    from core.exceptions import CalculationError, DataFetchError

    try:
        ...
    except CalculationError as e:
        sys.exit(EXIT_BAD_ARGS)
"""


class BerkshireError(Exception):
    """AI Berkshire 领域异常基类。"""


class ValidationError(BerkshireError):
    """输入参数校验失败（映射到退出码 2）。"""


class DataFetchError(BerkshireError, ConnectionError):
    """数据获取失败（网络/数据源异常，映射到退出码 1）。

    继承 ConnectionError 保持与现有 except ConnectionError 代码兼容。
    """


class CalculationError(BerkshireError, ValueError):
    """计算参数不合法（映射到退出码 2）。

    继承 ValueError 保持与现有 except ValueError 代码兼容。
    """
