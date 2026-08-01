# 参考：JSON Schema

构建定义、环境包和几何通道各有权威的 JSON Schema 投影，随 wheel 一起分发：

| 名称 | 用途 |
|---|---|
| `build-config` | `build.yaml` 构建定义 |
| `environment-package` | 导出包里的 `environment.yaml` |
| `geometry-channels` | 导体路径的通道几何 YAML |

```python
from magshield_env import load_json_schema

build_schema = load_json_schema("build-config")
```

仓库里的 `schemas/` 目录是同一投影的确定性提交版本；契约测试要求模型修改后重新生成 schema，且归一化 JSON 字节完全一致。模型与 schema 必须在同一次改动里更新。
