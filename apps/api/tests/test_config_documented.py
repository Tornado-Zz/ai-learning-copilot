"""配置项与 .env.example 必须一一对应。

背景：`DEEPSEEK_MODEL_COMPLEX` 曾在两份 `.env.example`、README 与架构文档里被宣传，
但代码里**从未读取**——运维改了环境变量却什么都不发生，这类沉默失效极难排查。
这条测试保证：文档里出现的每个键，Settings 里都有；Settings 的每个字段，文档里都写了。
"""

from __future__ import annotations

import re
from pathlib import Path

from app.core.config import API_DIR, Settings

# 只用于本地测试、不属于运行时配置的键（当前没有，留作显式扩展点）。
EXEMPT_KEYS: set[str] = set()


def _env_keys(path: Path) -> set[str]:
    """读取 .env.example 里的键（忽略注释与空行）。"""
    text = path.read_text(encoding='utf-8')
    return set(re.findall(r'^([A-Z][A-Z0-9_]*)', text, re.M))


def _settings_keys() -> set[str]:
    """Settings 的字段名转成环境变量名（大写）。"""
    return {name.upper() for name in Settings.model_fields}


def test_api_env_example_matches_settings_fields() -> None:
    """后端示例文件与 Settings 必须完全一致。"""
    documented = _env_keys(API_DIR / '.env.example') - EXEMPT_KEYS
    declared = _settings_keys() - EXEMPT_KEYS
    assert documented == declared, (
        f'只在 .env.example 里出现（代码不读，等于空旋钮）: {sorted(documented - declared)}; '
        f'只在 Settings 里出现（文档没写）: {sorted(declared - documented)}'
    )


# 根目录 .env.example 同时服务三件事：后端配置、docker compose 的 Postgres 账号、
# 前端构建期变量。这三类不属于 Settings，但都是真实被读取的键。
ROOT_NON_APP_PREFIXES = ('POSTGRES_',)
ROOT_NON_APP_KEYS = {'PORT', 'NEXT_PUBLIC_API_BASE_URL'}


def test_root_env_example_only_repeats_api_keys() -> None:
    """根目录示例里，除了 compose 与前端变量，其余键都必须是后端真实读取的。"""
    root_keys = _env_keys(Path(__file__).resolve().parents[3] / '.env.example')
    declared = _settings_keys()
    unknown = {
        key
        for key in root_keys - declared
        if key not in ROOT_NON_APP_KEYS and not key.startswith(ROOT_NON_APP_PREFIXES)
    }
    assert not unknown, f'根示例含未声明的键: {sorted(unknown)}'