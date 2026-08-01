# 概念：环境包与 manifest

一次成功的构建产生一个**自包含、可移植**的目录，恰好包含六个契约文件：

```text
environment.yaml
manifest.json
physics.h5
hardware.yaml
scenario.h5
README.md
```

- `environment.yaml`：命名不可变的包成员，声明 Gymnasium 接口行为。
- `physics.h5`：点身份加响应数据，或导体几何。
- `hardware.yaml`：冻结的有序通道约束。
- `scenario.h5`：外部场与位姿帧。
- `manifest.json`：记录 schema 版本、来源身份、坐标框架、数组形状、通道顺序和每个成员的 SHA-256。

包的性质：

- 缺少、多余、重排或被改动的成员都让校验失败；分析文件放在包旁边而不是里面。
- 导出是原子的：要么完整写出，要么不写；不覆盖已有目录。
- `make_env` 只读这个包，不接触任何原始构建源。

六文件之外的任何内容（说明文件、修改过的字节、编辑过的 manifest）都会破坏校验，这是刻意的不变量。
