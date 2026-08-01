# 概念：硬件投影与约束证据

每个 step，动作是归一化的电流增量，硬件模型把它映射进合法区间。合法增量由三个边界联合定义：

- 电流边界：新电流必须在 `[current_lower_a, current_upper_a]`。
- 爬升率边界：每步增量不能超过 `slew_rate_upper_a_per_s * timestep_seconds`。
- 电压推导边界：由电阻、电压上限和电流变化联合推导。

非法动作有两种显式行为，由构建时声明的 `constraint_mode` 决定：

- `project_and_report`：把动作投影进合法区间，在 `info` 里同时给出请求动作、实际动作和约束证据。
- `terminate`：非法动作直接终止本回合。

**不存在静默裁剪**：要么给出证据，要么结束回合。下游代码可以通过 `info` 看到当前生效的约束，而不是事后猜测。

硬件字段的声明方式见[操作指南：硬件与场景](../how-to/hardware-scenarios)。
