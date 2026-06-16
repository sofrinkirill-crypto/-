#!/bin/bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "=== Инициализация git ==="
git init
git add .
git commit -m "Initial commit — PBO scheduler" 2>/dev/null || echo "(уже закоммичено)"

echo ""
echo "=== Установка GitHub CLI ==="
if ! command -v gh &>/dev/null; then
    if command -v brew &>/dev/null; then
        brew install gh
    else
        echo "Homebrew не найден. Установи gh вручную: https://cli.github.com"
        exit 1
    fi
fi

echo ""
echo "=== Авторизация GitHub ==="
gh auth status 2>/dev/null || gh auth login

echo ""
read -p "Введи название репозитория на GitHub (например: pbo-scheduler): " REPO_NAME

echo ""
echo "=== Создание репозитория и пуш ==="
gh repo create "$REPO_NAME" --public --source=. --remote=origin --push

echo ""
echo "✅ Готово! Репозиторий: https://github.com/$(gh api user --jq .login)/$REPO_NAME"
read -p "Нажми Enter для закрытия..."
