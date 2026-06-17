<p align="center">
  <img src="https://upload.wikimedia.org/wikipedia/commons/thumb/3/36/McDonald%27s_Golden_Arches.svg/220px-McDonald%27s_Golden_Arches.svg.png" width="80" alt="ПБО">
</p>

<h1 align="center">Расписание ПБО</h1>

<p align="center">
  <em>Жмёшь одну кнопку. Расписание на месяц готово.</em>
</p>

---

Каждый месяц одно и то же: кто работает в субботу, у кого ночь, кому выходной после ночи, кто идёт в отпуск. Восемь человек, пятнадцать правил, один Excel на всех.

Это приложение делает всё за тебя.

## Что умеет

Нажимаешь «Генерировать» — Python-бэкенд строит расписание на месяц по политике McDonald's декабрь 2025:

- **П.4** — ротация 2У + 2В, одна неделя в месяц = 4 смены (доп. выходной)
- **П.5** — интервал ≥ 13 ч между сменами (нет вечер → утро)
- **П.6** — каждому менеджеру Сб+Вс хотя бы раз в месяц; директору — дважды
- **П.7** — не более 5 смен в неделю
- **П.8** — не более 3 выходных подряд, без цепочек через стык недель
- **П.9/10** — после ночной смены обязательный выходной + рекомендуемый второй
- **П.14** — в январские праздники (1–8 янв) не более 3 смен; на праздники с двойной оплатой level4-5 только лидируют сменой

Заявки на выходные учитываются. Слоты можно поправить руками после генерации.

## Запуск

```bash
pip install -r requirements.txt
python app.py
# → http://localhost:5000
```

На Railway деплоится автоматически из main. Данные в Postgres (DATABASE_URL) или `data.json`.

## Структура

```
├── app.py              # Flask + алгоритм (class Scheduler)
├── templates/
│   └── index.html      # UI
├── requirements.txt
└── data.json           # fallback хранилище
```

## Уровни

| Уровень | Роль | Слоты |
|---------|------|-------|
| level6 | Директор | morningInside / eveningInside / office |
| level5 | Рук. департамента | morningInside / eveningInside / rdm |
| level4 | Ассистент директора | morningInside / eveningInside / rdm |
| level3 | Менеджер ПБО | morningManager / eveningManager / night / sw |

## API

```
GET  /api/employees          — список сотрудников
POST /api/employees          — добавить
PUT  /api/employees/:id      — изменить
DELETE /api/employees/:id    — удалить
POST /api/requests           — заявка на выходной
POST /api/generate           — сгенерировать расписание {year, month}
GET  /api/schedule?year&month — загрузить сохранённое
PUT  /api/schedule/slot      — изменить один слот
POST /api/reset              — сброс к дефолтным сотрудникам
```

## Лицензия

MIT
