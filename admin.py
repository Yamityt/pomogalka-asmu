from flask import Blueprint, render_template, session, redirect, url_for, request, current_app

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

def admin_required(f):
    def decorated_function(*args, **kwargs):
        # Импортируем внутри функции, чтобы избежать круговой зависимости
        from app import db, User
        
        user_id = session.get('user_id')
        if not user_id:
            return redirect(url_for('login'))
            
        # Используем db.session.get — это работает лучше внутри блюпринтов
        user = db.session.get(User, user_id)
        
        if not user or not user.is_admin:
            return "ДОСТУП ЗАПРЕЩЕН: ТРЕБУЮТСЯ ПРАВА АДМИНИСТРАТОРА", 403
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

@admin_bp.route('/')
@admin_required
def dashboard():
    from app import db, User, Question, MerchOrder
    
    users = User.query.all()
    questions = Question.query.all()
    orders = MerchOrder.query.all()
    
    # Анти-фрод
    suspicious = db.session.execute(db.text(
        "SELECT author_id, helper_id, COUNT(*) as count FROM question "
        "WHERE status='solved' GROUP BY author_id, helper_id HAVING count > 2"
    )).fetchall()

    return render_template('admin/dashboard.html', 
                           users=users, 
                           questions=questions, 
                           orders=orders,
                           suspicious=suspicious)

@admin_bp.route('/ban/<int:user_id>', methods=['POST'])
@admin_required
def ban_user(user_id):
    from app import db, User, socketio
    user = db.session.get(User, user_id)
    reason = request.form.get('reason', 'Нарушение правил системы')

    if user:
        user.is_banned = True
        user.ban_reason = reason
        db.session.commit()
        
        # МГНОВЕННЫЙ КИК через сокеты
        socketio.emit('force_disconnect', 
                     {'reason': reason}, 
                     room=f"user_{user.id}")
        
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/unban/<int:user_id>')
@admin_required
def unban_user(user_id):
    # Импортируем модели внутри
    from models import db, User 
    
    # Ищем пользователя через db.session.get
    user = db.session.get(User, user_id)
    
    if user:
        user.is_banned = False      # Снимаем флаг бана
        user.ban_reason = None     # Очищаем причину (важно!)
        db.session.commit()         # Сохраняем изменения
        
    # Возвращаемся обратно в админку
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/clear_chat/<room_id>')
@admin_required
def clear_chat(room_id):
    from models import db, Message
    # Находим все сообщения этой комнаты и удаляем их
    Message.query.filter_by(room_id=room_id).delete()
    db.session.commit()
    
    # Возвращаемся в мониторинг чатов
    return redirect(url_for('admin.view_all_chats'))

@admin_bp.route('/chats')
@admin_required
def view_all_chats():
    from app import db, Message
    # Получаем все ID комнат, которые существуют в базе
    rooms = db.session.query(Message.room_id).distinct().all()
    # Превращаем список кортежей в обычный список строк
    room_list = [r[0] for r in rooms]
    return render_template('admin/chats_monitor.html', rooms=room_list)

@admin_bp.route('/spy_chat/<room_id>')
@admin_required
def spy_chat(room_id):
    from app import db, Message
    history = Message.query.filter_by(room_id=room_id).order_by(Message.timestamp.asc()).all()
    return render_template('messages.html', room_id=room_id, history=history, active_rooms=['global', room_id])
