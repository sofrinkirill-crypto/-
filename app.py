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

    def __init__(self, employees, requests):
        self.employees = employees
        self.requests = requests
        self.by_level = {}
        for emp in employees:
            lvl = emp.get('level', 'level3')
            self.by_level.setdefault(lvl, []).append(emp)

    def generate(self, year, month):
        # Build calendar aligned to Monday
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

        # Track night shifts for rest-day enforcement
        prev_nights = {emp['name']: set() for emp in self.employees}
        # Level6: track if they already got their Sat+Sun off this month
        l6_weekend_done = {emp['name']: False for emp in self.by_level.get('level6', [])}

        for week_idx, week in enumerate(weeks):
            self._current_week_idx = week_idx
            self._generate_week(week, week_idx, year, month, schedule, prev_nights, l6_weekend_done)

        return schedule

    def _generate_week(self, week, week_idx, year, month, schedule, prev_nights, l6_weekend_done):
        month_days = [d for d in week if d.month == month]
        if not month_days:
            return

        # Step 1: Determine who works which days this week
        work_map = {}
        for emp in self.employees:
            off = self._off_days(emp, week, prev_nights, month, l6_weekend_done)
            work_map[emp['name']] = [d for d in week if d not in off and d.month == month]

        # Step 2: Collectively assign inside slots for all canInside employees
        # (level5 and level4 together, using fewest-shifts-first priority)
        self._assign_all_inside(week, week_idx, work_map, schedule, month)

        # Step 3: Level6 office
        for emp in self.by_level.get('level6', []):
            self._assign_office(emp, work_map[emp['name']], schedule)

        # Step 4: Level3 managers
        self._assign_managers(week, schedule, work_map, week_idx, month)

        # Step 5: Nights
        self._assign_nights(week, schedule, work_map, prev_nights, month)

        # Step 6: SW (only if mandatory slots all filled)
        self._assign_sw(week, schedule, work_map, month)

    # ── Off-day calculation ──────────────────────────────────────────────────

    def _off_days(self, emp, week, prev_nights, month, l6_weekend_done):
        emp_req = self.requests.get(emp['name'], {})
        forced = set()

        # Requested off / vacation
        for d in week:
            if emp_req.get(d.strftime('%Y-%m-%d')) in ('off', 'vacation'):
                forced.add(d)

        # Rest after night shift
        for d in week:
            prev = d - timedelta(days=1)
            if prev.strftime('%Y-%m-%d') in prev_nights.get(emp['name'], set()):
                forced.add(d)

        # Level6: one Sat+Sun off per month
        if emp.get('level') == 'level6' and not l6_weekend_done.get(emp['name']):
            sat = next((d for d in week if d.weekday() == 5 and d.month == month), None)
            sun = next((d for d in week if d.weekday() == 6 and d.month == month), None)
            if sat and sun and sat not in forced and sun not in forced:
                forced.add(sat)
                forced.add(sun)
                l6_weekend_done[emp['name']] = True

        # Need exactly 2 days off per week (from current month days)
        month_days = [d for d in week if d.month == month]
        forced_in_month = forced & set(month_days)

        if len(forced_in_month) >= 2:
            return forced

        needed = 2 - len(forced_in_month)
        available = [d for d in month_days if d not in forced]
        extra = self._pick_off_days(available, needed, emp, week, self._current_week_idx)
        return forced | set(extra)

    def _pick_off_days(self, available, needed, emp, week, week_idx=0):
        if needed <= 0 or not available:
            return []

        # ── Determine employee's index within the canInside level4/5 pool ───────
        inside_pool = [e for e in self.employees
                       if e.get('level') in ('level4', 'level5') and e.get('canInside')]
        pool_idx = next((i for i, e in enumerate(inside_pool) if e['name'] == emp['name']), None)

        if pool_idx is not None:
            n = len(inside_pool)
            # ── Special 4-cycle rotation for up to 4 employees ─────────────────
            # Pairs defined by weekday numbers (0=Mon … 6=Sun).
            # The pair at position 3 always contains Sunday (weekday 6) so that
            # exactly one employee is off on Sunday each week, leaving 3 workers
            # for 3 Sunday inside-type slots.
            FOUR_CYCLE = [
                (0, 1),  # Mon+Tue
                (2, 3),  # Wed+Thu
                (4, 5),  # Fri+Sat
                (5, 6),  # Sat+Sun
            ]
            if n <= 4:
                target_wd = FOUR_CYCLE[(pool_idx + week_idx) % 4]
            else:
                # More than 4: fall through to generic stride logic below
                target_wd = None

            if target_wd is not None:
                matched = [d for d in available if d.weekday() in target_wd]
                if len(matched) >= 2:
                    return matched[:2] if needed >= 2 else [matched[0]]
                if len(matched) == 1 and needed == 1:
                    return matched
                # Fallback: pick first available consecutive pair
                # (happens near month boundary where some days are out-of-month)

            # Generic: stride through consecutive pairs
            pairs = [(available[i], available[i+1])
                     for i in range(len(available) - 1)
                     if (available[i+1] - available[i]).days == 1]
            if not pairs:
                return [available[0]] if needed == 1 else available[:needed]
            non_overlapping = pairs[::2] or pairs
            pair = non_overlapping[(pool_idx + week_idx) % len(non_overlapping)]
            return [pair[(pool_idx + week_idx) % 2]] if needed == 1 else list(pair)

        # ── Non-inside employee: simple rotation by global index ─────────────
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
        """Collectively assign morningInside / eveningInside / rdm for all canInside employees.

        Key insight: assigning employees one-by-one lets the first employee hoard slots,
        leaving nothing for later ones. This method assigns slots day-by-day with
        fewest-shifts-first priority so the workload stays balanced.

        Target per employee: 2 mI + 2 eI + 1 rdm = 5 shifts.
        With 4 employees × 2 mI = 8 needed but only 7 mI slots, one employee will get 1 mI
        and 3 eI instead — this is acceptable and noted below.
        """
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
        M_SOFT = 2   # preferred max mornings; relaxed to 3 if needed
        E_SOFT = 2   # preferred max evenings; relaxed to 3 if needed

        sorted_days = sorted(d for d in week if d.month == month)

        EVENING_SLOTS = ('eveningInside', 'eveningManager', 'night', 'night2')
        MORNING_SLOTS = ('morningInside', 'morningManager')

        def on_day(name, d):
            return any(schedule[d].get(sl) == name for sl in SLOTS)

        def had_evening_prev(name, d):
            """True if employee had an evening/night shift the day before d."""
            prev = d - __import__('datetime').timedelta(days=1)
            if prev not in schedule:
                return False
            return any(schedule[prev].get(sl) == name for sl in EVENING_SLOTS)

        def future_days(emp_name, after_d):
            """Work days remaining after today (not including today)."""
            return [x for x in work_map.get(emp_name, []) if x > after_d and x.month == month]

        def pick(candidates, d):
            eligible = [e for e in candidates
                        if not on_day(e['name'], d) and total[e['name']] < TARGET]
            if not eligible:
                return None
            eligible.sort(key=lambda e: e['name'])  # stable secondary
            eligible.sort(key=lambda e: (
                total[e['name']],           # fewest total first
                -len(future_days(e['name'], d)),  # fewest future days = most urgent
            ))
            return eligible[0]

        def pick_slot(candidates, d, count_dict, soft_cap, hard_cap=3, is_morning=False):
            """Pick employee for a slot type with urgency-aware sorting."""
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
                # urgency: slots still needed vs future days available
                needed = max(0, soft_cap - cnt)
                urgency = max(0, needed - len(fd))
                return (cnt, -urgency, total[e['name']])
            eligible.sort(key=key)
            return eligible[0]

        # ── Pass 1: fill mI and eI slot on every day ──────────────────────────
        for d in sorted_days:
            s = schedule[d]
            workers = [e for e in inside_emps if d in work_map.get(e['name'], [])]

            # morningInside
            if not s['morningInside']:
                emp = pick_slot(workers, d, m_count, M_SOFT, is_morning=True)
                if emp:
                    s['morningInside'] = emp['name']
                    m_count[emp['name']] += 1
                    total[emp['name']] += 1

            # eveningInside
            if not s['eveningInside']:
                emp = pick_slot(workers, d, e_count, E_SOFT)
                if emp:
                    s['eveningInside'] = emp['name']
                    e_count[emp['name']] += 1
                    total[emp['name']] += 1

        # ── Pass 2: assign rdm to employees still under TARGET ─────────────────
        # Process most-underserved first; scan work days in REVERSE so rdm goes
        # to the latest available day, keeping early days free for inside slots.
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

        # ── Pass 3: emergency fill — try any slot for employees still short ────
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

        def shifts_this_week(name, slots=('morningManager', 'eveningManager', 'sw')):
            return sum(1 for d in week for s in slots if d.month == month and schedule[d].get(s) == name)

        def mornings_this_week(name):
            return sum(1 for d in week if d.month == month and schedule[d].get('morningManager') == name)

        def evenings_this_week(name):
            return sum(1 for d in week if d.month == month and schedule[d].get('eveningManager') == name)

        for d in week:
            if d.month != month:
                continue
            prev_d = d - timedelta(days=1)

            # Available managers: working this day, under 5 shifts
            avail = [m for m in managers if d in work_map.get(m['name'], [])]
            avail.sort(key=lambda m: shifts_this_week(m['name']))

            # morningManager
            if not schedule[d]['morningManager']:
                for m in avail:
                    if shifts_this_week(m['name']) >= 5: continue
                    if mornings_this_week(m['name']) >= 2: continue
                    # No evening→morning same person
                    prev_ev = schedule[prev_d]['eveningManager'] if prev_d in schedule else ''
                    if prev_ev == m['name']: continue
                    # Not already on this day
                    if any(schedule[d].get(s) == m['name'] for s in SLOTS): continue
                    schedule[d]['morningManager'] = m['name']
                    break

            # eveningManager
            if not schedule[d]['eveningManager']:
                for m in avail:
                    if shifts_this_week(m['name']) >= 5: continue
                    if evenings_this_week(m['name']) >= 2: continue
                    if any(schedule[d].get(s) == m['name'] for s in SLOTS): continue
                    # Evening→morning next day? check
                    next_d = d + timedelta(days=1)
                    if next_d in schedule and schedule[next_d].get('morningManager') == m['name']:
                        continue
                    schedule[d]['eveningManager'] = m['name']
                    break

    def _assign_nights(self, week, schedule, work_map, prev_nights, month):
        night_pool = [e for e in self.employees if e.get('nightShifts')]
        nights_this_week = {e['name']: 0 for e in night_pool}

        for d in week:
            if d.month != month: continue
            if schedule[d]['night']: continue

            occupied = {v for k, v in schedule[d].items() if v}
            candidates = [
                e for e in night_pool
                if e['name'] not in occupied
                and d in work_map.get(e['name'], [])
                and nights_this_week[e['name']] < 2
            ]
            candidates.sort(key=lambda e: nights_this_week[e['name']])

            if candidates:
                emp = candidates[0]
                schedule[d]['night'] = emp['name']
                nights_this_week[emp['name']] += 1
                prev_nights[emp['name']].add(d.strftime('%Y-%m-%d'))

    def _assign_sw(self, week, schedule, work_map, month):
        sw_pool = self.by_level.get('level3', [])
        sw_this_week = {e['name']: 0 for e in sw_pool}

        for d in week:
            if d.month != month: continue
            if schedule[d]['sw']: continue
            # SW only when all mandatory slots are filled
            if not all(schedule[d].get(s) for s in self.MANDATORY): continue

            occupied = {v for k, v in schedule[d].items() if v}
            candidates = [
                e for e in sw_pool
                if e['name'] not in occupied
                and d in work_map.get(e['name'], [])
                and sw_this_week[e['name']] < 1
            ]
            if candidates:
                candidates.sort(key=lambda e: sw_this_week[e['name']])
                emp = candidates[0]
                schedule[d]['sw'] = emp['name']
                sw_this_week[emp['name']] += 1


if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') != 'production'
    print(f"Запуск на http://localhost:{port}")
    app.run(debug=debug, host='0.0.0.0', port=port)
