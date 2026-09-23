from __future__ import annotations

from typing import Literal

ProviderName = Literal["deepseek", "minimax", "glm"]

DEFAULT_PROVIDER_BASE_URLS: dict[ProviderName, str] = {
    "deepseek": "https://api.deepseek.com/v1",
    "minimax": "https://api.minimax.chat/v1",
    "glm": "https://open.bigmodel.cn/api/paas/v4",
}

DEFAULT_PROVIDER_MODELS: dict[ProviderName, str] = {
    "deepseek": "deepseek-chat",
    "minimax": "MiniMax-Text-01",
    "glm": "glm-4.5",
}
