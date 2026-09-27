"""NekroAgent 心流插件入口。"""

from __future__ import annotations

import sys

from pydantic import Field

try:
    from nekro_agent.api.plugin import ConfigBase, NekroPlugin
except ImportError as exc:
    # 纯逻辑测试不需要安装完整 Nekro；真实插件加载时该依赖必须存在。
    if "pytest" not in sys.modules:
        raise
    plugin = None  # type: ignore[assignment]
    config = None  # type: ignore[assignment]
    HeartflowConfig = None  # type: ignore[assignment,misc]
else:
    plugin = NekroPlugin(
        name="心流",
        module_name="nekro_plugin_heartflow",
        description="使用独立轻量模型判断群聊中的自然主动参与时机。",
        version="0.1.0",
        author="Healock",
        url="https://github.com/Healock/nekro_plugin_heartflow",
        support_adapter=["onebot_v11"],
        allow_sleep=False,
    )

    @plugin.mount_config()
    class HeartflowConfig(ConfigBase):
        """心流配置。字段名称和默认值保留自 AstrBot 版本。"""

        enable_heartflow: bool = Field(
            default=False,
            title="启用心流主动回复",
            description="启用后，插件会用独立判断模型分析群聊普通消息。",
        )
        judge_provider_name: str = Field(
            default="",
            title="原判断模型提供商标识",
            description="保留 AstrBot 配置字段；Nekro 版本使用下方独立 HTTP 配置。",
        )
        judge_api_base_url: str = Field(
            default="",
            title="独立判断模型地址",
            description="OpenAI-compatible 服务的基础地址，例如 https://example.com/v1。",
        )
        judge_api_key: str = Field(
            default="",
            title="独立判断模型密钥",
            json_schema_extra={"is_secret": True},
        )
        judge_model: str = Field(default="", title="独立判断模型名称")
        judge_api_path: str = Field(default="/chat/completions", title="独立判断模型路径")
        reply_threshold: float = Field(default=0.6, title="回复阈值（0 到 1）")
        energy_decay_rate: float = Field(default=0.1, title="精力衰减速度")
        energy_recovery_rate: float = Field(default=0.02, title="精力恢复速度")
        context_messages_count: int = Field(default=5, title="本地上下文缓冲基数")
        whitelist_enabled: bool = Field(default=False, title="启用群聊白名单")
        chat_whitelist: list[str] = Field(default_factory=list, title="群聊白名单")
        judge_relevance: float = Field(default=0.25, title="内容相关度权重")
        judge_willingness: float = Field(default=0.2, title="回复意愿权重")
        judge_social: float = Field(default=0.2, title="社交适宜性权重")
        judge_timing: float = Field(default=0.15, title="时机相关性权重")
        judge_continuity: float = Field(default=0.2, title="对话连贯性权重")
        judge_include_reasoning: bool = Field(default=True, title="判断时包含理由")
        judge_max_retries: int = Field(default=3, title="判断失败最大重试次数")
        judge_timeout_seconds: float = Field(default=30, title="判断模型超时（秒）")
        judge_context_count: int = Field(default=10, title="传入判断模型的上下文条数")
        min_reply_interval_seconds: int = Field(default=0, title="最短回复间隔（秒）")
        max_tracked_chats: int = Field(default=1000, title="最大群聊状态数量")
        max_persona_cache: int = Field(default=100, title="最大人格缓存数量")

    config = plugin.get_config(HeartflowConfig)

    # 入口对象和配置完成后再注册回调、命令和生命周期逻辑。
    from . import callbacks as _callbacks  # noqa: E402,F401
    from . import commands as _commands  # noqa: E402,F401
    from . import lifecycle as _lifecycle  # noqa: E402,F401

__all__ = ["HeartflowConfig", "config", "plugin"]
