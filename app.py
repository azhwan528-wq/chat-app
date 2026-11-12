from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
import random
import sqlite3
import os
import re
import shutil
from io import BytesIO
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "supersecretkey_ava_2026_secure"

@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response

# ==========================================
# تنظیمات
# ==========================================
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
if not os.path.exists(UPLOAD_FOLDER): os.makedirs(UPLOAD_FOLDER)

ADMIN_EMAIL = "aghwan528@gmail.com" 
ADMIN_PASSWORD = "pnl_admin_ava_a.gh.k.s.a.h" 
SUPPORT_EMAIL = "support@ava.com" 

# ==========================================
# دیتابیس
# ==========================================
def get_db_connection():
    conn = sqlite3.connect('ava.db')
    conn.row_factory = sqlite3.Row 
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        email TEXT UNIQUE NOT NULL, 
        phone TEXT NOT NULL, 
        password_hash TEXT, 
        is_verified INTEGER DEFAULT 0, 
        username TEXT UNIQUE, 
        display_name TEXT, 
        profile_pic TEXT, 
        is_admin INTEGER DEFAULT 0, 
        is_banned INTEGER DEFAULT 0, 
        ban_until TIMESTAMP,
        admin_custom_password TEXT
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS channels (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        name TEXT NOT NULL, 
        description TEXT, 
        owner_email TEXT NOT NULL, 
        is_private INTEGER DEFAULT 0, 
        channel_type TEXT DEFAULT 'channel', 
        profile_pic TEXT, 
        invite_token TEXT UNIQUE,
        is_suspended INTEGER DEFAULT 0,
        suspended_until TIMESTAMP
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS members (id INTEGER PRIMARY KEY AUTOINCREMENT, channel_id INTEGER NOT NULL, user_email TEXT NOT NULL, UNIQUE(channel_id, user_email))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, channel_id INTEGER NOT NULL, sender_email TEXT NOT NULL, message TEXT NOT NULL, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS saved_messages (id INTEGER PRIMARY KEY AUTOINCREMENT, user_email TEXT NOT NULL, message TEXT NOT NULL, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS private_messages (id INTEGER PRIMARY KEY AUTOINCREMENT, sender_email TEXT NOT NULL, receiver_email TEXT NOT NULL, message TEXT NOT NULL, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    cursor.execute("SELECT * FROM users WHERE email = ?", (SUPPORT_EMAIL,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO users (email, phone, is_verified, display_name, username) VALUES (?, '00000000000', 1, 'پشتیبانی آوا', 'support')", (SUPPORT_EMAIL,))
        
    cursor.execute("SELECT * FROM channels WHERE name = 'اطلاع‌رسانی آوا'")
    if not cursor.fetchone():
        invite_token = str(random.randint(100000, 999999))
        cursor.execute("INSERT INTO channels (name, description, owner_email, is_private, channel_type, invite_token) VALUES (?, ?, ?, 1, 'channel', ?)", 
                       ('اطلاع‌رسانی آوا', 'اخبار و اطلاعیه‌های پیام‌رسان آوا', ADMIN_EMAIL, invite_token))
        
    conn.commit()
    conn.close()

init_db()

def convert_to_english_digits(text):
    return text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))

# ==========================================
# توابع کمکی
# ==========================================
def is_user_banned(email):
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    if not user or user['is_banned'] == 0:
        return False
    if user['ban_until']:
        ban_until = datetime.strptime(user['ban_until'], '%Y-%m-%d %H:%M:%S')
        if datetime.now() > ban_until:
            # رفع خودکار بن
            conn = get_db_connection()
            conn.execute("UPDATE users SET is_banned = 0, ban_until = NULL WHERE email = ?", (email,))
            conn.commit()
            conn.close()
            return False
    return True

def is_channel_suspended(channel_id):
    conn = get_db_connection()
    channel = conn.execute("SELECT * FROM channels WHERE id = ?", (channel_id,)).fetchone()
    conn.close()
    if not channel or channel['is_suspended'] == 0:
        return False
    if channel['suspended_until']:
        suspended_until = datetime.strptime(channel['suspended_until'], '%Y-%m-%d %H:%M:%S')
        if datetime.now() > suspended_until:
            conn = get_db_connection()
            conn.execute("UPDATE channels SET is_suspended = 0, suspended_until = NULL WHERE id = ?", (channel_id,))
            conn.commit()
            conn.close()
            return False
    return True

def add_user_to_announcement_channel(email):
    conn = get_db_connection()
    channel = conn.execute("SELECT * FROM channels WHERE name = 'اطلاع‌رسانی آوا'").fetchone()
    if channel:
        try:
            conn.execute("INSERT INTO members (channel_id, user_email) VALUES (?, ?)", (channel['id'], email))
            conn.commit()
        except sqlite3.IntegrityError:
            pass
    conn.close()

# ==========================================
# مسیرهای اصلی
# ==========================================
@app.route('/', methods=['GET', 'POST'])
def login():
    if session.get('is_logged_in'):
        return redirect(url_for('home'))
        
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '').strip()
        
        if not email or not phone or not password:
            flash("لطفاً همه فیلدها را پر کنید.", "error")
            return redirect(url_for('login'))
            
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()
        
        if user:
            if user['password_hash'] and check_password_hash(user['password_hash'], password):
                if is_user_banned(email):
                    conn.close()
                    flash("حساب شما مسدود شده است.", "error")
                    return redirect(url_for('login'))
                conn.close()
                session['user_email'] = email
                session['is_logged_in'] = True
                session.pop('_flashes', None)
                add_user_to_announcement_channel(email)
                return redirect(url_for('home'))
            else:
                conn.close()
                flash("رمز عبور اشتباه است.", "error")
                return redirect(url_for('login'))
        else:
            password_hash = generate_password_hash(password)
            cursor.execute("INSERT INTO users (email, phone, password_hash, is_verified) VALUES (?, ?, ?, 1)", (email, phone, password_hash))
            conn.commit()
            conn.close()
            session['user_email'] = email
            session['is_logged_in'] = True
            add_user_to_announcement_channel(email)
            # پیام خوش‌آمدگویی
            conn = get_db_connection()
            welcome_msg = "🎉 به پیام‌رسان آوا خوش آمدید!\n\nاز این پس می‌توانید گروه و کانال بسازید، با دوستان خود چت کنید و از امکانات برنامه لذت ببرید. اگر سوالی داشتید، از بخش پشتیبانی با ما در ارتباط باشید."
            conn.execute("INSERT INTO private_messages (sender_email, receiver_email, message) VALUES (?, ?, ?)", (SUPPORT_EMAIL, email, welcome_msg))
            conn.commit()
            conn.close()
            return redirect(url_for('home'))
            
    return render_template('login.html')

@app.route('/home')
def home():
    if not session.get('is_logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (session['user_email'],)).fetchone()
    owned_channels = conn.execute("SELECT * FROM channels WHERE owner_email = ? AND name NOT IN ('پشتیبانی آوا', 'اطلاع‌رسانی آوا')", (session['user_email'],)).fetchall()
    joined_channels = conn.execute('''SELECT c.* FROM channels c JOIN members m ON c.id = m.channel_id WHERE m.user_email = ?''', (session['user_email'],)).fetchall()
    conn.close()
    return render_template('home.html', user=user, owned_channels=owned_channels, joined_channels=joined_channels)

@app.route('/logout')
def logout():
    session.clear()
    flash("شما خارج شدید.", "success")
    return redirect(url_for('login'))

@app.route('/delete_account', methods=['POST'])
def delete_account():
    if not session.get('is_logged_in'): return redirect(url_for('login'))
    email = session['user_email']
    conn = get_db_connection()
    conn.execute("DELETE FROM messages WHERE sender_email = ?", (email,))
    conn.execute("DELETE FROM members WHERE user_email = ?", (email,))
    conn.execute("DELETE FROM channels WHERE owner_email = ?", (email,))
    conn.execute("DELETE FROM users WHERE email = ?", (email,))
    conn.execute("DELETE FROM saved_messages WHERE user_email = ?", (email,))
    conn.execute("DELETE FROM private_messages WHERE sender_email = ? OR receiver_email = ?", (email, email))
    conn.commit()
    conn.close()
    session.clear()
    flash("حساب شما به طور کامل حذف شد.", "success")
    return redirect(url_for('login'))

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if not session.get('is_logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (session['user_email'],)).fetchone()
    if request.method == 'POST':
        display_name = request.form.get('display_name', '').strip()
        username = request.form.get('username', '').strip().lower()
        if username and not re.match(r"^[a-z0-9_]+$", username):
            flash("آیدی فقط شامل حروف انگلیسی، اعداد و _ باشد.", "error")
            return redirect(url_for('profile'))
        file = request.files.get('profile_pic')
        filename = user['profile_pic']
        if file and file.filename != '':
            filename = str(random.randint(1000, 9999)) + "_" + secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        try:
            conn.execute("UPDATE users SET display_name = ?, username = ?, profile_pic = ? WHERE email = ?", (display_name, username, filename, session['user_email']))
            conn.commit()
            flash("پروفایل آپدیت شد!", "success")
        except sqlite3.IntegrityError:
            flash("این آیدی قبلا انتخاب شده است.", "error")
        conn.close()
        return redirect(url_for('profile'))
    conn.close()
    return render_template('profile.html', user=user)

@app.route('/support', methods=['GET', 'POST'])
def support_chat():
    if not session.get('is_logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    if request.method == 'POST':
        msg = request.form.get('message', '').strip()
        if msg:
            conn.execute("INSERT INTO private_messages (sender_email, receiver_email, message) VALUES (?, ?, ?)", (session['user_email'], SUPPORT_EMAIL, msg))
            conn.commit()
        return redirect(url_for('support_chat'))
    messages = conn.execute('''SELECT * FROM private_messages WHERE (sender_email = ? AND receiver_email = ?) OR (sender_email = ? AND receiver_email = ?) ORDER BY timestamp ASC''', 
                           (session['user_email'], SUPPORT_EMAIL, SUPPORT_EMAIL, session['user_email'])).fetchall()
    conn.close()
    return render_template('support_chat.html', messages=messages, user_email=session['user_email'], support_email=SUPPORT_EMAIL)

@app.route('/saved', methods=['GET', 'POST'])
def saved_messages():
    if not session.get('is_logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    if request.method == 'POST':
        msg = request.form.get('message', '').strip()
        if msg:
            conn.execute("INSERT INTO saved_messages (user_email, message) VALUES (?, ?)", (session['user_email'], msg))
            conn.commit()
        return redirect(url_for('saved_messages'))
    messages = conn.execute("SELECT * FROM saved_messages WHERE user_email = ? ORDER BY timestamp DESC", (session['user_email'],)).fetchall()
    conn.close()
    return render_template('saved_messages.html', messages=messages)

@app.route('/search', methods=['GET'])
def search():
    if not session.get('is_logged_in'): return redirect(url_for('login'))
    query = request.args.get('q', '').strip().lower()
    results = []
    if query:
        conn = get_db_connection()
        users = conn.execute("SELECT * FROM users WHERE username LIKE ? OR display_name LIKE ?", (f'%{query}%', f'%{query}%')).fetchall()
        channels = conn.execute('''SELECT c.*, (SELECT COUNT(*) FROM members m WHERE m.channel_id = c.id) as member_count 
                                   FROM channels c 
                                   WHERE (c.name LIKE ? OR c.description LIKE ?) AND c.is_private = 0 AND c.name NOT IN ('پشتیبانی آوا', 'اطلاع‌رسانی آوا')
                                   HAVING member_count >= 10''', (f'%{query}%', f'%{query}%')).fetchall()
        conn.close()
        results = {'users': users, 'channels': channels}
    return render_template('search.html', query=query, results=results)

@app.route('/user/<username>')
def user_profile(username):
    if not session.get('is_logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    if not user:
        flash("کاربری یافت نشد.", "error")
        return redirect(url_for('search'))
    return render_template('user_profile.html', user=user)

@app.route('/create/<type>', methods=['GET', 'POST'])
def create_channel(type):
    if not session.get('is_logged_in'): return redirect(url_for('login'))
    if type not in ['channel', 'group']: return redirect(url_for('home'))
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        is_private = 1 if request.form.get('is_private') else 0
        file = request.files.get('profile_pic')
        filename = None
        if file and file.filename != '':
            filename = str(random.randint(1000, 9999)) + "_" + secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        invite_token = str(random.randint(100000, 999999))
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO channels (name, description, owner_email, is_private, channel_type, profile_pic, invite_token) VALUES (?, ?, ?, ?, ?, ?, ?)", (name, description, session['user_email'], is_private, type, filename, invite_token))
        channel_id = cursor.lastrowid
        cursor.execute("INSERT INTO members (channel_id, user_email) VALUES (?, ?)", (channel_id, session['user_email']))
        welcome_msg = f"🎉 به {name} خوش آمدید! این {'کانال' if type == 'channel' else 'گروه'} توسط مدیریت ساخته شد."
        cursor.execute("INSERT INTO messages (channel_id, sender_email, message) VALUES (?, ?, ?)", (channel_id, ADMIN_EMAIL, welcome_msg))
        conn.commit()
        conn.close()
        flash("با موفقیت ساخته شد!", "success")
        return redirect(url_for('home'))
    return render_template('create_channel.html', type=type)

@app.route('/join/<invite_token>')
def join_channel(invite_token):
    if not session.get('is_logged_in'):
        session['next_url'] = url_for('join_channel', invite_token=invite_token)
        return redirect(url_for('login'))
    conn = get_db_connection()
    channel = conn.execute("SELECT * FROM channels WHERE invite_token = ?", (invite_token,)).fetchone()
    if channel:
        if is_channel_suspended(channel['id']):
            conn.close()
            flash("این گروه/کانال به دلیل تخلف تعلیق شده است.", "error")
            return redirect(url_for('home'))
        try:
            conn.execute("INSERT INTO members (channel_id, user_email) VALUES (?, ?)", (channel['id'], session['user_email']))
            conn.commit()
            flash(f"شما به {channel['name']} پیوستید!", "success")
        except sqlite3.IntegrityError:
            flash("شما قبلا عضو هستید.", "info")
        conn.close()
        return redirect(url_for('chat', channel_id=channel['id']))
    conn.close()
    flash("لینک نامعتبر است.", "error")
    return redirect(url_for('home'))

@app.route('/chat/<int:channel_id>', methods=['GET', 'POST'])
def chat(channel_id):
    if not session.get('is_logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    channel = conn.execute("SELECT * FROM channels WHERE id = ?", (channel_id,)).fetchone()
    if not channel:
        conn.close(); return redirect(url_for('home'))
    
    if is_channel_suspended(channel_id):
        conn.close()
        flash("این گروه/کانال تعلیق شده است.", "error")
        return redirect(url_for('home'))
    
    is_member = conn.execute("SELECT * FROM members WHERE channel_id = ? AND user_email = ?", (channel_id, session['user_email'])).fetchone()
    if not is_member and channel['owner_email'] != session['user_email']:
        conn.close(); flash("شما عضو نیستید.", "error"); return redirect(url_for('home'))
    
    if request.method == 'POST':
        msg_text = request.form.get('message', '').strip()
        if msg_text:
            if channel['channel_type'] == 'channel' and channel['owner_email'] != session['user_email']:
                flash("فقط مدیران اجازه ارسال پیام دارند.", "error")
            else:
                conn.execute("INSERT INTO messages (channel_id, sender_email, message) VALUES (?, ?, ?)", (channel_id, session['user_email'], msg_text))
                conn.commit()
        return redirect(url_for('chat', channel_id=channel_id))
    
    messages = conn.execute('''SELECT m.*, u.display_name, u.username FROM messages m LEFT JOIN users u ON m.sender_email = u.email WHERE m.channel_id = ? ORDER BY m.timestamp ASC''', (channel_id,)).fetchall()
    conn.close()
    
    can_send = True
    if channel['channel_type'] == 'channel' and channel['owner_email'] != session['user_email']:
        can_send = False
    
    return render_template('chat.html', channel=channel, messages=messages, user_email=session['user_email'], can_send=can_send)

@app.route('/delete_message/<int:message_id>', methods=['POST'])
def delete_message(message_id):
    if not session.get('is_logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    msg = conn.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
    if msg and (msg['sender_email'] == session['user_email'] or session['user_email'] == ADMIN_EMAIL):
        conn.execute("DELETE FROM messages WHERE id = ?", (message_id,))
        conn.commit()
        flash("پیام حذف شد.", "success")
    else:
        flash("شما اجازه حذف این پیام را ندارید.", "error")
    channel_id = msg['channel_id'] if msg else 0
    conn.close()
    return redirect(url_for('chat', channel_id=channel_id))

# ==========================================
# ⭐ پنل ادمین (کامل)
# ==========================================
@app.route('/admin_panel_secret')
def admin_panel():
    conn = get_db_connection()
    total_users = conn.execute("SELECT COUNT(*) as count FROM users").fetchone()['count']
    total_channels = conn.execute("SELECT COUNT(*) as count FROM channels").fetchone()['count']
    total_messages = conn.execute("SELECT COUNT(*) as count FROM messages").fetchone()['count']
    all_users = conn.execute("SELECT * FROM users WHERE email != ? ORDER BY id DESC", (SUPPORT_EMAIL,)).fetchall()
    all_channels = conn.execute("SELECT * FROM channels WHERE name NOT IN ('پشتیبانی آوا', 'اطلاع‌رسانی آوا') ORDER BY id DESC").fetchall()
    all_messages = conn.execute('''SELECT m.*, c.name as channel_name, u.phone as sender_phone 
                                   FROM messages m 
                                   LEFT JOIN channels c ON m.channel_id = c.id 
                                   LEFT JOIN users u ON m.sender_email = u.email 
                                   ORDER BY m.timestamp DESC''').fetchall()
    all_private_messages = conn.execute('''SELECT pm.*, u.phone as sender_phone 
                                           FROM private_messages pm 
                                           LEFT JOIN users u ON pm.sender_email = u.email 
                                           ORDER BY pm.timestamp DESC''').fetchall()
    conn.close()
    total, used, free = shutil.disk_usage("/")
    total_gb = round(total / (1024**3), 2)
    used_gb = round(used / (1024**3), 2)
    free_gb = round(free / (1024**3), 2)
    return render_template('admin_panel.html', total_users=total_users, total_channels=total_channels, total_messages=total_messages, all_users=all_users, all_channels=all_channels, all_messages=all_messages, all_private_messages=all_private_messages, total_gb=total_gb, used_gb=used_gb, free_gb=free_gb)

@app.route('/admin/delete_message/<int:message_id>', methods=['POST'])
def admin_delete_message(message_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM messages WHERE id = ?", (message_id,))
    conn.commit()
    conn.close()
    flash("پیام حذف شد.", "success")
    return redirect(url_for('admin_panel'))

@app.route('/admin/edit_message/<int:message_id>', methods=['POST'])
def admin_edit_message(message_id):
    new_text = request.form.get('new_text', '').strip()
    if new_text:
        conn = get_db_connection()
        conn.execute("UPDATE messages SET message = ? WHERE id = ?", (new_text, message_id))
        conn.commit()
        conn.close()
        flash("پیام ویرایش شد.", "success")
    return redirect(url_for('admin_panel'))

@app.route('/admin/reply_private/<int:message_id>', methods=['POST'])
def admin_reply_private(message_id):
    reply_text = request.form.get('reply_text', '').strip()
    if reply_text:
        conn = get_db_connection()
        msg = conn.execute("SELECT * FROM private_messages WHERE id = ?", (message_id,)).fetchone()
        if msg:
            conn.execute("INSERT INTO private_messages (sender_email, receiver_email, message) VALUES (?, ?, ?)", (SUPPORT_EMAIL, msg['sender_email'], reply_text))
            conn.commit()
            flash("پاسخ ارسال شد.", "success")
        conn.close()
    return redirect(url_for('admin_panel'))

# ⭐ تعلیق کاربر
@app.route('/admin/ban_user/<int:user_id>', methods=['POST'])
def admin_ban_user(user_id):
    days = int(request.form.get('days', 0))
    if days > 0:
        ban_until = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
        conn = get_db_connection()
        conn.execute("UPDATE users SET is_banned = 1, ban_until = ? WHERE id = ?", (ban_until, user_id))
        conn.commit()
        conn.close()
        flash(f"کاربر به مدت {days} روز مسدود شد.", "success")
    return redirect(url_for('admin_panel'))

# ⭐ رفع تعلیق کاربر
@app.route('/admin/unban_user/<int:user_id>', methods=['POST'])
def admin_unban_user(user_id):
    conn = get_db_connection()
    conn.execute("UPDATE users SET is_banned = 0, ban_until = NULL WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    flash("کاربر از مسدودی خارج شد.", "success")
    return redirect(url_for('admin_panel'))

# ⭐ تعلیق گروه/کانال
@app.route('/admin/suspend_channel/<int:channel_id>', methods=['POST'])
def admin_suspend_channel(channel_id):
    days = int(request.form.get('days', 0))
    if days > 0:
        suspended_until = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
        conn = get_db_connection()
        conn.execute("UPDATE channels SET is_suspended = 1, suspended_until = ? WHERE id = ?", (suspended_until, channel_id))
        conn.commit()
        conn.close()
        flash(f"گروه/کانال به مدت {days} روز تعلیق شد.", "success")
    return redirect(url_for('admin_panel'))

# ⭐ رفع تعلیق گروه/کانال
@app.route('/admin/unsuspend_channel/<int:channel_id>', methods=['POST'])
def admin_unsuspend_channel(channel_id):
    conn = get_db_connection()
    conn.execute("UPDATE channels SET is_suspended = 0, suspended_until = NULL WHERE id = ?", (channel_id,))
    conn.commit()
    conn.close()
    flash("گروه/کانال از تعلیق خارج شد.", "success")
    return redirect(url_for('admin_panel'))

# ⭐ بخش جدید: ارسال پیام هدفمند
@app.route('/admin/target_message', methods=['POST'])
def admin_target_message():
    user_input = request.form.get('user_input', '').strip()
    message_type = request.form.get('message_type', 'support')
    message_text = request.form.get('message_text', '').strip()
    
    if not user_input:
        flash("لطفاً آیدی یا شماره کاربر را وارد کنید.", "error")
        return redirect(url_for('admin_panel'))
    
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE username = ? OR phone = ?", (user_input, user_input)).fetchone()
    
    if not user:
        conn.close()
        flash("کاربر یافت نشد.", "error")
        return redirect(url_for('admin_panel'))
    
    if message_type == 'support':
        if message_text:
            conn.execute("INSERT INTO private_messages (sender_email, receiver_email, message) VALUES (?, ?, ?)", (SUPPORT_EMAIL, user['email'], message_text))
            flash(f"پیام از طرف پشتیبانی به {user['email']} ارسال شد.", "success")
    elif message_type == 'group_link':
        channel = conn.execute("SELECT * FROM channels WHERE owner_email = ? AND channel_type = 'group' LIMIT 1", (user['email'],)).fetchone()
        if channel:
            flash(f"لینک گروه: http://me-chat-1w2h.onrender.com/join/{channel['invite_token']}", "success")
        else:
            flash("این کاربر گروهی ندارد.", "error")
    elif message_type == 'channel_link':
        channel = conn.execute("SELECT * FROM channels WHERE owner_email = ? AND channel_type = 'channel' LIMIT 1", (user['email'],)).fetchone()
        if channel:
            flash(f"لینک کانال: http://me-chat-1w2h.onrender.com/join/{channel['invite_token']}", "success")
        else:
            flash("این کاربر کانالی ندارد.", "error")
    
    conn.commit()
    conn.close()
    return redirect(url_for('admin_panel'))

@app.route('/admin/delete_channel/<int:channel_id>', methods=['POST'])
def admin_delete_channel(channel_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM messages WHERE channel_id = ?", (channel_id,))
    conn.execute("DELETE FROM members WHERE channel_id = ?", (channel_id,))
    conn.execute("DELETE FROM channels WHERE id = ?", (channel_id,))
    conn.commit()
    conn.close()
    flash("کانال/گروه با موفقیت حذف شد.", "success")
    return redirect(url_for('admin_panel'))

@app.route('/admin/backup_database')
def backup_database():
    if not os.path.exists('ava.db'):
        flash("فایل دیتابیس پیدا نشد.", "error")
        return redirect(url_for('admin_panel'))
    with open('ava.db', 'rb') as f:
        db_data = f.read()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"ava_backup_{timestamp}.db"
    return send_file(BytesIO(db_data), mimetype='application/x-sqlite3', as_attachment=True, download_name=filename)

@app.route('/admin/restore_database', methods=['POST'])
def restore_database():
    file = request.files.get('backup_file')
    if file and file.filename.endswith('.db'):
        file.save('ava.db')
        flash("دیتابیس با موفقیت بازیابی شد!", "success")
        return redirect(url_for('admin_panel'))
    else:
        flash("لطفاً یک فایل معتبر با پسوند .db انتخاب کنید.", "error")
        return redirect(url_for('admin_panel'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
