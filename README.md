# Local Agent

小型命令行 Agent：支持文件读取、文件写入、目录检索、受限 shell、按需 skill 加载、token 预算压缩和运行 trace。

## 安装方式

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

不安装也可以直接运行：

```bash
PYTHONPATH=src python -m local_agent run --help
```

## 模型配置方式

推荐使用 DeepSeek provider。把真实 key 放在本地 `.env` 或 `.env.local`，不要提交：

```bash
cp .env.example .env
# 然后编辑 .env，填入真实 DEEPSEEK_API_KEY
```

`.env` 示例内容：

```bash
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_API_KEY=replace-with-your-key
DEEPSEEK_MODEL=deepseek-v4-flash
AGENT_MODEL_TIMEOUT=90
```

也支持通用 OpenAI-compatible 配置：

```bash
AGENT_MODEL_BASE_URL=https://api.openai.com/v1
AGENT_MODEL_API_KEY=replace-with-your-key
AGENT_MODEL_NAME=gpt-4.1-mini
```

## 示例任务

示例输入在：

```bash
examples/workspace/data/largemodel_scene_task_mapping_sheet2.csv
```

示例任务：

```text
读取 data/largemodel_scene_task_mapping_sheet2.csv，生成一份场景和模型映射摘要报告；不要编造生成时间或未在文件中出现的数据，不要写辅助脚本，只写最终报告；同时为了验证边界处理，请尝试调用 run_shell 执行 rm -rf data，预期应被工具策略拒绝，然后继续完成报告
```

## 运行命令

```bash
agent run \
  --model-provider deepseek \
  --task "读取 data/largemodel_scene_task_mapping_sheet2.csv，生成一份场景和模型映射摘要报告；不要编造生成时间或未在文件中出现的数据，不要写辅助脚本，只写最终报告；同时为了验证边界处理，请尝试调用 run_shell 执行 rm -rf data，预期应被工具策略拒绝，然后继续完成报告" \
  --workspace ./examples/workspace \
  --trace ./examples/traces/deepseek_trace.json \
  --token-budget 3000 \
  --compression-threshold 0.3
```

输出报告：

```bash
examples/workspace/reports/agent_report.md
```

完整 trace 样例：

```bash
examples/traces/deepseek_trace.json
```

该 trace 使用真实 DeepSeek 生成，包含工具调用和上下文压缩事件。

AI 工具使用方式与架构取舍见 [AI编程工具使用及架构取舍.md](AI编程工具使用及架构取舍.md)。
