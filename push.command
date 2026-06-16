#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
git add .
git commit -m "Fix: hardcode port 5000 for Railway"
git push
echo "✅ Запушено! Жди ~1 мин."
read -p "Нажми Enter..."
