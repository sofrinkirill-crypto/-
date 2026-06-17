"""
McDonald's Schedule Generator — Flask Backend
Запуск: python app.py  →  http://localhost:5000
"""
from flask import Flask, request, jsonify, render_template
from datetime import date, timedelta
import json, os, uuid, calendar as cal

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
    SALARY_LEVELS = ('level3', 'level4', 'level5', 'level6')

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

        prev_nights = {emp['name']: set() for emp in self.employees}

        # FIX: Сб+Вс выходные раз в месяц для ВСЕХ сотрудников на окладе (не только level6)
        # Разбрасываем по разным неделям чтобы не все в одну
        weekend_done = {emp['name']: False for emp in self.employees}
        salary_emps = [e for e in self.employees if e.get('level') in self.SALARY_LEVELS]
        self._weekend_target_week = {}
        num_weeks = len(weeks)
        for i, emp in enumerate(salary_emps):
            self._weekend_target_week[emp['name']] = i % num_weeks

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

        # FIX: теперь назначает реальных level3 менеджеров
        self._assign_nights(week, schedule, work_map, prev_nights, month)

        self._assign_sw(week, schedule, work_map, month)

    # ── Off-day calculation ──────────────────────────────────────────────────

    def _off_days(self, emp, week, prev_nights, month, weekend_done, week_idx):
        emp_req = self.requests.get(emp['name'], {})
        forced = set()

        for d in week:
            if emp_req.get(d.strftime('%Y-%m-%d')) in ('off', 'vacation'):
                forced.add(d)

        # Обязательный выходной после ночной смены (правило 10 политики)
        for d in week:
            prev = d - timedelta(days=1)
            if prev.strftime('%Y-%m-%d') in prev_nights.get(emp['name'], set()):
                forced.add(d)

        # FIX: Сб+Вс выходные раз в месяц для ВСЕХ сотрудников на окладе (правило 6 политики)
        # Раньше было только для level6
        if emp.get('level') in self.SALARY_LEVELS and not weekend_done.get(emp['name']):
            target_week = self._weekend_target_week.get(emp['name'], 0)
            if week_idx == target_week:
                sat = next((d for d in week if d.weekday() == 5 and d.month == month), None)
                sun = next((d for d in week if d.weekday() == 6 and d.month == month), None)
                if sat and sun and sat not in forced and sun not in forced:
                    forced.add(sat)
                    forced.add(sun)
                    weekend_done[emp['name']] = True

        month_days = [d for d in week if d.month == month]
        max_off = max(0, len(month_days) - 1)
        target_off = min(2, max_off)
        forced_in_month = forced & set(month_days)

        if len(forced_in_month) >= target_off:
            return forced

        needed = target_off - len(forced_in_month)
        available = [d for d in month_days if d not in forced]
        extra = self._pick_off_days(available, needed, emp, week, self._current_week_idx)
        return forced | set(extra)

    def _pick_off_days(self, available, needed, emp, week, week_idx=0):
        if needed <= 0 or not available:
            return []

        inside_pool = [e for e in self.employees
                       if e.get('level') in ('level4', 'level5') and e.get('canInside')]
        pool_idx = next((i for i, e in enumerate(inside_pool) if e['name'] == emp['name']), None)

        if pool_idx is not None:
            n = len(inside_pool)
            # FIX: THREE_CYCLE теперь включает Сб+Вс (было Пт+Сб — воскресенье никогда не выпадало)
            THREE_CYCLE = [
                (0, 1),  # Пн+Вт
                (2, 3),  # Ср+Чт
                (5, 6),  # Сб+Вс  ← было (4, 5) Пт+Сб
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
        EVENING_SLOTS = ('eveningInside', 'eveningManager', 'night', 'night2')

        def on_day(name, d):
            return any(schedule[d].get(sl) == name for sl in SLOTS)

        def had_evening_prev(name, d):
            prev = d - timedelta(days=1)
            if prev not in schedule:
                return False
            return any(schedule[prev].get(sl) == name for sl in EVENING_SLOTS)

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
        count = 0
        for d in work_days:
            if count >= 5:
                break
            if not schedule[d]['office']:
                schedule[d]['office'] = emp['name']
                count += 1

    def _assign_managers(self, week, schedule, work_map, week_idx, month):
        managers = self.by_level.get('level3', []) + self.by_level.get('level2', [])
        EVENING_SLOTS = ('eveningInside', 'eveningManager', 'night', 'night2')

        # FIX: считаем ночные смены тоже — иначе менеджер может получить 6+ смен/неделю
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
                    # FIX: проверяем все вечерние слоты, не только eveningManager
                    had_evening = prev_d in schedule and any(
                        schedule[prev_d].get(s) == m['name'] for s in EVENING_SLOTS
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
                    if next_d in schedule and schedule[next_d].get('morningManager') == m['name']:
                        continue
                    schedule[d]['eveningManager'] = m['name']
                    break

    def _assign_nights(self, week, schedule, work_map, prev_nights, month):
        # FIX: был фильтр e.get('nightShifts') — поля нет ни у одного сотрудника,
        # поэтому ночные смены НИКОГДА не назначались. Теперь используем level3 pool.
        # Политика: "Управлять сменой в ночные часы допускается менеджером уровня не ниже ПБО (3 уровень)"
        night_pool = self.by_level.get('level3', []) + self.by_level.get('level2', [])
        if not night_pool:
            return

        def nights_this_week(name):
            return sum(
                1 for d in week
                if d.month == month and (schedule[d].get('night') == name or schedule[d].get('night2') == name)
            )

        # FIX: считаем все смены (включая ночные) для соблюдения лимита 5/нед
        def shifts_this_week(name):
            return sum(
                1 for d in week for s in ('morningManager', 'eveningManager', 'sw', 'night', 'night2')
                if d.month == month and schedule[d].get(s) == name
            )

        for d in week:
            if d.month != month: continue

            # night
            if not schedule[d]['night']:
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
                    schedule[d]['night'] = emp['name']
                    prev_nights[emp['name']].add(d.strftime('%Y-%m-%d'))

            # night2
            if not schedule[d]['night2']:
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
                    schedule[d]['night2'] = emp['name']
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
