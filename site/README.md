# 文档站说明

本站是 magshield-env 的公开用户文档（ReadTheDocs 部署）。中文是唯一事实源，英文通过 gettext 翻译维护。

## 本地构建

```bash
uv sync --locked
uv run sphinx-build -b html site site/_build/html -W          # 中文
uv run sphinx-intl build -d site/locales
READTHEDOCS_LANGUAGE=en uv run sphinx-build -b html site site/_build/html-en -W -D language=en  # 英文
uv run sphinx-build -b linkcheck site site/_build/linkcheck -W
```

## 更新翻译

改完中文源文件后重新抽取并更新英文翻译：

```bash
uv run sphinx-build -b gettext site site/_build/gettext
uv run sphinx-intl update -p site/_build/gettext -d site/locales -l en
```

然后编辑 `site/locales/en/LC_MESSAGES/*.po` 中的 `msgstr`。未翻译的字符串会让英文构建失败，而不是静默回退到中文。

## 发布

ReadTheDocs 主项目构建中文（项目语言设为 Chinese）；再建一个英文翻译项目（语言设为 English）并关联 Translations，两个项目使用同一个 `.readthedocs.yaml`。
