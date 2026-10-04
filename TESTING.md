# LifeSim Testing & Acceptance

测试目标不是证明 Agent “像人”，而是证明规则、约束、数据边界和实验结果可观察、可复现、不会静默损坏。

## 分层策略

### 1. 单元测试

覆盖纯函数和小对象：

- Clock：分钟、小时、日、周进位；Pause/Step 不丢 tick。
- Need update：饥饿、能量、社交、好奇心变化有界且无 NaN。
- Utility scoring：同一 Observation/Seed 得到同一分数；不可行 Action 不会被选择。
- Memory retrieval：importance/recency/relevance 排序、容量上限和午夜 consolidation。
- Relationship update：Familiarity、Trust、Affinity、Conflict 分开更新。
- Economy：工资、食物、租金、购买和余额边界。
- Movement：邻接/开放时间/时间成本；不存在不可达循环。
- Schema：Action、Observation、Snapshot、Report 序列化可往返。

### 2. 集成测试

- `ScenarioLoader → Engine → SQLite` 完成至少一个完整 tick。
- Save → Load 后继续运行，状态、tick、Seed 和 event sequence 一致。
- Snapshot → Time Travel 以只读方式查看且不改变原数据库。
- RuleBasedProvider/MockLLMProvider 接口返回合法 schema，不发生网络调用。
- Report Exporter 生成 Markdown/HTML，并包含 config hash、seed、指标和限制说明。

### 3. 回归测试

固定一个小型 world fixture（3 agents、3 locations、2 days），保存事件摘要 golden file。规则改动后允许明确更新 golden，但必须记录原因；不要只比较最终 Money，需比较 tick、action kind、location、关系和目标完成事件。

### 4. 长期与性能测试

```bash
# 快速回归（benchmark 标记的 100×365 测试单独运行）
python -m pytest -q -m 'not benchmark'

# 30 日验收
python -m lifesim headless --days 30 --agents 10 \
  --seed 20261004 --output artifacts/acceptance-30d

# 性能基准（不纳入普通 PR 的严格耗时阈值）
python -m lifesim --headless --days 365 --agents 100 \
  --seed 42 --output artifacts/benchmark-100x365

# 推荐的可重复吞吐基准（不写 SQLite，避免产生超大 trace 数据库）
python -m lifesim headless --benchmark --days 365 --agents 100 \
  --seed 42 --output artifacts/benchmark-100x365
```

30 日验收必须满足：

- 时间从 Day 1 单调到 Day 30，且没有停滞 tick。
- 所有 Agent 每天至少产生一个非空 ActionEvent（允许 Sleep/Wait，但不得无限 Wait）。
- 没有 NaN、Infinity、负 Energy/Health，资源和 Money 不越过配置边界。
- 数据库可关闭后重新打开；Event Log、Snapshots、Agents、Relationships 数量与报告一致。
- 每个 Agent 至少有日记/历史条目；关系、地点访问和 Action 统计可导出。
- 相同配置和 Seed 的两次运行，确定性字段逐项一致；wall-clock 时间可不同。

## 需求到测试映射

| 需求 | 验收证据 |
|---|---|
| 2D 小镇和 8 地点 | scenario fixture + location query |
| Pause/1×/5×/20×/100×/Step | clock/controller tests |
| 需求和 traits 驱动决策 | decision score snapshot + explanation |
| 受限感知 | observation contract test，禁止出现全局秘密字段 |
| 三层记忆与 consolidation | memory integration test + size bound |
| 社会关系四维度 | relationship event assertions + graph export |
| Template Conversation | deterministic dialogue fixture |
| 经济约束 | buy/work/rent invariant tests |
| 世界事件 | scheduled event replay test |
| Journal/Timeline | day boundary + snapshot read test |
| Save/Load/Time Travel | persistence round-trip + read-only test |
| Headless 365 日 | performance smoke + watchdog |
| Seed 复现 | paired-run event digest comparison |
| 报告与统计 | Markdown/HTML schema/content checks |

## 关键不变量

测试辅助函数应在每个 tick 和 run 结束时执行：

```text
assert tick >= previous_tick
assert every numeric field is finite
assert 0 <= normalized_need <= 1
assert 0 <= normalized_trait <= 1
assert health >= 0 and energy >= 0
assert location_id exists
assert every action has start/end/status
assert every relation references existing agents
assert snapshot.tick <= current_tick
assert event IDs are unique and monotonic
```

若设计允许透支 Money 或负 Health，应把例外写进 World Config，并测试该例外，而不是放宽全局断言。

## 网络与 API 保护测试

在测试环境中将网络 socket/HTTP 客户端替换为拒绝 stub；启动 demo、运行 30 日模拟和导出报告都必须通过。扫描源码和配置，确保没有硬编码 API Key、外部 URL 或隐式模型调用。Provider 测试应断言 `RuleBasedProvider` 与 `MockLLMProvider` 的调用次数和返回 schema。

## 故障场景

- 空地点、关闭商店、零资源、极端天气。
- Agent 没钱、极饿、低能量、无邻居、所有目标不可行。
- 重复加载同一 Snapshot、损坏/旧 schema、数据库事务中断。
- 100 agents 同时到达同一地点；地点容量和排队规则仍保持一致。
- 事件在午夜、工作时段和暂停期间边界触发。
- 连续 Wait、循环移动、过期 Goal；watchdog 必须停止并导出诊断。

## 发布前清单

```text
[ ] python -m pytest -q 通过
[ ] 离线环境可启动 GUI
[ ] Small Town 01 30 日 run 成功
[ ] 100 agents × 365 days headless smoke 成功或有可解释的资源记录
[ ] Save/Load/Time Travel 验收通过
[ ] Markdown/HTML 报告可打开，图表不为空
[ ] README 命令与实际入口一致
[ ] 截图、Demo World、测试报告和架构说明已随发行包提供
[ ] 明确标注模拟原型，不暗示真实意识/心理诊断
```
