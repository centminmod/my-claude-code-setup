#!/usr/bin/env bash
set -euo pipefail

# 事前に GitHub CLI (gh) へログインしてください: gh auth login
# フォークしてローカルにクローン
gh repo fork centminmod/my-claude-code-setup --clone --remote

cd my-claude-code-setup
git checkout -b docs-ja-setup

# このスクリプトと同階層に zip を置いた前提で解凍（必要に応じてパスを調整）
unzip -o ../docs-ja-kit.zip -d .

git add .
git commit -m "docs(ja): add Japanese docs and docs lint workflow"
git push -u origin docs-ja-setup

# PR を作成（タイトル・本文は同梱の PR_BODY.md を利用）
gh pr create       --title "docs(ja): Add Japanese docs & docs lint workflow"       --body-file PR_BODY.md       --base master || gh pr create       --title "docs(ja): Add Japanese docs & docs lint workflow"       --body-file PR_BODY.md       --base main
