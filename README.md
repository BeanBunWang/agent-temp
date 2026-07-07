# Local Agent

一个小型但完整的本地 CLI Agent 示例。它不追求大而全，重点展示 Agent Runtime 的关键边界：
显式循环、结构化工具协议、渐进式 skill 加载、token 预算与压缩、受限 shell、安全边界和可复盘 trace。

## 安装

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

也可以不安装，直接运行：

```bash
PYTHONPATH=src python -m local_agent run \
  --task "读取 data 目录下的文档并生成报告" \
  --workspace ./examples/workspace \
  --trace ./examples/traces/compression_trace.json \
  --token-budget 1200
```

## 运行命令

安装后入口为：

```bash
agent run \
  --task "读取 data 目录下的文档并生成报告" \
  --workspace ./examples/workspace \
  --trace ./examples/traces/compression_trace.json \
  --token-budget 1200
```

输出报告位于：

```bash
examples/workspace/reports/agent_report.md
```

trace 位于：

```bash
examples/traces/compression_trace.json
```

## 模型配置

默认 provider 是 `mock`，不需要 API key，适合复现和测试。

如需接入 OpenAI-compatible Chat Completions API：

```bash
export AGENT_MODEL_BASE_URL="https://api.openai.com/v1"
export AGENT_MODEL_API_KEY="..."
export AGENT_MODEL_NAME="gpt-4.1-mini"

agent run \
  --model-provider openai-compatible \
  --task "读取 data 目录下的文档并生成报告" \
  --workspace ./examples/workspace \
  --trace ./trace.json
```

模型必须返回 JSON action：

```json
{"kind":"tool","name":"search_dir","arguments":{"path":"data"},"content":"","rationale":"..."}
```

`AGENT_MODEL_API_KEY` 不会写入 trace。

### DeepSeek

DeepSeek 也是 OpenAI-compatible provider，但项目提供了单独入口，方便使用 `DEEPSEEK_*` 环境变量：

```bash
export DEEPSEEK_BASE_URL="https://api.deepseek.com"
export DEEPSEEK_API_KEY="..."
export DEEPSEEK_MODEL="deepseek-v4-pro"

agent run \
  --model-provider deepseek \
  --task "读取 data 目录下的文档并生成报告" \
  --workspace ./examples/workspace \
  --trace ./trace-deepseek.json
```

`DEEPSEEK_TIMELINE_MODEL` 暂不参与当前 CLI 调度；它保留在 `.env.example` 中，作为后续多模型路由或轻量任务模型的配置位。

不要把真实 key 写进代码、README、trace 或提交历史。建议将真实 key 放在本地 shell、direnv、1Password 或 CI secrets 中。

## 支持的 Tool

- `read_file`：读取 workspace 内文件，限制结果大小，超大结果截断并记录 metadata。
- `write_file`：写入 workspace 内文件，自动创建父目录，拒绝路径穿越。
- `search_dir`：按文件名或内容关键词检索目录，限制深度和返回条数。
- `run_shell`：受限 shell，工作目录固定在 workspace，命令 allowlist，超时，拒绝高风险命令和 shell 操作符。

## Skill 加载

Skill 存放在 workspace 的 `skills/<name>/SKILL.md`。启动时只读取元数据：

```yaml
---
name: report-writer
description: Generate a short evidence-backed markdown report from local files.
triggers: 读取,报告,文档,report
tools: read_file,write_file,search_dir,run_shell
risk: low
---
```

正文只有在模型显式选择 `load_skill`，或任务命中触发词后需要使用时才进入上下文。
Skill 内容被视为不可信流程知识，不能绕过工具权限和 workspace 边界。

## Trace 内容

每次运行导出 JSON trace，包含：

- `run_started` / `run_completed`
- `token_estimate`
- `compression_triggered`
- `model_call_started` / `model_call_completed`
- `skill_loaded`
- `tool_call_started` / `tool_call_completed`
- `boundary`，例如高风险 shell 拒绝、预算不足、工具失败

示例 trace `examples/traces/compression_trace.json` 使用默认 `mock` provider 生成，包含工具调用、skill 加载、压缩触发和高风险命令拒绝。这样没有 API key 的评审方也能复现；真实模型可用上面的 DeepSeek 或 OpenAI-compatible 命令另行 smoke test。

## 架构取舍

这个项目刻意选择单 Agent Runtime，而不是多 Agent 或大型平台。原因是题目关注的是小型但完整的核心闭环：

- 真实状态是结构化 `RunState` 和 append-only trace，模型上下文只是投影。
- Tool 使用统一 `ToolResult`，保证失败、拒绝、超时也能进入循环和 trace。
- Skill 是渐进式流程知识，避免启动时把所有文档塞进上下文。
- 压缩只替换上下文表示，不丢失目标、约束、进度、重要工具结果和未完成事项。
- 长期记忆、提醒创建、MCP、多 Agent 先不实现，避免扩大权限、审批和恢复复杂度。

更多说明见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## GitHub 推送

当前交付以本地 git 仓库为准。如果需要推送到 GitHub：

```bash
git remote add origin git@github.com:<owner>/<repo>.git
git branch -M main
git push -u origin main
```
