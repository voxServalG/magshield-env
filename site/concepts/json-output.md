# 概念：命令输出契约

面向脚本的命令（`validate`、`inspect`）在 stdout 输出**恰好一个** JSON 信封：

- 成功：`ok: true`，附带 `command` 和 `result`。
- 失败：`ok: false`，附带 `command` 和结构化的 `error`（`type`、`subtype`、`message`、`hint`）。

规则：

- `--help` 和 `--version` 输出纯文本，不受信封约束。
- 进度、调试和诊断信息一律走 stderr，不污染 stdout 的 JSON 流。
- TUI 的交互画面走 stderr，stdout 保持未使用。
- 错误信封不是成功；解析时先读 `ok` 字段。

脚本消费示例见[操作指南：在脚本和 CI 中消费命令输出](../how-to/use-json-output)。
