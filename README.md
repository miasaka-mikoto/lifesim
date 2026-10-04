# LifeSim

## 数字生命沙盒（Agent-Based Artificial Life Simulation）

LifeSim 是一个本地、离线优先的人工生命研究原型。它让多个由规则、状态、记忆、目标和效用决策驱动的数字个体，在一个小型二维城镇中持续生活、行动并产生可观察的后果。

> LifeSim 是 Agent Simulation，不是聊天机器人，也不声称模拟真实意识、真实人格或临床心理状态。`Energy`、`Stress`、`Trust` 等均为研究用模拟参数。

## 主要能力

- 8 个可交互地点：Home、Food Shop、Park、Library、Workplace、Hospital、Cafe、Town Square。
- 分钟/小时/日/周模拟时钟，支持暂停、单步和 1×/5×/20×/100×速度。
- Agent 状态：需求、性格参数、目标、工作、金钱、关系、三层记忆和完整历史。
- 感知受限：Agent 只能看到当前位置、附近实体、可见资源、时间、天气和近期事件。
- Utility Decision Engine：保存每个候选动作的评分、原因和最终选择，不依赖随机文本。
- 行动后果：时间、能量、金钱、情绪、关系与记忆事件会同时更新。
- 规则式对话、经济、天气、事件、日记、社会网络和地点统计。
- SQLite 持久化、世界快照、历史回溯（只读）和 Seed 可复现实验。
- 完全离线：默认使用 RuleBasedProvider/MockLLMProvider；没有 API Key 也可启动、演示和运行 30 日实验。
- Headless 模式适合 100 Agent × 365 日的性能基准与批量实验。

## 安全边界

开发和演示阶段不会自动调用任何收费模型 API。未来的 `CognitiveProvider` 只是可选扩展点；真实模型必须由用户显式配置。项目不收集云端凭据，不硬编码 API Key，也不把隐藏 chain-of-thought 保存到数据库。Trace 只保留公开的 observation、action、tool result 和规则式 decision summary。

## 快速开始

在项目根目录执行（实际入口以发行包中的 `--help` 为准）：

```bash
# 安装运行时依赖（无网络环境可使用随包提供的虚拟环境）
python -m pip install -r requirements.txt

# 启动图形观察站
python -m lifesim gui

# 运行内置 Small Town 01：10 agents、30 simulated days
python -m lifesim run --days 30 --agents 10 --seed 20261004 \
  --output reports/demo

# 无图形界面运行并导出结果
python -m lifesim headless --days 365 --agents 100 --seed 42 \
  --output artifacts/benchmark-42

# Throughput benchmark: coarse deterministic intervals, no SQLite database
python -m lifesim headless --benchmark --days 365 --agents 100 --seed 42 \
  --output artifacts/benchmark-100x365
```

如果使用打包后的 Windows 版本，相同参数可直接传给 `LifeSim.exe`：

```powershell
.\LifeSim.exe --headless --days 30 --seed 20261004 --output .\artifacts\demo
```

`--benchmark` 是专门的长期性能模式：它保留时钟、事件、需求、动作、记忆和报告，但用较粗的确定性时间间隔并跳过数据库写入。需要逐分钟 Trace、SQLite 快照或精确 GUI 重放时，不要使用该模式。

## 首次演示

首次启动会打开 **Small Town 01**，默认包含 10 个拥有不同 traits 的 Agent 和 8 个地点。点击 Agent 可打开 Inspector；点击时间线节点可以读取对应快照。建议先以 1× 观察一小时，再用 Step 或 20× 跑到 Day 2，最后导出 30 日报告。

内置演示报告至少回答：

1. 哪个 Agent 的探索次数最多？
2. 谁建立了最多双向关系？
3. 哪个地点访问量最高？
4. 哪些 Agent 形成稳定的工作/休息路线？
5. 关系网络在 30 日内如何变化？

## 研究工作流

1. 创建或复制一个 World Config。
2. 固定 Agent 参数、规则版本和 Seed。
3. 选择 GUI 或 Headless 模式运行。
4. 保存 checkpoints 与原始 event log。
5. 用 World Inspector、Social Graph、统计面板和 Agent Timeline 检查行为。
6. 导出 JSON/CSV 指标和 Markdown/HTML 报告。
7. 改变一个变量（例如 Curiosity），运行对照实验并比较。

每次运行的 metadata 应包括：`experiment_id`、`world_config_hash`、`agent_config_hash`、`seed`、`engine_version`、`provider`、`start_time`、`end_time` 和 `dataset/event-log hash`。这样同一配置在未来仍可以复现或解释差异。

## 目录约定

```text
LifeSim/
├── README.md
├── ARCHITECTURE.md
├── TESTING.md
├── requirements.txt
├── pyproject.toml
├── lifesim/              # 核心模拟、持久化、统计和 UI
├── tests/                # 单元、集成、回归和长期模拟测试
├── examples/             # Small Town 01 与配置样例
├── artifacts/            # 本地生成的报告、快照和图表（可清理）
└── docs/                 # 研究说明与扩展协议
```

SQLite 数据库建议按实验分别保存；不要把可再生成的 `artifacts/` 二进制输出提交到源码仓库。

## 数据与快照

每个 tick 先读取只读 Observation，再计算候选动作评分，最后在一个事务中提交 Action、状态变化、关系变化、Memory Event 和 Event Log。快照采用版本化 schema；读取旧快照时只做迁移，不就地改变历史记录。Time Travel Debug 以只读副本打开快照，因此不会改变原模拟。

## 故障排查

- **时间不动**：确认未处于 Pause，并检查事件循环/Headless tick 日志；使用 `Step` 验证时钟。
- **Agent 卡住**：导出该 Agent 最近 100 个 action；若连续选择 `Wait`，检查 energy、可达地点和 utility tie-break。
- **数值异常**：运行 `python -m pytest`；系统应拒绝 NaN/无穷值，并把资源、Money、Need 约束在配置范围内。
- **无法复现**：确认 Seed、配置哈希、引擎版本和数据库快照均来自同一次运行。
- **没有 API Key**：这是正常状态；RuleBasedProvider 是默认实现，完整 UI 和演示不需要网络。

## 许可证与研究用途

本项目是本地研究工具原型。若分发第三方数据、模型或地点素材，请单独确认其许可证。不要把模拟指标解释为对真实人的预测或诊断。
