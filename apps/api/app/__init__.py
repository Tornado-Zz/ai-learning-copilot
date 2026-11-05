"""AI Learning Copilot backend API package."""

# 这个常量会出现在 GET /health 的 version 字段和 OpenAPI 的 info.version 上。
# 本项目不作为发行包装入（[tool.uv] package = false），因此无法用 importlib.metadata
# 读 pyproject 的版本；scripts/docs-consistency-check.mjs 会断言它与 pyproject 一致。
__version__ = "0.1.30"
SERVICE_NAME = "ai-learning-copilot-api"
