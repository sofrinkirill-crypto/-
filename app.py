"""
McDonald's Schedule Generator — Flask Backend
Политика по составлению расписания менеджеров (декабрь 2025)

Реализованные правила:
 П.2  — менеджеры на окладе (level3-6, включая директора) — лидеры смен открытия/закрытия
 П.4  — последовательность 2У+2В; одна неделя в месяц = 4 смены (доп. выходной)
 П.5  — интервал ≥13ч: запрет вечер→утро следующего дня
 П.6  — Сб+Вс выходные ≥1 раза в месяц для всех level3-6
 П.7  — не более 5 смен в неделю для окладников
 П.8  — не более 3 выходных подряд; нельзя создавать 4+ подряд на стыке недель
 П.9  — после ночной смены рекомендуется 2 совмещённых выходных
 П.10 — следующий день после ночи = выходной
 П.14 — в январские праздники (1-8 янв) не более 3 смен — накопительный счёт
 П.14 — российские праздники с двойной оплатой: level4-5 только morningInside/eveningInside
 Директор п.6 — ДВАЖДЫ в месяц выходные Сб+Вс
 Директор п.9 — вечерняя смена закрытия (eveningInside) приоритетна для директора
"""
from flask import Flask, request, jsonify, render_template
from datetime import date, timedelta
import json, os, uuid, calendar as cal, random

app = Flask(__name__)
DATA_FILE = os.path.join(os.path.dirname(__file__), 'data.json')

SLOTS = ['morningInside', 'morningManager', 'eveningInside', 'eveningManager',
         'night', 'night2', 'rdm', 'office', 'sw']

MORNING_SLOTS = ('morningInside', 'morningManager')
EVENING_SLOTS = ('eveningInside', 'eveningManager', 'night', 'night2')

# Российские нерабочие праздничные дни с двойной оплатой (П.14)
# Формат: (месяц, день)
RU_DOUBLE_PAY_DAYS = {
    (1, 1), (1, 2), (1, 3), (1, 4), (1, 5), (1, 6), (1, 7), (1, 8),
    (2, 23), (3, 8), (5, 1), (5, 2), (5, 9), (6, 12), (11, 4)
}

def is_holiday(d):
    return (d.month, d.day) in RU_DOUBLE_PAY_DAYS

# ─── Storage ─────────────────────────────────────────────────────────────────

DATABASE_URL = os.environ.get('DATABASE_URL')

def _get_pg():
    import psycopg2
    url = DATABASE_URL
    if url and url.startswith('postgres://'):
        url = url.replace('postgres://', 'postgresql://', 1)
    return psycopg2.connect(url)

