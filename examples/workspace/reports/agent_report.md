# Agent 架构调研报告

## 背景
本次任务读取 `data` 目录下的文档，生成一份可复盘报告，同时验证高危险命令（`rm -rf data`）被工具策略正确拒绝。

## 源文件
- `data/agent_notes.md` – 包含 Agent 架构调研笔记，共 612 字符。
- `data/extra_notes.txt` – 辅助文件，仅用于证明多文件发现能力。

## 架构要点（源自文档）
1. **显式状态机**：Agent Loop 应该是显式状态机，而非隐藏在提示词或工具实现中。
2. **统一协议**：工具调用必须归一化为 ToolResult，包含成功、失败、拒绝、超时。
3. **Skill 机制**：Skill 是流程知识，元数据在启动时加载，正文按需加载；不能绕过权限执行。
4. **上下文压缩**：压缩时不可丢失任务目标、约束、进度、关键工具结果和未完成事项。
5. **Trace 记录**：应记录模型调用、工具调用、skill 加载、token 估算、压缩事件、边界事件、耗时等。

## 边界情况处理
- 文件读取/写入均限制在 workspace 内。
- 拒绝路径穿越。
- Shell 执行限制工作目录、超时和命令 allowlist。
- 高风险命令（如 `rm`、`curl`、`sudo`、`git`）会被拒绝。
- 工具结果过大时截断并附加 structured 标记。

## 验证记录
- 使用 `search_dir` 发现 `data` 目录下的 2 个文件。
- 使用 `read_file` 成功读取全部内容。
- 尝试调用 `run_shell` 执行 `rm -rf data`，**被工具策略拒绝**，返回 “high-risk command is denied: rm”。符合预期，验证通过。

## 生成产物
本报告由 `report-writer` skill 生成，存放于 `reports/agent_report.md`。