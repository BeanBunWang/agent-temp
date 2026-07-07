# 架构说明

## AI 编程工具使用方式

本项目由 Codex 根据需求文档和参考架构文档生成。实现时先提炼需求中的硬性验收点：
Agent Loop、Tool、Skill、Token 预算、边界处理、Trace、README 和样例 trace。
参考架构中的判断被收敛为一个轻量版本：事件优先、工具协议统一、skill 渐进披露、压缩保留不变量。

## 核心判断

### 1. 单 Agent 优先

MVP 不做多 Agent。多 Agent 会引入上下文隔离、写入冲突、取消传播和结果汇合协议。
这个题目的关键不是并行吞吐，而是一个 Agent 是否能可靠推进多步任务并留下证据。

### 2. 显式循环优先于提示词魔法

`AgentRuntime` 按固定顺序推进：

```text
build context -> token estimate -> optional compression -> model call -> action validation -> skill/tool/final -> trace event
```

每一步都会进入 trace。终止原因是结构化字段，而不是靠自然语言猜测。

### 3. 工具结果必须归一化

所有工具都返回 `ToolResult`。路径越界、高风险 shell、超时和未知工具不会直接抛出到主循环，
而是转成 `denied`、`timeout` 或 `error`，这样模型和 trace 都能看到边界处理结果。

### 4. Skill 是流程知识，不是权限通道

启动时只加载 skill 元数据，正文按需读取。Skill 正文进入上下文前会加上“不可信指导”的包裹说明，
并扫描常见 prompt injection 标记。最终执行仍走普通工具和 policy。

### 5. 压缩保留不变量

预算估算使用近似 token。超过水位后压缩 `important_results`，同时保留：

- 任务目标
- 约束
- 已加载 skill
- 当前进度摘要
- 最近重要工具结果
- 未完成事项
- 失败计数

压缩不负责“变聪明”，只负责让上下文变短且不丢失运行事实。

## 边界与未实现内容

- 不实现长期记忆：长期写入需要来源、置信度、过期和删除策略。
- 不实现提醒创建：提醒是副作用动作，通常需要确认和幂等 key。
- 不实现 MCP：MCP 适合作为外部互操作边界，但会带来认证、连接生命周期和故障隔离。
- 不实现多 Agent：小任务中协调成本高于收益。

这些能力可以在当前协议上扩展，但不应塞进第一版核心循环。

