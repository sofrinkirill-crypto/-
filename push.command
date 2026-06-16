#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
git add .
git commit -m "Fix: gunicorn bind to \$PORT for Railway"
git push
echo "✅ Запушено! Railway сам перезапустится через ~1 мин."
read -p "Нажми Enter..."
