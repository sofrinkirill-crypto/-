"""
McDonald's Schedule Generator — Flask Backend
Запуск: python app.py  →  http://localhost:5000
"""
from flask import Flask, request, jsonify, render_template
from datetime import date, timedelta
import json, os, uuid, calendar as cal, random

app = Flask(__name__)
DATA_FILE = os.path.join(os.path.dirname(__file__), 'data.json')

SLOTS = ['morningInside', 'morningManager', 'eveningInside', 'eveningManager',
         'night', 'night2', 'rdm', 'office', 'sw']

# ─── Storage: Postgres if available, else data.json ─────────────────────────

DATABASE_URL = os.environ.get('DATABASE_URL')

def _get_pg():
    import psycopg2, psycopg2.extras
    url = DATABASE_URL
    if url and url.startswith('postgres://'):
        url = url.replace('postgres://', 'postgresql://', 1)
    conn = psycopg2.connect(url)
    return conn

def _pg_init():
    conn = _get_pg()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS store (
            key TEXT PRIMARY KEY,
            value JSONB NOT NULL
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

def load_data():
    if DATABASE_URL:
        try:
            _pg_init()
            conn = _get_pg()
            cur = conn.cursor()
            cur.execute("SELECT key, value FROM store WHERE key IN ('employees','requests','schedules')")
            rows = {r[0]: r[1] for r in cur.fetchall()}
            cur.close(); conn.close()
            return {
                'employees': rows.get('employees', []),
                'requests':  rows.get('requests', {}),
                'schedules': rows.get('schedules', {}),
            }
        except Exception as e:
            print('PG load error:', e)
    # fallback to file
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'employees': [], 'requests': {}, 'schedules': {}}

def save_data(data):
    if DATABASE_URL:
        try:
            _pg_init()
            conn = _get_pg()
            cur = conn.cursor()
            import psycopg2.extras
            for key in ('employees', 'requests', 'schedules'):
                cur.execute("""
                    INSERT INTO store(key, value) VALUES(%s, %s)
                    ON CONFLICT(key) DO UPDATE SET value = EXCLUDED.value
                """, (key, json.dumps(data.get(key), ensure_ascii=False)))
            conn.commit()
            cur.close(); conn.close()
            return
        except Exception as e:
            print('PG save error:', e)
    # fallback to file
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ─── Default employees (seed when DB is empty) ───────────────────────────────
DEFAULT_EMPLOYEES = [
    {'name': 'Кирилл',   'level': 'level5', 'canInside': True},
    {'name': 'Олег',     'level': 'level5', 'canInside': True},
    {'name': 'Вова',     'level': 'level5', 'canInside': True},
    {'name': 'Ангелина', 'level': 'level3', 'canInside': False},
    {'name': 'Антон',    'level': 'level3', 'canInside': False},
    {'name': 'Андрей',   'level': 'level3', 'canInside': False},
    {'name': 'Маша',     'level': 'level3', 'canInside': False},
    {'name': 'Ариана',   'level': 'level3', 'canInside': False},
    {'name': 'Лиза',     'level': 'level6', 'canInside': False},
]

def seed_if_empty():
    data = load_data()
    if not data['employees']:
        data['employees'] = [{'id': str(uuid.uuid4()), **e} for e in DEFAULT_EMPLOYEES]
        save_data(data)
        print('Seeded default employees')

# ─── Routes ─────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

# Employees
@app.route('/api/employees', methods=['GET'])
def get_employees():
    return jsonify(load_data()['employees'])

@app.route('/api/employees', methods=['POST'])
def add_employee():
    data = load_data()
    emp = request.json
    emp['id'] = str(uuid.uuid4())
    data['employees'].append(emp)
    save_data(data)
    return jsonify(emp), 201

@app.route('/api/employees/bulk', methods=['PUT'])
def bulk_employees():
    """Replace entire employee list (used by original HTML frontend)."""
    data = load_data()
    emps = request.json or []
    for e in emps:
        if not e.get('id'):
            e['id'] = str(uuid.uuid4())
    data['employees'] = emps
    save_data(data)
    return jsonify({'ok': True, 'count': len(emps)})

