#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "=== Пушим обновления в GitHub ==="
git add .
git commit -m "Add Render deployment config" 2>/dev/null || echo "(нечего коммитить)"
git push

echo ""
echo "=== Готово! ==="
echo ""
echo "Теперь зайди на https://render.com и:"
echo "  1. New → Web Service"
echo "  2. Connect → sofrinkirill-crypto/Расписание"
echo "  3. Runtime: Python 3"
echo "  4. Build Command: pip install -r requirements.txt"
echo "  5. Start Command: gunicorn app:app"
echo "  6. Create Web Service"
echo ""
echo "Через 2-3 минуты сайт будет доступен!"
open "https://render.com/deploy"
read -p "Нажми Enter для закрытия..."
