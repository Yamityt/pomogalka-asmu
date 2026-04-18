from flask import Blueprint, render_template, session, redirect, url_for, request
from functools import wraps

from models import db, User, Question, MerchOrder, Message

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


# 🔐 ПРОВЕРКА АДМИНА
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')

        if not user_id:
            return redirect(url_for('login'))

        user = db.session.get(User, user_id)

        if not user or not user.is_admin:
            return "ДОСТУП ЗАПРЕЩЕН", 403

        return f(*args, **kwargs)

    return decorated_function


# 📊 DASHBOARD
@admin_bp.route('/')
@admin_required
def dashboard():
    users = User.query.all()
    all_questions = Question.query.all()
    orders = MerchOrder.query.order_by(MerchOrder.date_created.desc()).all()

    total_users = User.query.count()
    total_questions = Question.query.count()

    subjects_stats = db.session.query(
        Question.subject,
        db.func.count(Question.id)
    ).group_by(Question.subject).all()

    return render_template(
        'admin/dashboard.html',
        users=users,
        all_questions=all_questions,
        total_users=total_users,
        total_questions=total_questions,
        subjects_stats=subjects_stats,
        orders=orders
    )


# ✅ ПОДТВЕРДИТЬ ТАЛОН
@admin_bp.route('/approve_order/<int:order_id>')
@admin_required
def approve_order(order_id):
    order = MerchOrder.query.get(order_id)

    if order:
        order.status = 'approved'
        db.session.commit()

    return redirect(url_for('admin.dashboard'))


# ❌ ОТКЛОНИТЬ ТАЛОН
@admin_bp.route('/reject_order/<int:order_id>')
@admin_required
def reject_order(order_id):
    order = MerchOrder.query.get(order_id)

    if order:
        order.status = 'rejected'
        db.session.commit()

    return redirect(url_for('admin.dashboard'))


# 🚫 БАН
@admin_bp.route('/ban/<int:user_id>', methods=['POST'])
@admin_required
def ban_user(user_id):
    from app import socketio

    user = db.session.get(User, user_id)
    reason = request.form.get('reason', 'Нарушение правил системы')

    if user:
        user.is_banned = True
        user.ban_reason = reason
        db.session.commit()

        socketio.emit(
            'force_disconnect',
            {'reason': reason},
            room=f"user_{user.id}"
        )

    return redirect(url_for('admin.dashboard'))


# ✅ РАЗБАН
@admin_bp.route('/unban/<int:user_id>')
@admin_required
def unban_user(user_id):
    user = db.session.get(User, user_id)

    if user:
        user.is_banned = False
        user.ban_reason = None
        db.session.commit()

    return redirect(url_for('admin.dashboard'))


# 🧹 ОЧИСТКА ЧАТА
@admin_bp.route('/clear_chat/<room_id>')
@admin_required
def clear_chat(room_id):
    Message.query.filter_by(room_id=room_id).delete()
    db.session.commit()

    return redirect(url_for('admin.view_all_chats'))


# 💬 СПИСОК ЧАТОВ
@admin_bp.route('/chats')
@admin_required
def view_all_chats():
    rooms = db.session.query(Message.room_id).distinct().all()
    room_list = [r[0] for r in rooms]

    return render_template('admin/chats_monitor.html', rooms=room_list)


# 👁️ ПРОСМОТР ЧАТА
@admin_bp.route('/spy_chat/<room_id>')
@admin_required
def spy_chat(room_id):
    history = Message.query.filter_by(room_id=room_id).order_by(Message.timestamp.asc()).all()

    return render_template(
        'messages.html',
        room_id=room_id,
        history=history,
        active_rooms=['global', room_id]
    )
