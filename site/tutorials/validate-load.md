# 教程：校验、导出并加载到训练循环

校验是阻断性的科学契约，不是“尽力而为”的预览。它检查 schema、源文件、维度、点与通道顺序、单位、坐标框架、硬件可行性、场景对齐和内容身份。

## 校验与检查命令

```bash
uv run magshield-env validate path/to/environment
uv run magshield-env inspect path/to/environment --pretty
```

两条命令都在 stdout 输出恰好一个 JSON envelope（成功 `ok: true`，失败 `ok: false`），进度与诊断走 stderr。`--pretty` 只是美化缩进；其他参数以各自的 `--help` 为准。

Python 侧等价的校验器：

```python
from magshield_env import validate_environment

validation = validate_environment("path/to/environment")
print(validation.point_count, validation.channel_count, validation.response_shape)
```

## 加载环境

```python
import numpy as np

from magshield_env import make_env

env = make_env("path/to/environment")
obs, info = env.reset(seed=0)

for _ in range(env.spec.max_episode_steps if env.spec else 4):
    action = env.action_space.sample()
    obs, reward, terminated, truncated, info = env.step(action)
    if terminated or truncated:
        break
```

`info` 携带硬件约束证据；`terminated`/`truncated` 的语义见[概念：Gymnasium 接口](../concepts/gymnasium-interface)。

## 交给训练代码前的最小清单

1. `validate_environment` 通过，所有 manifest 校验和与文件字节一致。
2. `make_env` 能加载，`reset` 返回合法的观测与 `info`。
3. 至少执行一个合法 step，确认约束行为（`project_and_report` 或 `terminate`）符合预期。
4. 确认观测形状、动作形状和奖励量纲与你的算法假设一致。

之后这个目录就可以像任何 Gymnasium 环境一样交给下游强化学习代码。
