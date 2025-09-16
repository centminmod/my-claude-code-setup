## 概要
日本語ドキュメント（`docs/ja/**`）を追加し、Markdown の整形・Lint・日本語スタイルチェックを CI で自動化しました。

## 追加点
- `docs/ja/README.ja.md` / `CLAUDE.ja.md` / `GEMINI.ja.md` の雛形
- Prettier / markdownlint / textlint（日本語技術文書プリセット + prh）
- `Docs Lint` GitHub Actions（PR/Push 時に実行）
- `npm run docs:fix` で自動整形 + 一部自動修正

## 追記推奨（別コミット可）
ルート `README.md` 冒頭に日本語版リンク：

```md
> 🇯🇵 日本語ドキュメント: [docs/ja/README.ja.md](docs/ja/README.ja.md)
```

## 動作確認
```bash
npm ci
npm run docs:fix
npm run docs:check
```
