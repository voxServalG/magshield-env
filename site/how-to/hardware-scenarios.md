# 操作指南：声明硬件、外部场与位姿

硬件与场景把响应模型变成可执行的控制环境。所有数值都是规范 SI 单位，并且通道与点身份必须和物理源保持一致。

## 硬件

每个通道声明：

- `current_lower_a` / `current_upper_a`：电流边界（安培）。
- `slew_rate_upper_a_per_s`：正向爬升率上限（安培每秒）。
- `resistance_ohm`：电阻（欧姆）。
- `voltage_upper_v`：电压上限（伏特）。

另外声明控制器步长 `timestep_seconds`。通道 ID 唯一，且必须按响应矩阵的通道列顺序出现。

每个 step 里，电流边界、爬升率边界和电压推导的边界联合定义合法增量；非法动作的行为由 `constraint_mode` 显式选择（`project_and_report` 或 `terminate`），不存在静默裁剪。

## 静态外部场与位姿

```yaml
scenario:
  kind: static
  episode_length: 4
  external_field_component_frame: body
```

静态场景可以带一个外部场文件；位姿可选，但一旦出现，平移 `translation_m` 和四元数 `quaternion_xyzw` 必须成对完整。四元数表达取向，不是欧拉角。

固定响应包要求外部场分量框架等于响应框架。动态几何把每个位姿解释为从点框架到路径框架的变换，然后在目标框架里求响应和外场分量。

## 轨迹场景

```yaml
scenario:
  kind: trajectory
  path: scenario.h5
  external_field_component_frame: body
  episode_length: 100
  random_start: false
```

HDF5 轨迹绑定外部场帧与可选位姿数组，约束：

- 平移与四元数数据集要么都存在，要么都不存在。
- 所有随时间变化的数组共享相同的首帧数。
- 文件显式声明 `field_unit=T`、外场分量框架、位姿平移单位 `m` 和四元数顺序 `xyzw`；名字本身不能当作单位证据。
- 动态几何里每个运行时帧都需要位姿；重复的精确位姿可命中缓存。

## 奖励声明

奖励的尺度和权重是构建时声明的一部分：场误差、功率、电流变化、约束，以及可选的额定电流偏差。没有事后再调参的隐藏默认值。

各字段的精确含义见[参考：格式契约](../reference/format-contracts)和[概念：场误差指标](../concepts/field-error-metric)。
