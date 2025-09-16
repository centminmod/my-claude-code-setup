# Claude Code プロジェクト用スターター設定（日本語版）

> 本ドキュメントは、`centminmod/my-claude-code-setup` の README を日本語向けに再構成したものです。英語原文はレポジトリ直下の `README.md` を参照してください。

## 目次
- [概要](#概要)
- [前提条件](#前提条件)
- [導入手順](#導入手順)
- [Claude Code Hooks](#claude-code-hooks)
- [Claude Code Subagents](#claude-code-subagents)
- [Slash Commands（抜粋）](#slash-commands抜粋)
- [ライセンス](#ライセンス)

## 概要
このリポジトリには、**Claude Code 用のスターター設定**および **CLAUDE.md を中心としたメモリバンク運用**、各種 **Hooks／Slash コマンド**のテンプレートが含まれます。まずは公式ドキュメント「Claude Code 概要」を確認し、**有料プランの Claude アカウント**（Pro/Max 等）に加入してください。

- 公式ドキュメント: https://docs.anthropic.com/en/docs/claude-code/overview
- アカウント: https://claude.ai

## 前提条件
- （推奨）**Visual Studio Code** と **Claude Code 拡張機能**を導入します。
- プロジェクトに合わせて `CLAUDE.md` の内容（ルール・手順・メモリ項目）を調整します。
- macOS の場合は `.claude/settings.json` の通知連携で **Terminal-Notifier** を使用します（他 OS は該当設定を削除して構いません）。

## 導入手順
1. 本リポジトリのファイル一式を、対象プロジェクトのルート（コードベースのトップ）にコピーします。
2. テンプレート類と `CLAUDE.md` をプロジェクト方針に合わせて編集します。macOS を使わない場合は `.claude/settings.json` を削除しても問題ありません。
3. プロジェクトディレクトリで **Claude Code を初回起動**したら、`/init` を実行してコードベースを解析し、`CLAUDE.md` の指示に従ってメモリバンクを初期化します。
4. （強く推奨）**Visual Studio Code** と **Claude Code VSCode Extension** を導入します。
5. （推奨）**GitHub** アカウントと Git をセットアップし、基本操作に慣れておきます。

## Claude Code Hooks
- `STOP` Hook を用意しています。Claude Code の応答完了時に **デスクトップ通知（macOS）** を出すために **Terminal-Notifier** を使用します。

## Claude Code Subagents
各サブエージェントは、特定領域のタスクを自律的にこなす専門ツールです。メイン対話とは**別のコンテキストウィンドウ**を持ち、**専用プロンプト**を利用できます。

### `memory-bank-synchronizer`
- 目的: メモリバンク（CLAUDE-*.md 群）と実際のコード状態の差分を継続同期
- 役割: パターン文書の整合、アーキテクチャ決定の更新、実装状況の追跡、コード例の鮮度チェック、相互参照の検証
- 使い所: メモリファイルの信頼性を保つための定期運用

### `code-searcher`
- 目的: コードベースの高速探索と要約。通常モードに加え **Chain of Draft (CoD)** の超簡潔モードを任意で使用可能
- 使い所: 関数・クラスの所在、バグ原因箇所、実装ポイント探索など

### `get-current-datetime`
- 目的: ブリスベン（GMT+10）タイムゾーンでの正確な日時値を返すユーティリティ
- 使い所: タイムスタンプ付きファイル名やレポート作成など（**出力は説明なしの生値**）

### `ux-design-expert`
- 目的: UX/UI 全般の設計ガイダンス（Tailwind CSS、データ可視化、高品質コンポーネント設計、アクセシビリティ等）

## Slash Commands（抜粋）
### `/anthropic` 系
- `/apply-thinking-to`: 論理展開を強化する拡張思考フレームをプロンプトに適用
- `/convert-to-todowrite-tasklist-prompt`: 複雑ワークフローを TodoWrite ベースの並列タスク形式に変換
- `/update-memory-bank`: `CLAUDE.md` とメモリファイル群を更新

### `/ccusage`
- `/ccusage-daily`: コスト・使用量の集計レポートを Markdown で生成（総コスト、ピーク日、キャッシュ効率など）

### `/cleanup`
- `/cleanup-context`: 重複・陳腐化したメモリ文書を整理し、トークン消費を 15–25% 削減

### `/documentation`
- `/create-readme-section`: README 向けの特定セクションを既存スタイルに合わせて自動生成

### `/security`
- `/security-audit`: OWASP 観点で認証・入力検証・データ保護等を網羅監査
- `/check-best-practices`: 言語/フレームワーク慣行に基づくコード品質チェック
- `/secure-prompts`: プロンプトインジェクション検知と詳細レポート生成（`reports/secure-prompts/` に保存）

## ライセンス
- MIT License（英語原本に準拠）
