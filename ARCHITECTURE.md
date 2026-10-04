# LifeSim Architecture

本文档描述 LifeSim 的可观察、可复现模拟内核。UI 只是观察和控制层，不能绕过 Simulation Engine 直接修改 Agent 状态。

## 分层

```text
┌──────────────────────────────────────────────────────────┐
│ UI / CLI / Headless Runner                               │
│ World View · Inspector · Timeline · Charts · Export      │
└───────────────┬──────────────────────────────────────────┘
                │ commands / read models
┌───────────────▼──────────────────────────────────────────┐
│ Simulation Application                                    │
│ Clock · Scenario · Run Control · Checkpoint Manager       │
└───────────────┬──────────────────────────────────────────┘
                │ immutable Observation / Action result
┌───────────────▼──────────────────────────────────────────┐
│ Domain Engine                                             │
│ Perception → Needs → Memory Retrieval → Utility Decision  │
│ → Action Executor → Consequences → Consolidation          │
└───────────────┬──────────────────────────────────────────┘
                │ events / snapshots / metrics
┌───────────────▼──────────────────────────────────────────┐
│ Persistence & Analysis                                   │
│ SQLite · Event Log · Snapshots · Social Graph · Reports   │
└──────────────────────────────────────────────────────────┘
```

## 核心领域对象

### World

`World` 持有 simulation clock、天气、事件、资源、地点、Agent、规则版本和 Seed。World 不允许 UI 直接写入；修改必须通过 command 或 engine step。

### Location

地点包含 `location_id`、类型、容量、开放时间、功能标签、资源状态和邻接关系。移动成本来自地图距离或预先定义的 travel matrix。

### Agent

Agent 由以下分组组成：

- **State**：location、money、health、energy、hunger、mood、social_need、stress、safety、curiosity、achievement。
- **Traits**：sociability、curiosity、risk_tolerance、patience、discipline、generosity、independence、emotion_reactivity。
- **Goals**：short/medium/long goal，带优先级、进度、完成条件和来源规则。
- **Memory**：working、episodic、semantic 三层；每条长期记忆有 importance、recency、relevance、retrieval_score。
- **Relations**：familiarity、trust、affinity、conflict、last_interaction、interaction_count。
- **History**：由不可变事件日志引用，不在 Agent 表中重复堆积完整文本。

所有连续参数都经过边界校验。默认 Need/trait 范围是 `[0, 1]`，Money、计数和时间均使用显式单位，避免隐式浮点混用。

## 一个 tick 的确定性顺序

```text
1. Clock.advance(delta)
2. Apply scheduled world events (weather, festival, outage, discounts)
3. For each active Agent in stable agent_id order:
   a. Build limited Observation
   b. Update Needs from elapsed time and local conditions
   c. Retrieve bounded Working/Episodic/Semantic memory
   d. Generate feasible actions (no inaccessible or unaffordable actions)
   e. Score actions with deterministic utility + seeded tie-break
   f. Select one action and execute its consequence transaction
   g. Emit ActionEvent, MemoryEvent, RelationshipEvent and metrics
4. Resolve end-of-tick resource/relationship effects
5. At local midnight, consolidate memory and write JournalEntry
6. Periodically write an immutable SimulationSnapshot
```

Agent iteration顺序必须稳定；禁止依赖 Python set/dict 的未定义顺序。任何随机数都从 `SeededRng` 派生，并记录 stream/key，确保增加 UI 刷新不会改变结果。

## Perception 与信息边界

`Observation` 是只读 DTO，只包含：当前位置、附近 Agent、附近资源/地点、当前时刻、天气、近期公开事件和 Agent 自身状态。它不包含其他 Agent 的完整 Memory、未来事件或全局统计。该边界是研究结果可信度的重要组成部分。

## 决策引擎

每个候选 Action 都产生：

