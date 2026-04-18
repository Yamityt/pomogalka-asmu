from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import random
import os
from flask_socketio import SocketIO, emit, join_room
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

# 1. ИМПОРТИРУЕМ ВСЁ ИЗ MODELS
from models import db, User, Question, Message, MerchOrder

app = Flask(__name__)

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,  # Запрещает JS доступ к кукам сессии
    SESSION_COOKIE_SECURE=True,    # Куки передаются только по HTTPS (на Render это есть)
    SESSION_COOKIE_SAMESITE='Lax', # Защита от CSRF атак
)
# --- ПОЛНАЯ КОНФИГУРАЦИЯ ---
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'default_key_for_local_dev')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads' # <--- ВОТ ЭТОЙ СТРОКИ НЕ ХВАТАЛО

# Создаем папку, если её нет
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# 2. ИНИЦИАЛИЗИРУЕМ БАЗУ (НЕ СОЗДАВАЙ db = SQLAlchemy(app) ЗДЕСЬ!)
db.init_app(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# --- ДАННЫЕ ДЛЯ РАЗДЕЛОВ ---
LIBRARY_DATA = [
    {'cat': 'Экзамены', 'name': 'Ответы к ГИА: Анатомия', 'type': 'PDF', 'size': '2.1 MB'},
    {'cat': 'Методички', 'name': 'Гистология: Альбом препаратов', 'type': 'PDF', 'size': '15 MB'},
    {'cat': 'Схемы', 'name': 'Биохимия: Цикл Кребса', 'type': 'JPG', 'size': '1.2 MB'}
]

MAP_DATA = [
    {'id': 'bakin', 'title': 'Главный корпус АГМУ', 'addr': 'ул. Бакинская, 121'},
    {'id': 'mech', 'title': 'Учебный корпус №2', 'addr': 'ул. Мечникова, 20'}
]
# Данные для раздела МНО (Наука)
SOCIETIES_DATA = [
    {'name': 'МНО Кафедры Анатомии', 'head': 'проф. Котов С.В.', 'desc': 'Изучение топографической анатомии и вариантной изменчивости сосудов.'},
    {'name': 'МНО Кафедры Биохимии', 'head': 'доц. Левина А.М.', 'desc': 'Исследование молекулярных механизмов обмена веществ.'},
    {'name': 'МНО Кафедры Гистологии', 'head': 'проф. Самойлов И.Р.', 'desc': 'Анализ микроструктур тканей при различных патологиях.'}
]

# --- ИНИЦИАЛИЗАЦИЯ БАЗЫ ---
def seed_db():
    file_path = 'students.txt'
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip(): continue
                try:
                    name, sid, fac, cour, pwd = line.strip().split(':')
                    sid_clean = sid.strip().lower()
                    
                    # Проверяем, есть ли уже такой пользователь
                    if not User.query.filter_by(student_id=sid_clean).first():
                        # Проверяем, является ли он админом
                        is_adm = (sid_clean == 'admin') 
                        
                        new_user = User(
                            fullname=name.strip(), 
                            student_id=sid_clean, 
                            faculty=fac.strip(),
                            course=cour.strip(), 
                            password=generate_password_hash(pwd.strip()),
                            is_admin=is_adm # <--- ПРИСВАИВАЕМ ПРАВА ТУТ
                        )
                        db.session.add(new_user)
                except: continue
        db.session.commit()

with app.app_context():
    db.create_all()
    seed_db()

# --- СИСТЕМНЫЕ ФУНКЦИИ ---
def get_current_user():
    if 'user_id' in session:
        return User.query.get(session['user_id'])
    return None

@app.context_processor
def inject_user():
    return {'current_user': get_current_user()}

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        sid = request.form.get('student_id').strip().lower()
        pwd = request.form.get('password').strip()
        
        user = User.query.filter_by(student_id=sid).first()
        
        # 1. Проверяем существование пользователя и верность пароля
        if user and check_password_hash(user.password, pwd):
            
            # 2. Проверяем, не забанен ли он
            if user.is_banned:
                return render_template('login.html', error=f"Ваш аккаунт заблокирован! Причина: {user.ban_reason}")
            
            # 3. Если ВСЁ ОК — сохраняем IP и логиним
            user.last_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
            db.session.commit()
            
            session['user_id'] = user.id
            session['user_name'] = user.fullname
            return redirect(url_for('index'))
            
        else:
            # Сюда попадаем, если пользователя нет или пароль неверный
            import time
            time.sleep(1) # Замедляем перебор
            return render_template('login.html', error="Неверный ID или пароль")

    return render_template('login.html')

@app.route('/')
def index():
    user = get_current_user()
    if not user: return redirect(url_for('login'))
    
    # Все открытые вопросы (кроме своих)
    questions = Question.query.filter(Question.status == 'open', Question.author_id != user.id).all()
    
    # ТОЛЬКО срочные вопросы для боковой панели
    urgent_qs = Question.query.filter_by(status='open', is_urgent=True).all()
    
    top_users = User.query.order_by(User.points.desc()).limit(10).all()
    
    # Передаем urgent=urgent_qs, чтобы правая сторона не была пустой
    return render_template('index.html', questions=questions, top_users=top_users, urgent=urgent_qs)

@app.route('/messages')
@app.route('/messages/<room_id>')
def chat_room(room_id=None):
    user = get_current_user()
    if not user: return redirect(url_for('login'))
    
    if not room_id:
        return redirect(url_for('chat_room', room_id='global'))

    # Находим все комнаты, где есть ID пользователя (например, "chat_1_2")
    # Ищем и в сообщениях, и в активных вопросах
    all_messages = Message.query.filter(Message.room_id.contains(f"_{user.id}")).all()
    rooms_from_msg = [m.room_id for m in all_messages]
    
    active_questions = Question.query.filter(
        ((Question.author_id == user.id) | (Question.helper_id == user.id)),
        Question.status == 'in_progress'
    ).all()
    
    rooms_from_q = []
    for q in active_questions:
        u_ids = sorted([int(q.author_id), int(q.helper_id)])
        rooms_from_q.append(f"chat_{u_ids[0]}_{u_ids[1]}")

    # Объединяем, убираем дубликаты и всегда добавляем global
    active_rooms = list(set(['global'] + rooms_from_msg + rooms_from_q))
    
    return render_template('messages.html', room_id=room_id, active_rooms=active_rooms)

@app.route('/api/messages/<room_id>')
def get_messages_api(room_id):
    user = get_current_user()
    if not user: return jsonify([])
    
    # Загружаем последние 50 сообщений для этой комнаты
    messages = Message.query.filter_by(room_id=room_id).order_by(Message.timestamp.asc()).all()
    
    history = []
    for m in messages:
        history.append({
            'user': m.author_name,
            'text': m.text,
            'time': m.timestamp.strftime('%H:%M'),
            'is_me': m.author_name == user.fullname
        })
    return jsonify(history)

@app.route('/library')
def library():
    if not get_current_user(): return redirect(url_for('login'))
    return render_template('library.html', files=LIBRARY_DATA)

@app.route('/map')
def map_page():
    if not get_current_user(): return redirect(url_for('login'))
    return render_template('map.html', buildings=MAP_DATA)

@app.route('/profile')
def profile():
    user = get_current_user()
    if not user: return redirect(url_for('login'))
    pending = Question.query.filter_by(author_id=user.id, status='in_progress').all()
    return render_template('profile.html', user=user, pending=pending)

@app.route('/add_question', methods=['POST'])
def add_question():
    user = get_current_user()
    if user.is_admin:
        return "Админы не могут просить о помощи. Вы тут для порядка!", 403
    
    subject = request.form.get('subject')
    text = request.form.get('text')
    if not text or len(text) > 500:
        # Если текста нет или он слишком длинный (больше 500 символов)
        # Мы просто не даем создать заявку
        return "ОШИБКА: Текст должен быть от 1 до 500 символов", 400
    is_urgent = request.form.get('urgent') == 'on' # Проверяем галочку
    
    points = 100 if is_urgent else 50 # Если срочно - даем 100 баллов
    
    new_q = Question(
        subject=subject, 
        text=text,
        author_id=user.id, 
        author_name=user.fullname,
        pts=points,
        is_urgent=is_urgent
    )
    
    db.session.add(new_q)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/api/redeem_merch', methods=['POST'])
def redeem():
    user = get_current_user()
    item = request.json.get('item')
    code = f"AGMU-{random.randint(1000, 9999)}"
    
    # ПРАВИЛЬНЫЕ НАЗВАНИЯ (должны совпадать с кнопками в HTML)
    prices = {
        'Кружка Digital ASMU': 500, 
        'Футболка Helper Team': 1500,
        'Толстовка Limited': 3500
    }
    
    price = prices.get(item)
    if price is None:
        return jsonify({'error': 'Товар не найден'}), 400

    if user.points >= price:
        user.points -= price
        new_order = MerchOrder(user_id=user.id, item_name=item, code=code)
        db.session.add(new_order)
        db.session.commit()
        return jsonify({'code': code})
    
    return jsonify({'error': f'Недостаточно баллов. Нужно {price}, у вас {user.points}'}), 400

@app.route('/give_help/<int:q_id>')
def give_help(q_id):
    user = get_current_user()
    if not user: return redirect(url_for('login'))
    q = Question.query.get(q_id)
    if q and q.status == 'open' and q.author_id != user.id:
        q.status = 'in_progress'
        q.helper_id = user.id
        db.session.commit()
        u_ids = sorted([int(user.id), int(q.author_id)])
        room_id = f"chat_{u_ids[0]}_{u_ids[1]}"
        return redirect(url_for('chat_room', room_id=room_id))
    return redirect(url_for('index'))

@app.route('/confirm_help/<int:q_id>')
def confirm_help(q_id):
    user = get_current_user()
    q = Question.query.get(q_id)
    if q and q.author_id == user.id and q.status == 'in_progress':
        helper = User.query.get(q.helper_id)
        if helper:
            helper.points += q.pts
            helper.helps_done += 1
        q.status = 'solved'
        db.session.commit()
    return redirect(url_for('profile'))

@app.route('/science')
def science():
    if not get_current_user(): return redirect(url_for('login'))
    # Передаем данные в шаблон
    return render_template('mno.html', societies=SOCIETIES_DATA)
    
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/api/search')
def search_api():
    q = request.args.get('q', '').lower()
    results = []
    for f in LIBRARY_DATA:
        if q in f['name'].lower():
            results.append({'type': 'file', 'cat': f['cat'], 'title': f['name'], 'url': '/library'})
    return jsonify(results)

@app.before_request
def check_banned():
    # 1. Получаем пользователя из базы, а не только из сессии
    user = get_current_user()
    
    # 2. Если пользователь существует и он ВСЁ ЕЩЕ забанен
    if user and user.is_banned:
        # Разрешаем только выход, статику и страницу логина (чтобы увидеть ошибку)
        if request.endpoint not in ['logout', 'static', 'login']:
            # Очищаем сессию, чтобы "выкинуть" его
            session.clear()
            return f"""
                <div style="text-align:center; padding:50px; font-family:sans-serif;">
                    <h1 style="color:red;">ДОСТУП ЗАБЛОКИРОВАН</h1>
                    <p>Причина: {user.ban_reason}</p>
                    <hr>
                    <p>Если вы считаете, что это ошибка, обратитесь в Студсовет.</p>
                    <a href='/logout' style="color:blue;">Вернуться на главную</a>
                </div>
            """, 403

@socketio.on('register_user')
def register_user(data):
    if data.get('user_id'):
        join_room(f"user_{data['user_id']}")

@socketio.on('send_msg')
def handle_msg(data):
    if 'user_id' not in session: return
    user = get_current_user()
    
    room = data['room']
    text = data['text']
    
    if not text or len(text) > 100:
        return # Игнорируем слишком длинные сообщения
    # Сохраняем в базу
    new_m = Message(room_id=room, text=text, author_name=user.fullname)
    db.session.add(new_m)
    db.session.commit()
    
    # Отправляем ВСЕМ (включая себя) — убрали include_self=False
    emit('receive_msg', {
        'text': text, 
        'user': user.fullname, 
        'time': datetime.now().strftime('%H:%M'),
        'room_id': room 
    }, room=room)
    
from admin import admin_bp
app.register_blueprint(admin_bp)

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000,  allow_unsafe_werkzeug=True)
