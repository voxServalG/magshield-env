# 快速开始

## 安装

项目要求 Python 3.12 或更高（3.12 至 3.14），推荐用 `uv` 管理：

```bash
git clone git@github.com:voxServalG/magshield-env.git
cd magshield-env
uv sync --locked
```

也可以先构建 wheel 再作为命令行工具安装：

```bash
uv build
uv tool install dist/magshield_env-0.1.0-py3-none-any.whl
```

任何情况下，先运行 `magshield-env --help` 查看当前可用的命令、参数和示例；它是最新的命令细节来源。

## 第一次使用：TUI 五步向导

```bash
uv run magshield-env tui
```

全屏向导按五个步骤收集定义，最后给出校验报告，只有没有任何阻塞问题时才允许导出：

1. **采样区域**：生成笛卡尔盒、圆柱、球体或球面点集，或导入测量点集。
2. **正向模型**：三选一——固定响应矩阵、有限元逐通道场、或导体几何（动态 Biot-Savart）。
3. **硬件**：声明每个通道的电流边界、爬升率、电阻和电压限制，以及控制器步长。
4. **场景**：声明静态外部场与位姿，或绑定 HDF5 轨迹。
5. **环境行为**：选择观测模式、是否包含位姿、非法动作行为与奖励参数。

## 三分钟跑通一个例子

仓库自带一个完整的最小构建定义 `examples/minimal-finite-element/build.yaml`（两点、两通道的有限元 CSV 场）。复制它到一个新目录，把 `output_dir` 改成新路径，然后：

```bash
uv run magshield-env validate path/to/environment
uv run magshield-env inspect path/to/environment --pretty
```

程序化构建和加载见[教程：用 build.yaml 与 Python API 构建](../tutorials/programmatic-build)。

## 加载环境包

导出的目录不依赖任何原始源文件，直接通过 Gymnasium 接口加载：

```python
import numpy as np

from magshield_env import make_env

env = make_env("path/to/environment")
observation, info = env.reset(seed=7)
observation, reward, terminated, truncated, info = env.step(
    np.zeros(env.action_space.shape, dtype=np.float64)
)
```

## 下一步

- 想跟着向导走完整流程：[用 TUI 构建第一个环境](../tutorials/tui-first-env)。
- 想理解每个概念的物理含义：[概念](../concepts/units-and-formats)。
- 遇到校验失败：[操作指南：排查](../how-to/troubleshooting)。