@app.route('/api/employees/<emp_id>', methods=['PUT'])
def update_employee(emp_id):
    data = load_data()
    for i, emp in enumerate(data['employees']):
        if emp['id'] == emp_id:
            data['employees'][i] = {**emp, **request.json, 'id': emp_id}
            save_data(data)
            return jsonify(data['employees'][i])
    return jsonify({'error': 'Not found'}), 404

@app.route('/api/employees/<emp_id>', methods=['DELETE'])
def delete_employee(emp_id):
    data = load_data()
    data['employees'] = [e for e in data['employees'] if e['id'] != emp_id]
    save_data(data)
    return jsonify({'ok': True})

@app.route('/api/requests/bulk', methods=['PUT'])
def bulk_requests():
    """Replace entire requests dict (used by original HTML frontend)."""
    data = load_data()
    data['requests'] = request.json or {}
    save_data(data)
    return jsonify({'ok': True})

@app.route('/api/reset', methods=['POST'])
def reset_data():
    """Clear all data and re-seed defaults."""
    data = {'employees': [], 'requests': {}, 'schedules': {}}
    save_data(data)
    seed_if_empty()
    return jsonify({'ok': True})

# Requests
@app.route('/api/requests', methods=['GET'])
def get_requests():
    data = load_data()
    emp_name = request.args.get('emp')
    if emp_name:
        return jsonify(data['requests'].get(emp_name, {}))
    return jsonify(data['requests'])

@app.route('/api/requests', methods=['POST'])
def set_request():
    data = load_data()
    body = request.json
    emp = body['emp_name']
    date_str = body['date']
    req_type = body.get('type')  # 'off', 'vacation', or None to clear
    if emp not in data['requests']:
        data['requests'][emp] = {}
    if req_type:
        data['requests'][emp][date_str] = req_type
    else:
        data['requests'][emp].pop(date_str, None)
    save_data(data)
    return jsonify({'ok': True})

# Schedule
@app.route('/api/schedule', methods=['GET'])
def get_schedule():
    data = load_data()
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    key = f'{year}-{month}'
    return jsonify(data['schedules'].get(key, {}))

@app.route('/api/schedule/slot', methods=['PUT'])
def update_slot():
    data = load_data()
    body = request.json
    key = f'{body["year"]}-{body["month"]}'
    if key not in data['schedules']:
        data['schedules'][key] = {}
    date_str = body['date_str']
    if date_str not in data['schedules'][key]:
        data['schedules'][key][date_str] = {s: '' for s in SLOTS}
    data['schedules'][key][date_str][body['slot']] = body['value']
    save_data(data)
    return jsonify({'ok': True})

@app.route('/api/generate', methods=['POST'])
def generate():
    data = load_data()
    body = request.json
    year, month = body['year'], body['month']
    scheduler = Scheduler(data['employees'], data['requests'])
    schedule = scheduler.generate(year, month)
    key = f'{year}-{month}'
    data['schedules'][key] = {
        d.strftime('%Y-%m-%d'): slots
        for d, slots in schedule.items()
    }
    save_data(data)
    return jsonify(data['schedules'][key])

# ─── Scheduling Algorithm ────────────────────────────────────────────────────

