# NekroAgent 心流

原作者：advent259141

原仓库：[Astrbot_plugin_Heartflow](https://github.com/advent259141/Astrbot_plugin_Heartflow)

Heartflow 是一个面向群聊的主动参与判断插件：它先用独立的轻量模型判断当前普通消息是否值得参与，再让 NekroAgent 的主模型按当前频道人格正常回复。当前 Nekro 版本为 `0.1.0`。

插件包根目录直接导出 `plugin`、配置类和配置实例，主要逻辑拆分为消息回调、独立 judge、历史读取、状态管理和命令模块。

## 重要运行说明

Heartflow 会把一条普通群消息升级为 Agent 的主动触发。**同一个频道不要同时开启 NekroAgent 原生的随机回复或随机主动触发机制。** 两套机制同时运行会让同一条消息出现重复触发、回复频率失控，导致 Heartflow 的冷却和能量判断失去意义。

建议的运行方式：

- 关闭目标频道的 Nekro 原生随机回复/随机主动触发；
- 保留 Nekro 的显式触发、直接 @ 和命令处理；
- 只让 Heartflow 负责普通群消息的主动参与判断；
- 如果必须同时开启，先在测试频道验证重复触发和回复配额行为。

直接 @、唤醒词和插件命令仍由 NekroAgent 原生流程处理，Heartflow 不会再次对它们做主动判断。

## 配置迁移

AstrBot 的 `judge_provider_name` 字段会保留用于识别旧配置，但 Nekro 版本不查找 AstrBot Provider。请把原判断模型迁移为独立 HTTP 配置：

| Nekro 配置 | 说明 |
| --- | --- |
| `judge_api_base_url` | OpenAI-compatible 服务基础地址，例如 `https://example.com/v1` |
| `judge_api_key` | 独立判断模型密钥，配置界面按 secret 处理；无需鉴权的本地服务可留空 |
| `judge_model` | 独立判断模型名称 |
| `judge_api_path` | 请求路径，默认 `/chat/completions` |

其余 Heartflow 配置字段和 AstrBot 版本保持相同名称及默认值，包括阈值、精力、上下文、白名单、权重、超时、重试和状态上限。

## 依赖

- NekroAgent 当前插件 API；
- `aiohttp`，用于独立 judge HTTP 请求；
- 可访问所配置判断模型地址的网络环境。

judge 请求只在消息回调期间发起，不在 import 阶段联网。请求失败、超时或返回非法 JSON 时，本条消息安全降级为不触发。

## 与 AstrBot 的已知差异

- Nekro 没有 AstrBot `on_llm_request`，主动参与说明通过运行时提示注入提供，语义保持一致但位置不完全相同；
- Nekro 没有 AstrBot `on_llm_response`，`0.1.0` 只能在触发预留时更新部分状态，主模型失败后的精确回滚和流式最终文本记录尚未实现；
- judge 使用独立 HTTP 模型配置，不直接使用 AstrBot Provider ID；
- judge 历史通过 `DBChatMessage` 读取，当前消息直接使用回调参数补入窗口；
- 当前人格文本使用 Nekro 有效预设并做长度截断，尚未复刻 AstrBot 的人格摘要模型；
- `CommandPermission.SUPER_USER` 用于替代 AstrBot ADMIN 权限；
- 插件只处理群聊普通消息，直接 @、唤醒词和命令继续由 Nekro 原生流程处理。

## 迁移文档

- [AstrBot 到 NekroAgent 的迁移设计](docs/migration-design.md)

## 当前状态

- 已包含 `0.1.0` 插件实现和纯逻辑测试；
- 需要在 Nekro 部署环境中配置独立 judge 服务后使用；
- 尚未做真实 Nekro、Docker、OneBot 或 LLM 服务验证。
