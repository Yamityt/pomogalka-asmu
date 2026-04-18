from flask import Blueprint, render_template, session, redirect, url_for, request, current_app
from models import MerchOrder

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')

        if not user_id:
            return redirect(url_for('login'))

        user = db.session.get(User, user_id)

        if not user or not user.is_admin:
            return "ДОСТУП ЗАПРЕЩЕН: ТРЕБУЮТСЯ ПРАВА АДМИНИСТРАТОРА", 403

        return f(*args, **kwargs)

    return decorated_function

@admin_bp.route('/')
@admin_required
def dashboard():
    from app import db, User, Question, MerchOrder
    
    users = User.query.all()
    questions = Question.query.all()
    orders = MerchOrder.query.order_by(MerchOrder.date_created.desc()).all()
    
    # Анти-фрод
    
    return render_template(
        'admin/dashboard.html',
        users=users,
        all_questions=all_questions,
        total_users=total_users,
        total_questions=total_questions,
        subjects_stats=subjects_stats,
        orders=orders 
    )

@admin_bp.route('/approve_order/<int:order_id>')
def approve_order(order_id):
    order = MerchOrder.query.get(order_id)
    if order:
        order.status = 'approved'
        db.session.commit()
    return redirect('/admin')


@admin_bp.route('/reject_order/<int:order_id>')
def reject_order(order_id):
    order = MerchOrder.query.get(order_id)
    if order:
        order.status = 'rejected'
        db.session.commit()
    return redirect('/admin')

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