def _pg_init():
    conn = _get_pg()
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS store (key TEXT PRIMARY KEY, value JSONB NOT NULL)""")
    conn.commit(); cur.close(); conn.close()

def load_data():
    if DATABASE_URL:
        try:
            _pg_init()
            conn = _get_pg(); cur = conn.cursor()
            cur.execute("SELECT key, value FROM store WHERE key IN ('employees','requests','schedules')")
            rows = {r[0]: r[1] for r in cur.fetchall()}
            cur.close(); conn.close()
            return {'employees': rows.get('employees', []),
                    'requests':  rows.get('requests', {}),
                    'schedules': rows.get('schedules', {})}
        except Exception as e:
            print('PG load error:', e)
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'employees': [], 'requests': {}, 'schedules': {}}

def save_data(data):
    if DATABASE_URL:
        try:
            _pg_init()
            conn = _get_pg(); cur = conn.cursor()
            for key in ('employees', 'requests', 'schedules'):
                cur.execute("""INSERT INTO store(key,value) VALUES(%s,%s)
                    ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value""",
                    (key, json.dumps(data.get(key), ensure_ascii=False)))
            conn.commit(); cur.close(); conn.close(); return
        except Exception as e:
            print('PG save error:', e)
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ─── Default employees ───────────────────────────────────────────────────────

DEFAULT_EMPLOYEES = [
    {'name': 'Кирилл',   'level': 'level5', 'canInside': True},
    {'name': 'Олег',     'level': 'level5', 'canInside': True},
    {'name': 'Вова',     'level': 'level5', 'canInside': True},
    {'name': 'Ангелина', 'level': 'level3', 'canInside': False},
    {'name': 'Антон',    'level': 'level3', 'canInside': False},
    {'name': 'Андрей',   'level': 'level3', 'canInside': False},
    {'name': 'Маша',     'level': 'level3', 'canInside': False},
    {'name': 'Ариана',   'level': 'level3', 'canInside': False},
    {'name': 'Лиза',     'level': 'level6', 'canInside': True},
]

def seed_if_empty():
    data = load_data()
    if not data['employees']:
        data['employees'] = [{'id': str(uuid.uuid4()), **e} for e in DEFAULT_EMPLOYEES]
        save_data(data)
        print('Seeded default employees')

# ─── Routes ──────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/employees', methods=['GET'])
def get_employees():
    return jsonify(load_data()['employees'])

@app.route('/api/employees', methods=['POST'])
def add_employee():
    data = load_data()
    emp = request.json; emp['id'] = str(uuid.uuid4())
    data['employees'].append(emp); save_data(data)
    return jsonify(emp), 201

@app.route('/api/employees/bulk', methods=['PUT'])
def bulk_employees():
    data = load_data()
    emps = request.json or []
    for e in emps:
        if not e.get('id'): e['id'] = str(uuid.uuid4())
    data['employees'] = emps; save_data(data)
    return jsonify({'ok': True, 'count': len(emps)})

@app.route('/api/employees/<emp_id>', methods=['PUT'])
def update_employee(emp_id):
    data = load_data()
    for i, emp in enumerate(data['employees']):
        if emp['id'] == emp_id:
            data['employees'][i] = {**emp, **request.json, 'id': emp_id}
            save_data(data); return jsonify(data['employees'][i])
    return jsonify({'error': 'Not found'}), 404

@app.route('/api/employees/<emp_id>', methods=['DELETE'])
def delete_employee(emp_id):
    data = load_data()
    data['employees'] = [e for e in data['employees'] if e['id'] != emp_id]
    save_data(data); return jsonify({'ok': True})

@app.route('/api/requests/bulk', methods=['PUT'])
def bulk_requests():
    data = load_data()
    data['requests'] = request.json or {}; save_data(data)
    return jsonify({'ok': True})

@app.route('/api/reset', methods=['POST'])
def reset_data():
    data = {'employees': [], 'requests': {}, 'schedules': {}}
    save_data(data); seed_if_empty()
    return jsonify({'ok': True})

@app.route('/api/requests', methods=['GET'])
def get_requests():
    data = load_data()
    emp_name = request.args.get('emp')
    if emp_name: return jsonify(data['requests'].get(emp_name, {}))
    return jsonify(data['requests'])

@app.route('/api/requests', methods=['POST'])
def set_request():
    data = load_data(); body = request.json
    emp = body['emp_name']; date_str = body['date']; req_type = body.get('type')
    if emp not in data['requests']: data['requests'][emp] = {}
    if req_type: data['requests'][emp][date_str] = req_type
    else: data['requests'][emp].pop(date_str, None)
    save_data(data); return jsonify({'ok': True})

@app.route('/api/schedule', methods=['GET'])
def get_schedule():
    data = load_data()
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    key = f'{year}-{month}'
    return jsonify(data['schedules'].get(key, {}))

@app.route('/api/schedule/slot', methods=['PUT'])
def update_slot():
    data = load_data(); body = request.json
    key = f'{body["year"]}-{body["month"]}'
    if key not in data['schedules']: data['schedules'][key] = {}
    date_str = body['date_str']
    if date_str not in data['schedules'][key]:
        data['schedules'][key][date_str] = {s: '' for s in SLOTS}
    data['schedules'][key][date_str][body['slot']] = body['value']
    save_data(data); return jsonify({'ok': True})

@app.route('/api/generate', methods=['POST'])
def generate():
    data = load_data(); body = request.json
    year, month = body['year'], body['month']
    scheduler = Scheduler(data['employees'], data['requests'])
    schedule = scheduler.generate(year, month)
    key = f'{year}-{month}'
    data['schedules'][key] = {d.strftime('%Y-%m-%d'): slots for d, slots in schedule.items()}
    save_data(data); return jsonify(data['schedules'][key])

# ─── Scheduling Algorithm ─────────────────────────────────────────────────────

class Scheduler:
    MANDATORY = ['morningInside', 'morningManager', 'eveningInside', 'eveningManager']
    SALARY_LEVELS = ('level2', 'level3', 'level4', 'level5', 'level6')

    JAN_HOLIDAY_START = 1
    JAN_HOLIDAY_END   = 8

    def __init__(self, employees, requests):
        self.employees = employees
        self.requests  = requests
        self.by_level  = {}
        for emp in employees:
            lvl = emp.get('level', 'level3')
            self.by_level.setdefault(lvl, []).append(emp)

    # ── Top-level generate ────────────────────────────────────────────────────

    def generate(self, year, month):
        first = date(year, month, 1)
        last  = date(year, month, cal.monthrange(year, month)[1])
        start = first - timedelta(days=first.weekday())
        end   = last  + timedelta(days=(6 - last.weekday()))

        schedule = {}
        d = start
        while d <= end:
            schedule[d] = {s: '' for s in SLOTS}
            d += timedelta(days=1)

        days  = sorted(schedule.keys())
        weeks = [days[i:i+7] for i in range(0, len(days), 7)]

        prev_nights = {emp['name']: set() for emp in self.employees}

        # П.6: Сб+Вс выходные — недели в месяце с полными Сб+Вс
        sat_sun_weeks = [
            wi for wi, w in enumerate(weeks)
            if any(d.weekday() == 5 and d.month == month for d in w)
            and any(d.weekday() == 6 and d.month == month for d in w)
        ]
        salary_emps = [e for e in self.employees if e.get('level') in self.SALARY_LEVELS]
        self._weekend_target_weeks = {}
        for i, emp in enumerate(salary_emps):
            if emp.get('level') == 'level6' and len(sat_sun_weeks) >= 2:
                n = len(sat_sun_weeks)
                w1 = sat_sun_weeks[i % n]
                w2 = sat_sun_weeks[(i + max(1, n // 2)) % n]
                self._weekend_target_weeks[emp['name']] = sorted({w1, w2})
            elif sat_sun_weeks:
                self._weekend_target_weeks[emp['name']] = [sat_sun_weeks[i % len(sat_sun_weeks)]]
            else:
                self._weekend_target_weeks[emp['name']] = []

        weekend_done = {emp['name']: 0 for emp in self.employees}

        self._gen_nonce = random.randint(0, 99)

        # П.4: ротация 2У+2В
        self._week_start_morning = {}
        for emp in self.employees:
            emp_hash = sum(ord(c) for c in emp['name'])
            morning_weeks = set()
            for wi in range(len(weeks)):
                if ((emp_hash + wi + self._gen_nonce) % 2) == 0:
                    morning_weeks.add(wi)
            self._week_start_morning[emp['name']] = morning_weeks

        # П.4: одна неделя в месяц = 4 смены (доп. выходной)
        # Выбираем неделю с доп. выходным для каждого сотрудника
        month_week_count = len([w for w in weeks if any(d.month == month for d in w)])
        self._extra_off_week = {}
        for i, emp in enumerate(salary_emps):
            emp_hash = sum(ord(c) for c in emp['name'])
            if month_week_count >= 2:
                # Избегаем первую и последнюю неделю (могут быть неполными)
                candidates = list(range(1, month_week_count - 1)) if month_week_count > 2 else [0]
                chosen = candidates[(emp_hash + self._gen_nonce) % len(candidates)]
                self._extra_off_week[emp['name']] = chosen
            else:
                self._extra_off_week[emp['name']] = -1  # не применять

        # П.14: накопительный счёт смен за январские праздники 1-8 янв
        self._jan_holiday_shifts = {emp['name']: 0 for emp in self.employees}

        for week_idx, week in enumerate(weeks):
            self._current_week_idx = week_idx
            self._generate_week(week, week_idx, year, month, schedule, prev_nights, weekend_done)

        # П.8 пост-обработка: устранить 4+ выходных подряд на стыках недель
        self._fix_straddle_offs(schedule, days, month)

        return schedule

    # ── Week generation ───────────────────────────────────────────────────────

    def _generate_week(self, week, week_idx, year, month, schedule, prev_nights, weekend_done):
        month_days = [d for d in week if d.month == month]
        if not month_days:
            return

        work_map = {}
        for emp in self.employees:
            off = self._off_days(emp, week, prev_nights, month, weekend_done, week_idx)
            work_map[emp['name']] = [d for d in week if d not in off and d.month == month]

        plan = self._build_rotation_plan(work_map, week, week_idx, month)

        self._assign_all_inside(week, week_idx, work_map, schedule, month, plan)
        self._assign_managers(week, schedule, work_map, week_idx, month, plan)
        self._assign_managers_emergency(week, schedule, work_map, month)
        self._assign_nights(week, schedule, work_map, prev_nights, month)
        self._assign_sw(week, schedule, work_map, month)

        for emp in self.by_level.get('level6', []):
            self._assign_director_office(emp, work_map[emp['name']], schedule)

        # П.14: январские праздники — накопительный лимит 3 смены
        if month == 1:
            self._enforce_january_holiday_limit(week, schedule)

    # ── Rotation plan (П.4: 2У + 2В) ─────────────────────────────────────────

    def _build_rotation_plan(self, work_map, week, week_idx, month):
        plan = {}
        for emp_name, work_days in work_map.items():
            sorted_days = sorted(d for d in work_days if d.month == month)
            day_plan = {}
            morning_first = week_idx in self._week_start_morning.get(emp_name, set())

            if morning_first:
                sequence = ['morning', 'morning', 'evening', 'evening', 'morning']
            else:
                sequence = ['evening', 'evening', 'morning', 'morning', 'evening']

            for i, d in enumerate(sorted_days):
                day_plan[d] = sequence[i] if i < len(sequence) else 'morning'

            plan[emp_name] = day_plan
        return plan

    # ── Off-day calculation ───────────────────────────────────────────────────

    def _off_days(self, emp, week, prev_nights, month, weekend_done, week_idx):
        emp_req = self.requests.get(emp['name'], {})
        forced = set()

        for d in week:
            if emp_req.get(d.strftime('%Y-%m-%d')) in ('off', 'vacation'):
                forced.add(d)

        # П.10/9: после ночной — выходные
        night_dates = prev_nights.get(emp['name'], set())
        for d in week:
            prev = (d - timedelta(days=1)).strftime('%Y-%m-%d')
            if prev in night_dates:
                forced.add(d)
                next_d = d + timedelta(days=1)
                if next_d in week:
                    forced.add(next_d)

        # П.6: Сб+Вс выходные
        max_weekends = 2 if emp.get('level') == 'level6' else 1
        if emp.get('level') in self.SALARY_LEVELS:
            target_weeks = self._weekend_target_weeks.get(emp['name'], [])
            if weekend_done.get(emp['name'], 0) < max_weekends and week_idx in target_weeks:
                sat = next((d for d in week if d.weekday() == 5 and d.month == month), None)
                sun = next((d for d in week if d.weekday() == 6 and d.month == month), None)
                if sat and sun and sat not in forced and sun not in forced:
                    forced.add(sat); forced.add(sun)
                    weekend_done[emp['name']] = weekend_done.get(emp['name'], 0) + 1

        month_days = [d for d in week if d.month == month]
        max_off = max(0, len(month_days) - 1)

        # П.4: в «доп. выходную» неделю — 3 выходных вместо 2 (4 смены вместо 5)
        is_extra_off_week = (week_idx == self._extra_off_week.get(emp['name'], -1))
        target_off = min(3 if is_extra_off_week else 2, max_off)
        # Только если это полная неделя (7 дней текущего месяца) — иначе 2
        if len(month_days) < 5:
            target_off = min(2, max_off)

        forced_in_month = forced & set(month_days)
        if len(forced_in_month) >= target_off:
            return self._trim_consecutive_offs(forced, month_days)

        needed = target_off - len(forced_in_month)
        available = [d for d in month_days if d not in forced]
        extra = self._pick_off_days(available, needed, emp, week, week_idx)
        result = forced | set(extra)

        return self._trim_consecutive_offs(result, month_days)

    def _pick_off_days(self, available, needed, emp, week, week_idx):
        if needed <= 0 or not available:
            return []

        emp_hash = sum(ord(c) for c in emp['name'])
        inside_pool = [e for e in self.employees
                       if e.get('level') in ('level4', 'level5') and e.get('canInside')]
        pool_idx = next((i for i, e in enumerate(inside_pool) if e['name'] == emp['name']), None)

        if pool_idx is not None:
            n = len(inside_pool)
            THREE_CYCLE = [(0, 1), (2, 3), (5, 6)]
            FOUR_CYCLE  = [(0, 1), (2, 3), (4, 5), (5, 6)]
            if n == 3:
                target_wd = THREE_CYCLE[(pool_idx + week_idx + self._gen_nonce) % 3]
            elif n == 4:
                target_wd = FOUR_CYCLE[(pool_idx + week_idx + self._gen_nonce) % 4]
            else:
                target_wd = None

            if target_wd:
                matched = [d for d in available if d.weekday() in target_wd]
                if len(matched) >= 2:
                    return matched[:2] if needed >= 2 else [matched[0]]
                if len(matched) == 1 and needed == 1:
                    return matched

        # Ищем ПОДРЯД идущую пару (П.6: совмещённые выходные)
        pairs = [(available[i], available[i+1])
                 for i in range(len(available)-1)
                 if (available[i+1]-available[i]).days == 1]
        offset = (emp_hash + week_idx + self._gen_nonce) % max(1, len(pairs) if pairs else 1)
        if pairs:
            pair = pairs[offset % len(pairs)]
            return [pair[(emp_hash + week_idx) % 2]] if needed == 1 else list(pair)
        if needed == 1:
            return [available[(emp_hash + week_idx + self._gen_nonce) % len(available)]]
        return available[:needed]

    def _trim_consecutive_offs(self, off_set, month_days):
        """П.8: убираем 4-й+ выходной из серии подряд внутри недели."""
        off_sorted = sorted(d for d in off_set if d in month_days)
        to_remove = set()
        i = 0
        while i < len(off_sorted):
            j = i
            while j + 1 < len(off_sorted) and (off_sorted[j+1] - off_sorted[j]).days == 1:
                j += 1
            if (j - i + 1) > 3:
                for k in range(i + 3, j + 1):
                    to_remove.add(off_sorted[k])
            i = j + 1
        return off_set - to_remove

    def _fix_straddle_offs(self, schedule, days, month):
        """
        П.8: не допускать 4+ выходных подряд на стыке недель.
        Ищем серии 4+ выходных подряд и принудительно добавляем смену на 3-й день.
        """
        for emp in self.employees:
            name = emp['name']
            run = []
            for d in days:
                if not any(schedule[d].get(s) == name for s in SLOTS):
                    run.append(d)
                    if len(run) >= 4:
                        # 3-й выходной в серии (индекс 2) делаем рабочим
                        target_d = run[2]
                        if target_d.month == month and not any(schedule[target_d].get(s) == name for s in SLOTS):
                            s = schedule[target_d]
                            if emp.get('level') == 'level3' and not s.get('morningManager'):
                                s['morningManager'] = name
                            elif emp.get('canInside') and not s.get('morningInside'):
                                s['morningInside'] = name
                        run = run[3:]  # перезапускаем после исправления
                else:
                    run = []

    # ── Shift assignment ──────────────────────────────────────────────────────

    def _assign_all_inside(self, week, week_idx, work_map, schedule, month, plan):
        """
        П.2: менеджеры на окладе — лидеры смен открытия/закрытия.
        П.14: на праздничные дни с двойной оплатой level4-5 ТОЛЬКО morningInside/eveningInside
              (rdm/office/sw запрещены).
        """
        level6_emps = [e for e in self.by_level.get('level6', []) if e.get('canInside')]
        level5_emps = [e for e in self.by_level.get('level5', []) if e.get('canInside')]
        level4_emps = [e for e in self.by_level.get('level4', []) if e.get('canInside')]

        inside_emps = level6_emps + level5_emps + level4_emps
        if not inside_emps:
            return

        names   = [e['name'] for e in inside_emps]
        m_count = {n: 0 for n in names}
        e_count = {n: 0 for n in names}
        r_count = {n: 0 for n in names}
        total   = {n: 0 for n in names}
        TARGET  = 5

        sorted_days = sorted(d for d in week if d.month == month)

        def on_day(name, d):
            return any(schedule[d].get(sl) == name for sl in SLOTS)

        def had_evening_prev(name, d):
            prev = d - timedelta(days=1)
            if prev not in schedule: return False
            return any(schedule[prev].get(sl) == name for sl in EVENING_SLOTS)

        def future_days(emp_name, after_d):
            return [x for x in work_map.get(emp_name, []) if x > after_d and x.month == month]

        def wants_morning(emp, d):
            return plan.get(emp['name'], {}).get(d) == 'morning'

        def pick_inside(candidates, d, count_dict, soft_cap, is_morning):
            def ok(e):
                if on_day(e['name'], d): return False
                if total[e['name']] >= TARGET: return False
                if is_morning and had_evening_prev(e['name'], d): return False
                return True

            pool = [e for e in candidates if ok(e) and count_dict[e['name']] < soft_cap
                    and (wants_morning(e, d) == is_morning)]
            if not pool:
                pool = [e for e in candidates if ok(e) and count_dict[e['name']] < soft_cap]
            if not pool:
                pool = [e for e in candidates if ok(e) and count_dict[e['name']] < soft_cap + 1]
            if not pool:
                return None

            def sort_key(e):
                fd = future_days(e['name'], d)
                needed  = max(0, soft_cap - count_dict[e['name']])
                urgency = max(0, needed - len(fd))
                return (count_dict[e['name']], -urgency, total[e['name']])

            pool.sort(key=sort_key)
            return pool[0]

        for d in sorted_days:
            s = schedule[d]
            workers = [e for e in inside_emps if d in work_map.get(e['name'], [])]

            if not s['morningInside']:
                non_director = [e for e in workers if e.get('level') != 'level6']
                pool = non_director if non_director else workers
                emp = pick_inside(pool, d, m_count, 2, is_morning=True)
                if emp:
                    s['morningInside'] = emp['name']
                    m_count[emp['name']] += 1; total[emp['name']] += 1

            if not s['eveningInside']:
                director_avail = [e for e in workers if e.get('level') == 'level6']
                if director_avail:
                    emp = pick_inside(director_avail, d, e_count, 2, is_morning=False)
                    if not emp:
                        emp = pick_inside(workers, d, e_count, 2, is_morning=False)
                else:
                    emp = pick_inside(workers, d, e_count, 2, is_morning=False)
                if emp:
                    s['eveningInside'] = emp['name']
                    e_count[emp['name']] += 1; total[emp['name']] += 1

        # Pass 2: RDM — только в НЕ праздничные дни для level4-5 (П.14)
        for emp in sorted(inside_emps, key=lambda e: total[e['name']]):
            if emp.get('level') == 'level6': continue
            if r_count[emp['name']] > 0 or total[emp['name']] >= TARGET: continue
            for d in reversed(sorted_days):
                # П.14: на праздничные дни level4-5 — только shift leading
                if is_holiday(d): continue
                if d not in work_map.get(emp['name'], []): continue
                s = schedule[d]
                if not s['rdm'] and not on_day(emp['name'], d):
                    s['rdm'] = emp['name']
                    r_count[emp['name']] += 1; total[emp['name']] += 1
                    break

        # Pass 3: добираем до 5 смен (кроме праздников — только inside)
        for emp in sorted(inside_emps, key=lambda e: total[e['name']]):
            if total[emp['name']] >= TARGET: continue
            for d in sorted_days:
                if total[emp['name']] >= TARGET: break
                if d not in work_map.get(emp['name'], []) or on_day(emp['name'], d): continue
                s = schedule[d]
                holiday = is_holiday(d)
                if not s['morningInside'] and m_count[emp['name']] < 3 and not had_evening_prev(emp['name'], d):
                    s['morningInside'] = emp['name']
                    m_count[emp['name']] += 1; total[emp['name']] += 1
                elif not s['eveningInside'] and e_count[emp['name']] < 3:
                    s['eveningInside'] = emp['name']
                    e_count[emp['name']] += 1; total[emp['name']] += 1
                elif not holiday and emp.get('level') != 'level6' and not s['rdm'] and r_count[emp['name']] < 1:
                    s['rdm'] = emp['name']
                    r_count[emp['name']] += 1; total[emp['name']] += 1

        # Pass 4: emergency — обязательные слоты без cap
        for d in sorted_days:
            s = schedule[d]
            workers_week = [e for e in inside_emps if d in work_map.get(e['name'], [])]
            workers_any  = [e for e in inside_emps if not on_day(e['name'], d)]

            if not s['morningInside']:
                cands = [e for e in workers_week if not on_day(e['name'], d)
                         and not had_evening_prev(e['name'], d)]
                if not cands: cands = [e for e in workers_week if not on_day(e['name'], d)]
                if not cands: cands = [e for e in workers_any if not had_evening_prev(e['name'], d)]
                if not cands: cands = workers_any
                if cands:
                    cands.sort(key=lambda e: (m_count.get(e['name'],0), total.get(e['name'],0)))
                    emp = cands[0]
                    s['morningInside'] = emp['name']
                    m_count[emp['name']] = m_count.get(emp['name'],0) + 1
                    total[emp['name']]   = total.get(emp['name'],0)   + 1

            if not s['eveningInside']:
                cands = [e for e in workers_week if not on_day(e['name'], d)]
                if not cands: cands = workers_any
                if cands:
                    cands.sort(key=lambda e: (e_count.get(e['name'],0), total.get(e['name'],0)))
                    emp = cands[0]
                    s['eveningInside'] = emp['name']
                    e_count[emp['name']] = e_count.get(emp['name'],0) + 1
                    total[emp['name']]   = total.get(emp['name'],0)   + 1

    def _assign_director_office(self, emp, work_days, schedule):
        """После inside-смен — office для директора (административная работа)."""
        for d in work_days:
            already_on = any(schedule[d].get(s) == emp['name']
                             for s in ('morningInside', 'eveningInside', 'rdm'))
            if not already_on and not schedule[d]['office']:
                schedule[d]['office'] = emp['name']

    def _assign_managers(self, week, schedule, work_map, week_idx, month, plan):
        """
        П.4: level3 — morningManager/eveningManager по ротации 2У+2В.
        П.14: на праздничные дни level3 управляет участками (morningManager/eveningManager).
        П.5: запрет вечер→утро.
        П.7: макс 5 смен/нед.
        """
        managers = self.by_level.get('level3', []) + self.by_level.get('level2', [])

        def shifts_this_week(name):
            return sum(
                1 for d in week for s in ('morningManager','eveningManager','sw','night','night2')
                if d.month == month and schedule[d].get(s) == name
            )

        def mornings_this_week(name):
            return sum(1 for d in week if d.month == month
                       and schedule[d].get('morningManager') == name)

        def evenings_this_week(name):
            return sum(1 for d in week if d.month == month
                       and schedule[d].get('eveningManager') == name)

        for d in week:
            if d.month != month: continue
            prev_d = d - timedelta(days=1)
            avail = [m for m in managers if d in work_map.get(m['name'], [])]

            def sort_by_plan(mgrs, slot_type):
                def key(m):
                    plan_type = plan.get(m['name'], {}).get(d)
                    match = 1 if plan_type == slot_type else 2
                    return (match, shifts_this_week(m['name']))
                return sorted(mgrs, key=key)

            if not schedule[d]['morningManager']:
                for m in sort_by_plan(avail, 'morning'):
                    if shifts_this_week(m['name']) >= 5: continue
                    if mornings_this_week(m['name']) >= 2: continue
                    had_evening = prev_d in schedule and any(
                        schedule[prev_d].get(s) == m['name'] for s in EVENING_SLOTS
                    )
                    if had_evening: continue
                    if any(schedule[d].get(s) == m['name'] for s in SLOTS): continue
                    schedule[d]['morningManager'] = m['name']
                    break

            if not schedule[d]['eveningManager']:
                for m in sort_by_plan(avail, 'evening'):
                    if shifts_this_week(m['name']) >= 5: continue
                    if evenings_this_week(m['name']) >= 2: continue
                    if any(schedule[d].get(s) == m['name'] for s in SLOTS): continue
                    next_d = d + timedelta(days=1)
                    if next_d in schedule and schedule[next_d].get('morningManager') == m['name']:
                        continue
                    schedule[d]['eveningManager'] = m['name']
                    break

    def _assign_managers_emergency(self, week, schedule, work_map, month):
        """Emergency: заполняем пустые morningManager/eveningManager без лимита 5 смен."""
        managers = self.by_level.get('level3', []) + self.by_level.get('level2', [])
        if not managers: return

        for d in week:
            if d.month != month: continue
            prev_d = d - timedelta(days=1)

            if not schedule[d]['morningManager']:
                cands = [m for m in managers
                         if not any(schedule[d].get(s) == m['name'] for s in SLOTS)]
                cands_ok = [m for m in cands
                            if not (prev_d in schedule and
                                    any(schedule[prev_d].get(s) == m['name'] for s in EVENING_SLOTS))]
                if not cands_ok: cands_ok = cands
                if cands_ok:
                    cands_ok.sort(key=lambda m: sum(
                        1 for dd in week for sl in ('morningManager','eveningManager','sw','night','night2')
                        if dd.month == month and schedule[dd].get(sl) == m['name']
                    ))
                    schedule[d]['morningManager'] = cands_ok[0]['name']

            if not schedule[d]['eveningManager']:
                cands = [m for m in managers
                         if not any(schedule[d].get(s) == m['name'] for s in SLOTS)]
                if cands:
                    cands.sort(key=lambda m: sum(
                        1 for dd in week for sl in ('morningManager','eveningManager','sw','night','night2')
                        if dd.month == month and schedule[dd].get(sl) == m['name']
                    ))
                    schedule[d]['eveningManager'] = cands[0]['name']

    def _assign_nights(self, week, schedule, work_map, prev_nights, month):
        """
        П.1: ночные — level3+.
        П.14: ночь перед праздником — level3 (уже выполняется, т.к. night pool = level3).
        """
        night_pool = self.by_level.get('level3', []) + self.by_level.get('level2', [])
        if not night_pool: return

        def nights_this_week(name):
            return sum(1 for d in week if d.month == month
                       and (schedule[d].get('night') == name or schedule[d].get('night2') == name))

        def shifts_this_week(name):
            return sum(
                1 for d in week for s in ('morningManager','eveningManager','sw','night','night2')
                if d.month == month and schedule[d].get(s) == name
            )

        for d in week:
            if d.month != month: continue
            for slot in ('night', 'night2'):
                if schedule[d][slot]: continue
                occupied = {v for k, v in schedule[d].items() if v}
                cands = [
                    e for e in night_pool
                    if e['name'] not in occupied
                    and d in work_map.get(e['name'], [])
                    and nights_this_week(e['name']) < 2
                    and shifts_this_week(e['name']) < 5
                ]
                cands.sort(key=lambda e: (nights_this_week(e['name']), shifts_this_week(e['name'])))
                if cands:
                    emp = cands[0]
                    schedule[d][slot] = emp['name']
                    prev_nights[emp['name']].add(d.strftime('%Y-%m-%d'))

    def _assign_sw(self, week, schedule, work_map, month):
        """SW — только level3, только когда обязательные слоты закрыты, не в праздники."""
        sw_pool = self.by_level.get('level3', [])
        sw_week = {e['name']: 0 for e in sw_pool}

        def shifts_this_week(name):
            return sum(
                1 for d in week for s in ('morningManager','eveningManager','sw','night','night2')
                if d.month == month and schedule[d].get(s) == name
            )

        for d in week:
            if d.month != month: continue
            if schedule[d]['sw']: continue
            if not all(schedule[d].get(s) for s in self.MANDATORY): continue
            # П.14: в праздники SW не планируется
            if is_holiday(d): continue
            occupied = {v for k, v in schedule[d].items() if v}
            cands = [
                e for e in sw_pool
                if e['name'] not in occupied
                and d in work_map.get(e['name'], [])
                and sw_week[e['name']] < 1
                and shifts_this_week(e['name']) < 5
            ]
            if cands:
                cands.sort(key=lambda e: sw_week[e['name']])
                emp = cands[0]
                schedule[d]['sw'] = emp['name']
                sw_week[emp['name']] += 1

    def _enforce_january_holiday_limit(self, week, schedule):
        """
        П.14: в период 1-8 января — не более 3 смен СУММАРНО за весь период.
        Счёт ведётся накопительно через self._jan_holiday_shifts.
        """
        holiday_days = [
            d for d in week
            if d.month == 1 and self.JAN_HOLIDAY_START <= d.day <= self.JAN_HOLIDAY_END
        ]
        if not holiday_days: return

        salary_emps = [e for e in self.employees if e.get('level') in self.SALARY_LEVELS]
        low_priority = ['sw', 'rdm', 'office', 'night2', 'night']

        for emp in salary_emps:
            name = emp['name']
            # Добавляем новые смены этой недели в накопительный счёт
            new_shifts = sum(
                1 for d in holiday_days
                for s in SLOTS if schedule[d].get(s) == name
            )
            self._jan_holiday_shifts[name] = self._jan_holiday_shifts.get(name, 0) + new_shifts

            # Убираем лишние (от конца к началу, только низкоприоритетные)
            over = self._jan_holiday_shifts[name] - 3
            if over <= 0: continue

            for d in reversed(holiday_days):
                if over <= 0: break
                for slot in low_priority:
                    if over <= 0: break
                    if schedule[d].get(slot) == name:
                        schedule[d][slot] = ''
                        self._jan_holiday_shifts[name] -= 1
                        over -= 1


# ─── Startup ──────────────────────────────────────────────────────────────────

try:
    seed_if_empty()
except Exception as _e:
    print('Seed error:', _e)

if __name__ == '__main__':
    port  = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') != 'production'
    print(f"Запуск на http://localhost:{port}")
    app.run(debug=debug, host='0.0.0.0', port=port)
