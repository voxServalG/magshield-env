# 教程：用 build.yaml 与 Python API 构建

TUI 适合交互式构建，脚本和 CI 则用一份严格的 YAML 构建定义加 Python API。仓库的 `examples/minimal-finite-element/build.yaml` 是完整的最小例子（两点、两通道）。

## 构建定义长什么样

```yaml
schema_name: magshield_env.build_config
schema_version: 1
name: minimal-two-channel
region:
  kind: import
  path: points.csv
  frame: body
forward:
  kind: finite_element
  channel_files:
    - field_ch0.csv
    - field_ch1.csv
  channel_ids:
    - ch0
    - ch1
  coordinate_tolerance_m: 0.0
hardware:
  timestep_seconds: 0.01
  channels:
    - channel_id: ch0
      current_lower_a: -1.0
      current_upper_a: 1.0
      slew_rate_upper_a_per_s: 10.0
      resistance_ohm: 1.0
      voltage_upper_v: 10.0
    - channel_id: ch1
      current_lower_a: -1.0
      current_upper_a: 1.0
      slew_rate_upper_a_per_s: 10.0
      resistance_ohm: 1.0
      voltage_upper_v: 10.0
scenario:
  kind: static
  episode_length: 4
  external_field_component_frame: body
environment:
  observation_mode: full_field
  include_pose: false
  action_mode: current_delta
  constraint_mode: project_and_report
  reward:
    field_scale_t: 1.0e-6
    field_threshold_t: 1.0e-7
    field_weight: 1.0
    power_scale_w: 1.0
    power_weight: 0.01
    slew_scale_a: 0.1
    slew_weight: 0.01
    constraint_scale_a: 0.1
    constraint_weight: 1.0
output_dir: environment
```

字段含义（单位、形状、顺序约束）见[格式契约](../reference/format-contracts)和[概念](../concepts/units-and-formats)；JSON Schema 投影是机器校验的权威。

## 加载并构建

```python
from magshield_env import (
    build_environment,
    inspect_build,
    load_build_config,
)

config = load_build_config("build.yaml")

# Preview the resolved dimensions and sources before building
preview = inspect_build(config)

# Build atomically into a new directory; existing paths are never overwritten
report = build_environment(config)
print(report.output_dir)
```

`report` 是 `BuildReport`，包含输出目录、包身份、点数、通道数、响应形状与秩、响应内存字节数和物理模式（`fixed` 或 `dynamic_geometry`）。

## 构建失败时

异常是结构化的 `MagshieldEnvError`，携带 `type`、`subtype`、`message` 和可执行的 `hint`。按提示修复声明或源文件后重试；不要改一个不同的物理模型来碰运气。常见修复路径见[操作指南：排查](../how-to/troubleshooting)。

## 导出后的双保险

```python
from magshield_env import validate_environment

validation = validate_environment(report.output_dir)
print(validation.package_identity)
```

`validate_environment` 校验每个文件哈希、数组身份和跨文件契约。之后再用 `make_env` 加载并执行一次 step，见[教程：校验、导出并加载](../tutorials/validate-load)。