class Scheduler:
    MANDATORY = ['morningInside', 'morningManager', 'eveningInside', 'eveningManager']
    # Все уровни на окладе (правило 6 политики — выходные Сб+Вс раз в месяц для каждого)
    SALARY_LEVELS = ('level3', 'level4', 'level5', 'level6')
    EVENING_SLOTS = ('eveningInside', 'eveningManager', 'night', 'night2')

    def __init__(self, employees, requests):
        self.employees = employees
        self.requests = requests
        self.by_level = {}
        for emp in employees:
            lvl = emp.get('level', 'level3')
            self.by_level.setdefault(lvl, []).append(emp)

    def generate(self, year, month):
        first = date(year, month, 1)
        last = date(year, month, cal.monthrange(year, month)[1])
        start = first - timedelta(days=first.weekday())
        end = last + timedelta(days=(6 - last.weekday()))

        schedule = {}
        d = start
        while d <= end:
            schedule[d] = {s: '' for s in SLOTS}
            d += timedelta(days=1)

        days = sorted(schedule.keys())
        weeks = [days[i:i+7] for i in range(0, len(days), 7)]
        num_weeks = len(weeks)

        # Отслеживаем ночные смены для правила "выходной после ночи"
        prev_nights = {emp['name']: set() for emp in self.employees}

        # Правило 6/7 политики: Сб+Вс выходные для всех сотрудников на окладе.
        # Директор (level6): ДВА раза в месяц Сб+Вс (п.6 "Политика для директора").
        # Все остальные: один раз в месяц.
        # Разбрасываем по разным неделям чтобы not все в одну.
        weekend_done = {emp['name']: 0 for emp in self.employees}  # счётчик закрытых уикендов
        salary_emps = [e for e in self.employees if e.get('level') in self.SALARY_LEVELS]

        # Для каждого сотрудника — список целевых недель для Сб+Вс
        self._weekend_target_weeks = {}
        # Найдём недели с Сб+Вс внутри текущего месяца
        sat_sun_weeks = []
        for wi, w in enumerate(weeks):
            has_sat = any(d.weekday() == 5 and d.month == month for d in w)
            has_sun = any(d.weekday() == 6 and d.month == month for d in w)
            if has_sat and has_sun:
                sat_sun_weeks.append(wi)

        for i, emp in enumerate(salary_emps):
            if emp.get('level') == 'level6':
                # Директор: 2 Сб+Вс в месяц
                if len(sat_sun_weeks) >= 2:
                    # берём 2 равномерно распределённые
                    w1 = sat_sun_weeks[i % len(sat_sun_weeks)]
                    w2 = sat_sun_weeks[(i + 2) % len(sat_sun_weeks)]
                    self._weekend_target_weeks[emp['name']] = sorted(set([w1, w2]))
                else:
                    self._weekend_target_weeks[emp['name']] = sat_sun_weeks[:1]
            else:
                # Остальные: 1 Сб+Вс в месяц, стагерируем по сотрудникам
                if sat_sun_weeks:
                    self._weekend_target_weeks[emp['name']] = [sat_sun_weeks[i % len(sat_sun_weeks)]]
                else:
                    self._weekend_target_weeks[emp['name']] = []

        # Отслеживание ротации утро/вечер для правила "2У + 2В" (п.4 политики)
        # phase[name] = текущая фаза: 0=утро, 1=вечер (чередуем блоками по 2)
        rotation_phase = {}
        rotation_count = {}  # сколько смен в текущей фазе
        for emp in self.employees:
            rotation_phase[emp['name']] = random.randint(0, 1)
            rotation_count[emp['name']] = 0

        self._rotation_phase = rotation_phase
        self._rotation_count = rotation_count

        for week_idx, week in enumerate(weeks):
            self._current_week_idx = week_idx
            self._generate_week(week, week_idx, year, month, schedule, prev_nights, weekend_done)

        return schedule

    def _generate_week(self, week, week_idx, year, month, schedule, prev_nights, weekend_done):
        month_days = [d for d in week if d.month == month]
        if not month_days:
            return

        work_map = {}
        for emp in self.employees:
            off = self._off_days(emp, week, prev_nights, month, weekend_done, week_idx)
            work_map[emp['name']] = [d for d in week if d not in off and d.month == month]

        self._assign_all_inside(week, week_idx, work_map, schedule, month)

        for emp in self.by_level.get('level6', []):
            self._assign_office(emp, work_map[emp['name']], schedule)

        self._assign_managers(week, schedule, work_map, week_idx, month)
        self._assign_nights(week, schedule, work_map, prev_nights, month)
        self._assign_sw(week, schedule, work_map, month)

    # ── Off-day calculation ──────────────────────────────────────────────────

    def _off_days(self, emp, week, prev_nights, month, weekend_done, week_idx):
        emp_req = self.requests.get(emp['name'], {})
        forced = set()

        for d in week:
            if emp_req.get(d.strftime('%Y-%m-%d')) in ('off', 'vacation'):
                forced.add(d)

        # Правило 10 (п.9 политики): после ночной смены — следующий день выходной.
        # Правило 9 политики (рекомендация): после ночной — ДВА выходных подряд.
        for d in week:
            prev = d - timedelta(days=1)
            prev_str = prev.strftime('%Y-%m-%d')
            if prev_str in prev_nights.get(emp['name'], set()):
                forced.add(d)
                # Рекомендация: ещё один выходной после ночи (правило п.9)
                next_d = d + timedelta(days=1)
                if next_d in [x for x in week]:
                    forced.add(next_d)

        # Правило 6 политики: Сб+Вс выходные для всех на окладе.
        # Директор (level6): два раза в месяц (п.6 "Политика для директора").
        if emp.get('level') in self.SALARY_LEVELS:
            target_weeks = self._weekend_target_weeks.get(emp['name'], [])
            max_weekends = 2 if emp.get('level') == 'level6' else 1
            if weekend_done.get(emp['name'], 0) < max_weekends and week_idx in target_weeks:
                sat = next((d for d in week if d.weekday() == 5 and d.month == month), None)
                sun = next((d for d in week if d.weekday() == 6 and d.month == month), None)
                if sat and sun and sat not in forced and sun not in forced:
                    forced.add(sat)
                    forced.add(sun)
                    weekend_done[emp['name']] = weekend_done.get(emp['name'], 0) + 1

        month_days = [d for d in week if d.month == month]
        max_off = max(0, len(month_days) - 1)
        target_off = min(2, max_off)
        forced_in_month = forced & set(month_days)

        if len(forced_in_month) >= target_off:
            return forced

        needed = target_off - len(forced_in_month)
        available = [d for d in month_days if d not in forced]
        extra = self._pick_off_days(available, needed, emp, week, week_idx)
        result = forced | set(extra)

        # Правило 8 политики: не более 3 выходных подряд.
        # Если получается 4+ подряд на стыке недель — убираем лишний выходной.
        result = self._trim_consecutive_offs(result, emp, week, month)

        return result

    def _trim_consecutive_offs(self, off_set, emp, week, month):
        """Правило 8: не более 3 выходных подряд. Убираем лишние если 4+."""
        # Строим цепочку из 3 дней вокруг недели (последний день предыдущей недели уже в prev_nights отслеживается)
        # Считаем серии подряд только внутри текущей недели
        month_days = [d for d in week if d.month == month]
        off_list = sorted(d for d in off_set if d.month == month)

        # Ищем серии 4+ подряд (внутри недели)
        to_remove = set()
        if len(off_list) >= 4:
            i = 0
            while i < len(off_list):
                j = i
                while j + 1 < len(off_list) and (off_list[j+1] - off_list[j]).days == 1:
                    j += 1
                run_len = j - i + 1
                # Разрешаем максимум 3 подряд, лишние убираем из середины цепочки
                if run_len > 3:
                    # убираем самый последний из серии (наименее критичный)
                    for k in range(i + 3, j + 1):
                        to_remove.add(off_list[k])
                i = j + 1

        return off_set - to_remove

    def _pick_off_days(self, available, needed, emp, week, week_idx=0):
        if needed <= 0 or not available:
            return []

        inside_pool = [e for e in self.employees
                       if e.get('level') in ('level4', 'level5') and e.get('canInside')]
        pool_idx = next((i for i, e in enumerate(inside_pool) if e['name'] == emp['name']), None)

        if pool_idx is not None:
            n = len(inside_pool)
            # Ротация циклов выходных: 3 canInside → THREE_CYCLE, 4 → FOUR_CYCLE
            # THREE_CYCLE включает Сб+Вс (п.6) — было (4,5) Пт+Сб, исправлено на (5,6) Сб+Вс
            THREE_CYCLE = [
                (0, 1),  # Пн+Вт
                (2, 3),  # Ср+Чт
                (5, 6),  # Сб+Вс
            ]
            FOUR_CYCLE = [
                (0, 1),  # Пн+Вт
                (2, 3),  # Ср+Чт
                (4, 5),  # Пт+Сб
                (5, 6),  # Сб+Вс
            ]
            if n == 3:
                target_wd = THREE_CYCLE[(pool_idx + week_idx) % 3]
            elif n == 4:
                target_wd = FOUR_CYCLE[(pool_idx + week_idx) % 4]
            else:
                target_wd = None

            if target_wd is not None:
                matched = [d for d in available if d.weekday() in target_wd]
                if len(matched) >= 2:
                    return matched[:2] if needed >= 2 else [matched[0]]
                if len(matched) == 1 and needed == 1:
                    return matched

            pairs = [(available[i], available[i+1])
                     for i in range(len(available) - 1)
                     if (available[i+1] - available[i]).days == 1]
            if not pairs:
                return [available[0]] if needed == 1 else available[:needed]
            non_overlapping = pairs[::2] or pairs
            pair = non_overlapping[(pool_idx + week_idx) % len(non_overlapping)]
            return [pair[(pool_idx + week_idx) % 2]] if needed == 1 else list(pair)

        # Non-inside employee
        emp_idx = next((i for i, e in enumerate(self.employees) if e['name'] == emp['name']), 0)
        pairs = [(available[i], available[i+1])
                 for i in range(len(available) - 1)
                 if (available[i+1] - available[i]).days == 1]
        if pairs:
            pair = pairs[(emp_idx + week_idx) % len(pairs)]
            return [pair[(emp_idx + week_idx) % 2]] if needed == 1 else list(pair)
        if needed == 1:
            return [available[(emp_idx + week_idx) % len(available)]]
        return available[-needed:]

    # ── Shift assignment ─────────────────────────────────────────────────────

    def _assign_all_inside(self, week, week_idx, work_map, schedule, month):
        inside_emps = [
            emp for lvl in ('level5', 'level4')
            for emp in self.by_level.get(lvl, [])
            if emp.get('canInside')
        ]
        if not inside_emps:
            return

        names = [e['name'] for e in inside_emps]
        m_count = {n: 0 for n in names}
        e_count = {n: 0 for n in names}
        r_count = {n: 0 for n in names}
        total   = {n: 0 for n in names}
        TARGET = 5
        M_SOFT = 2
        E_SOFT = 2

        sorted_days = sorted(d for d in week if d.month == month)

        def on_day(name, d):
            return any(schedule[d].get(sl) == name for sl in SLOTS)

        def had_evening_prev(name, d):
            # Правило 5: интервал 13ч — запрет вечер→утро
            prev = d - timedelta(days=1)
            if prev not in schedule:
                return False
            return any(schedule[prev].get(sl) == name for sl in self.EVENING_SLOTS)

        def future_days(emp_name, after_d):
            return [x for x in work_map.get(emp_name, []) if x > after_d and x.month == month]

        def pick_slot(candidates, d, count_dict, soft_cap, hard_cap=3, is_morning=False):
            def ok(e):
                if on_day(e['name'], d): return False
                if total[e['name']] >= TARGET: return False
                if is_morning and had_evening_prev(e['name'], d): return False
                return True
            eligible = [e for e in candidates if ok(e) and count_dict[e['name']] < soft_cap]
            if not eligible:
                eligible = [e for e in candidates if ok(e) and count_dict[e['name']] < hard_cap]
            if not eligible:
                return None
            def key(e):
                cnt = count_dict[e['name']]
                fd = future_days(e['name'], d)
                needed = max(0, soft_cap - cnt)
                urgency = max(0, needed - len(fd))
                return (cnt, -urgency, total[e['name']])
            eligible.sort(key=key)
            return eligible[0]

        for d in sorted_days:
            s = schedule[d]
            workers = [e for e in inside_emps if d in work_map.get(e['name'], [])]

            if not s['morningInside']:
                emp = pick_slot(workers, d, m_count, M_SOFT, is_morning=True)
                if emp:
                    s['morningInside'] = emp['name']
                    m_count[emp['name']] += 1
                    total[emp['name']] += 1

            if not s['eveningInside']:
                emp = pick_slot(workers, d, e_count, E_SOFT)
                if emp:
                    s['eveningInside'] = emp['name']
                    e_count[emp['name']] += 1
                    total[emp['name']] += 1

        for emp in sorted(inside_emps, key=lambda e: total[e['name']]):
            if r_count[emp['name']] > 0 or total[emp['name']] >= TARGET:
                continue
            for d in reversed(sorted_days):
                if d not in work_map.get(emp['name'], []):
                    continue
                s = schedule[d]
                if not s['rdm'] and not on_day(emp['name'], d):
                    s['rdm'] = emp['name']
                    r_count[emp['name']] += 1
                    total[emp['name']] += 1
                    break

        for emp in sorted(inside_emps, key=lambda e: total[e['name']]):
            if total[emp['name']] >= TARGET:
                continue
            for d in sorted_days:
                if total[emp['name']] >= TARGET:
                    break
                if d not in work_map.get(emp['name'], []) or on_day(emp['name'], d):
                    continue
                s = schedule[d]
                if not s['morningInside'] and m_count[emp['name']] < 3 and not had_evening_prev(emp['name'], d):
                    s['morningInside'] = emp['name']
                    m_count[emp['name']] += 1; total[emp['name']] += 1
                elif not s['eveningInside'] and e_count[emp['name']] < 3:
                    s['eveningInside'] = emp['name']
                    e_count[emp['name']] += 1; total[emp['name']] += 1
                elif not s['rdm'] and r_count[emp['name']] < 1:
                    s['rdm'] = emp['name']
                    r_count[emp['name']] += 1; total[emp['name']] += 1

        # Pass 4: emergency fill — если слоты всё ещё пустые
        for d in sorted_days:
            s = schedule[d]
            workers = [e for e in inside_emps if d in work_map.get(e['name'], [])]

            if not s['morningInside']:
                candidates = [e for e in workers if not on_day(e['name'], d) and not had_evening_prev(e['name'], d)]
                if not candidates:
                    candidates = [e for e in workers if not on_day(e['name'], d)]
                if candidates:
                    candidates.sort(key=lambda e: (m_count[e['name']], total[e['name']]))
                    emp = candidates[0]
                    s['morningInside'] = emp['name']
                    m_count[emp['name']] += 1; total[emp['name']] += 1

            if not s['eveningInside']:
                candidates = [e for e in workers if not on_day(e['name'], d)]
                if candidates:
                    candidates.sort(key=lambda e: (e_count[e['name']], total[e['name']]))
                    emp = candidates[0]
                    s['eveningInside'] = emp['name']
                    e_count[emp['name']] += 1; total[emp['name']] += 1

    def _assign_office(self, emp, work_days, schedule):
        """Правило 2: директор лидирует сменами открытия и закрытия → office каждый рабочий день (макс 5/нед)."""
        count = 0
        for d in work_days:
            if count >= 5:
                break
            if not schedule[d]['office']:
                schedule[d]['office'] = emp['name']
                count += 1

    def _assign_managers(self, week, schedule, work_map, week_idx, month):
        managers = self.by_level.get('level3', []) + self.by_level.get('level2', [])

        # Правило 7: макс 5 смен/неделю (считаем ВСЕ типы смен включая ночные)
        def shifts_this_week(name):
            return sum(
                1 for d in week for s in ('morningManager', 'eveningManager', 'sw', 'night', 'night2')
                if d.month == month and schedule[d].get(s) == name
            )

        def mornings_this_week(name):
            return sum(1 for d in week if d.month == month and schedule[d].get('morningManager') == name)

        def evenings_this_week(name):
            return sum(1 for d in week if d.month == month and schedule[d].get('eveningManager') == name)

        for d in week:
            if d.month != month:
                continue
            prev_d = d - timedelta(days=1)

            avail = [m for m in managers if d in work_map.get(m['name'], [])]
            avail.sort(key=lambda m: shifts_this_week(m['name']))

            # morningManager
            if not schedule[d]['morningManager']:
                for m in avail:
                    if shifts_this_week(m['name']) >= 5: continue
                    if mornings_this_week(m['name']) >= 2: continue
                    # Правило 5 (п.5 политики): 13ч интервал — запрет вечер→утро
                    had_evening = prev_d in schedule and any(
                        schedule[prev_d].get(s) == m['name'] for s in self.EVENING_SLOTS
                    )
                    if had_evening: continue
                    if any(schedule[d].get(s) == m['name'] for s in SLOTS): continue
                    schedule[d]['morningManager'] = m['name']
                    break

            # eveningManager
            if not schedule[d]['eveningManager']:
                for m in avail:
                    if shifts_this_week(m['name']) >= 5: continue
                    if evenings_this_week(m['name']) >= 2: continue
                    if any(schedule[d].get(s) == m['name'] for s in SLOTS): continue
                    next_d = d + timedelta(days=1)
                    # Правило 5: не ставить вечер если следующий день утро уже назначен
                    if next_d in schedule and schedule[next_d].get('morningManager') == m['name']:
                        continue
                    schedule[d]['eveningManager'] = m['name']
                    break

    def _assign_nights(self, week, schedule, work_map, prev_nights, month):
        """Правило политики: ночные смены — только level3+ (п.1 стр.1 политики).
        Политика: "Управлять сменой в ночные часы допускается менеджером уровня не ниже ПБО (3 уровень)".
        """
        night_pool = self.by_level.get('level3', []) + self.by_level.get('level2', [])
        if not night_pool:
            return

        def nights_this_week(name):
            return sum(
                1 for d in week
                if d.month == month and (schedule[d].get('night') == name or schedule[d].get('night2') == name)
            )

        # Правило 7: макс 5 смен/нед (ночные тоже считаются)
        def shifts_this_week(name):
            return sum(
                1 for d in week for s in ('morningManager', 'eveningManager', 'sw', 'night', 'night2')
                if d.month == month and schedule[d].get(s) == name
            )

        for d in week:
            if d.month != month: continue

            for slot in ('night', 'night2'):
                if schedule[d][slot]: continue
                occupied = {v for k, v in schedule[d].items() if v}
                candidates = [
                    e for e in night_pool
                    if e['name'] not in occupied
                    and d in work_map.get(e['name'], [])
                    and nights_this_week(e['name']) < 2
                    and shifts_this_week(e['name']) < 5
                ]
                candidates.sort(key=lambda e: (nights_this_week(e['name']), shifts_this_week(e['name'])))
                if candidates:
                    emp = candidates[0]
                    schedule[d][slot] = emp['name']
                    prev_nights[emp['name']].add(d.strftime('%Y-%m-%d'))

    def _assign_sw(self, week, schedule, work_map, month):
        sw_pool = self.by_level.get('level3', [])
        sw_this_week = {e['name']: 0 for e in sw_pool}

        def shifts_this_week(name):
            return sum(
                1 for d in week for s in ('morningManager', 'eveningManager', 'sw', 'night', 'night2')
                if d.month == month and schedule[d].get(s) == name
            )

        for d in week:
            if d.month != month: continue
            if schedule[d]['sw']: continue
            if not all(schedule[d].get(s) for s in self.MANDATORY): continue

            occupied = {v for k, v in schedule[d].items() if v}
            candidates = [
                e for e in sw_pool
                if e['name'] not in occupied
                and d in work_map.get(e['name'], [])
                and sw_this_week[e['name']] < 1
                and shifts_this_week(e['name']) < 5
            ]
            if candidates:
                candidates.sort(key=lambda e: sw_this_week[e['name']])
                emp = candidates[0]
                schedule[d]['sw'] = emp['name']
                sw_this_week[emp['name']] += 1


# Auto-seed on startup
try:
    seed_if_empty()
except Exception as _e:
    print('Seed error:', _e)

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') != 'production'
    print(f"Запуск на http://localhost:{port}")
    app.run(debug=debug, host='0.0.0.0', port=port)
