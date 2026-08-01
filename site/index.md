# magshield-env 用户文档

`magshield-env` 把显式声明的物理输入（采样区域、响应矩阵或导体几何、硬件限制、外部场与位姿）构建成**经过完整校验、自包含的 Gymnasium 环境包**。它不训练策略，也不调用有限元求解器；构建和加载是两件独立的事。

本站按你的角色组织内容：

- **研究人员与工程师**：从[教程](tutorials/tui-first-env)开始，学会用五步向导或构建定义生成环境。
- **强化学习开发者**：从[快速开始](getting-started/index)和[Python API](reference/python-api)入手，直接消费环境包。
- **评审与维护者**：[概念](concepts/units-and-formats)解释物理与契约，[架构](architecture/index)说明设计边界。

命令的参数、flag 和默认值只以各命令的 `--help` 为准；本站只解释概念和流程，不复制命令细节。

```{toctree}
:maxdepth: 1
:caption: 快速开始

getting-started/index
```

```{toctree}
:maxdepth: 1
:caption: 教程

tutorials/tui-first-env
tutorials/programmatic-build
tutorials/import-point-set
tutorials/import-fe-results
tutorials/conductor-paths
tutorials/validate-load
```

```{toctree}
:maxdepth: 1
:caption: 操作指南

how-to/sampling
how-to/hardware-scenarios
how-to/use-json-output
how-to/troubleshooting
```

```{toctree}
:maxdepth: 1
:caption: 概念

concepts/units-and-formats
concepts/coordinate-frames
concepts/field-error-metric
concepts/hardware-projection
concepts/dynamic-geometry
concepts/environment-package
concepts/json-output
concepts/gymnasium-interface
```

```{toctree}
:maxdepth: 1
:caption: 参考

reference/cli
reference/python-api
reference/format-contracts
reference/schemas
reference/faq
```

```{toctree}
:maxdepth: 1
:caption: 架构

architecture/index
```
