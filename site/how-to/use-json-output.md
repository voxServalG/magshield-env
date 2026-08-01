# 操作指南：在脚本和 CI 中消费命令输出

`validate` 和 `inspect` 是脚本友好的：stdout 只输出一个 JSON envelope，进度和诊断走 stderr。不要解析帮助文本，也不要把错误信封当成功。

## 成功信封

```json
{
  "ok": true,
  "command": "validate",
  "result": {
    "package_dir": "environment",
    "package_identity": "…",
    "point_count": 2,
    "channel_count": 2,
    "response_shape": [2, 3, 2],
    "response_rank": 2,
    "physics_mode": "fixed"
  }
}
```

字段名以实际输出为准；先读 `ok`，不要靠文本猜测。

## 失败信封

```json
{
  "ok": false,
  "command": "validate",
  "error": {
    "type": "validation",
    "subtype": "package_contract",
    "message": "…",
    "hint": "Restore the original package or rebuild it from validated sources."
  }
}
```

`type`、`subtype`、`message`、`hint` 都是结构化字段；`hint` 是可执行的下一步。修复源头后重试，不要绕过校验。

## 在 CI 里用

```bash
magshield-env validate environment/ > result.json
jq -e '.ok == true' result.json
```

也可以用 `--pretty` 让终端阅读更舒服，但机器解析请用默认的紧凑 JSON。各命令的参数以 `--help` 为准。

## 例外

`--help` 和 `--version` 输出纯文本，不受 JSON 信封约束；交互式 TUI 的画面写 stderr，stdout 保持未使用。
