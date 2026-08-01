# 参考：命令行入口

`magshield-env` 提供三个面向用户的命令。**本站不复制任何 flag 或参数**：运行每个命令的 `--help` 即可获得最新的参数、默认值、可选值和示例，那是唯一真源。

| 命令 | 作用 | 输出 |
|---|---|---|
| `tui` | 打开五步全屏环境构建向导 | 交互画面走 stderr，stdout 未使用 |
| `validate` | 校验环境包的哈希、schema、数组与跨文件契约 | stdout 一个 JSON 信封 |
| `inspect` | 读取包元数据与派生维度，不做修改 | stdout 一个 JSON 信封 |

```bash
magshield-env --help
magshield-env tui --help
magshield-env validate --help
magshield-env inspect --help
```

输出契约的语义见[概念：命令输出契约](../concepts/json-output)，脚本消费示例见[操作指南](../how-to/use-json-output)。
