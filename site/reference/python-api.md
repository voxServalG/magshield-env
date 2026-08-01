# 参考：Python API

包顶层导出以下公开 API。签名以当前安装版本为准；本页描述的是 v0.1 的行为。

## 构建

```python
from magshield_env import (
    BuildConfig,
    BuildReport,
    build_environment,
    inspect_build,
    load_build_config,
)

config = load_build_config("build.yaml")          # -> BuildConfig
preview = inspect_build(config)                    # -> dict
report = build_environment(config)                 # -> BuildReport
```

`BuildReport` 字段：`output_dir`、`package_identity`、`point_count`、`channel_count`、`response_shape`、`response_rank`、`response_memory_bytes`、`physics_mode`。

## 校验与检查

```python
from magshield_env import inspect_environment, validate_environment

validation = validate_environment("environment")   # -> ValidationReport
facts = inspect_environment("environment")         # -> dict
```

`ValidationReport` 字段：`package_dir`、`package_identity`、`point_count`、`channel_count`、`response_shape`、`response_rank`、`physics_mode`。

`inspect_environment` 返回的 dict 额外包含：`name`、`physics_mode`、`channel_ids`、`response_memory_bytes`、`observation_mode`、`include_pose`、`scenario_frames`、`episode_length`、`frames`、`units`。

## 加载环境

```python
from magshield_env import make_env

env = make_env("environment")                      # -> MagneticControlEnv
```

`make_env` 只消费校验过的环境包；接口语义见[概念：Gymnasium 接口](../concepts/gymnasium-interface)。

## JSON Schema

```python
from magshield_env import load_json_schema

schema = load_json_schema("build-config")
```

支持的名称：`build-config`、`environment-package`、`geometry-channels`。未知名称立即抛 `ValueError`。