```json
{
  "action": "Eat",
  "score": 0.82,
  "feasible": true,
  "factors": {
    "hunger": 0.76,
    "energy_cost": -0.03,
    "money_cost": -0.08,
    "sociability": 0.02
  },
  "reasons": ["hunger is high", "Food Shop is open"]
}
```

最终结果保存 `selected_action` 和可公开的 `decision_summary`。不保存或展示隐藏 chain-of-thought；若未来接入 LLM，只允许其返回 schema 化的短摘要与动作，不允许将内部推理当作研究事实。

## Action 与后果

统一 Action 协议包含：`action_id`、`agent_id`、`kind`、`target`、`start_tick`、`duration`、`time_cost`、`energy_cost`、`money_delta`、`mood_delta`、`relationship_delta`、`memory_event` 和 `status`。执行器在提交前验证：目标地点开放、资源足够、Money 不会非法透支、duration > 0 且状态没有 NaN。

## Memory

- **Working Memory**：短窗口、容量有限，只存近期相关 Observation/事件。
- **Episodic Memory**：带时间和地点的事件，例如“Day 2 下午在 Cafe 遇到 Alex”。
- **Semantic Memory**：从重复事件中规则式归纳的事实，例如“Alex 通常下午去 Cafe”。

检索分数是可解释函数：

```text
retrieval_score =
  w_i * importance + w_r * recency + w_c * relevance
```

每天结束时压缩低分记忆、强化高分记忆并归纳事实；原始 Event Log 永不被 Memory Consolidation 删除。`max_memory_items` 和保留策略写入 World Config。

## 社会关系

关系不是单一好感度，而是独立维度：`familiarity`、`trust`、`affinity`、`conflict`。互动根据类型、上下文和 traits 更新不同维度；例如 Help 提高 trust/affinity，Disagree 可能提高 familiarity 但增加 conflict。Social Graph 只从关系 read model 绘制，原始互动仍可追溯到 Event Log。

## Provider 扩展

```python
class CognitiveProvider(Protocol):
    def plan(self, observation, context) -> PlanResult: ...
    def reflect(self, outcome, context) -> Reflection: ...
    def summarize_memory(self, events) -> MemorySummary: ...
    def dialogue(self, conversation) -> DialogueResult: ...
```

默认 `RuleBasedProvider` 不联网，`MockLLMProvider` 只返回固定/Seeded 响应。Provider 不能直接写 World；只能返回经过 schema 校验的建议，由领域引擎决定是否可执行。

## Persistence

推荐 SQLite 表：`worlds`、`agents`、`traits`、`needs`、`goals`、`memories`、`relationships`、`locations`、`events`、`actions`、`snapshots`、`experiments`、`metrics`、`journals`。写入采用事务，事件 ID 和 snapshot ID 单调递增。每个 Snapshot 包含 `schema_version`、`engine_version`、`seed`、`tick`、配置哈希和状态 JSON/规范化表。

Time Travel Debug 打开 Snapshot 的只读 connection 或深拷贝 DTO；任何 UI 调整都创建新实验，不覆盖原运行。

## Headless 与 GUI 解耦

Headless Runner 复用同一个 Engine，不引入 UI 线程或定时器：

```text
CLI args → ScenarioLoader → SimulationEngine.step() × N
         → MetricsCollector → ReportExporter
```

GUI 通过事件订阅或只读查询读取 Engine 状态；绘图刷新不能改变 RNG、tick 或 Action 顺序。长跑时采用批量提交和可配置 snapshot 间隔，避免每个 tick 强制刷新界面。

## 可复现性与性能护栏

- 固定 `seed + world_config + agent_config + engine_version` 才称为同一实验。
- 所有配置、依赖版本、数据库 schema 版本和输入文件 hash 都写入 run metadata。
- 每个 tick 至少检查 `isfinite`、范围、时间单调性和动作完成状态。
- 对 100 agents × 365 days 记录 wall time、ticks/sec、内存峰值和 DB 大小。
- 发现死循环时使用 `max_consecutive_waits`、行动超时和 watchdog；失败 run 保存诊断快照，不静默继续。

