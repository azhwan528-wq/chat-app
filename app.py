from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
import random
import sqlite3
import os
import re
import shutil
from io import BytesIO
from datetime import datetime
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "supersecretkey_ava_2026_secure"

# ⭐ هدرهای ضد کش: مرورگر همیشه نسخه جدید رو بگیره
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
        admin_custom_password TEXT
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS channels (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, description TEXT, owner_email TEXT NOT NULL, is_private INTEGER DEFAULT 0, channel_type TEXT DEFAULT 'channel', profile_pic TEXT, invite_token TEXT UNIQUE)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS members (id INTEGER PRIMARY KEY AUTOINCREMENT, channel_id INTEGER NOT NULL, user_email TEXT NOT NULL, UNIQUE(channel_id, user_email))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, channel_id INTEGER NOT NULL, sender_email TEXT NOT NULL, message TEXT NOT NULL, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    cursor.execute("SELECT * FROM users WHERE email = ?", (SUPPORT_EMAIL,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO users (email, phone, is_verified, display_name, username) VALUES (?, '00000000000', 1, 'پشتیبانی آوا', 'support')", (SUPPORT_EMAIL,))
        
    conn.commit()
    conn.close()

init_db()

def convert_to_english_digits(text):
    return text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))

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
                if user['is_banned'] == 1:
                    conn.close()
                    flash("حساب شما مسدود شده است.", "error")
                    return redirect(url_for('login'))
                    
                conn.close()
                session['user_email'] = email
                session['is_logged_in'] = True
                session.pop('_flashes', None)
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
            return redirect(url_for('home'))
            
    return render_template('login.html')

@app.route('/home')
def home():
    if not session.get('is_logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (session['user_email'],)).fetchone()
    owned_channels = conn.execute("SELECT * FROM channels WHERE owner_email = ? AND name != 'پشتیبانی آوا'", (session['user_email'],)).fetchall()
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

@app.route('/support')
def support_chat():
    if not session.get('is_logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    support_channel = conn.execute("SELECT * FROM channels WHERE name = 'پشتیبانی آوا' AND owner_email = ?", (SUPPORT_EMAIL,)).fetchone()
    if not support_channel:
        invite_token = str(random.randint(100000, 999999))
        cursor = conn.cursor()
        cursor.execute("INSERT INTO channels (name, description, owner_email, is_private, channel_type, invite_token) VALUES (?, ?, ?, 1, 'channel', ?)", ('پشتیبانی آوا', 'ارتباط با پشتیبانی', SUPPORT_EMAIL, invite_token))
        channel_id = cursor.lastrowid
        conn.commit()
    else:
        channel_id = support_channel['id']
    messages = conn.execute('''SELECT m.*, u.display_name, u.username FROM messages m LEFT JOIN users u ON m.sender_email = u.email WHERE m.channel_id = ? ORDER BY m.timestamp ASC''', (channel_id,)).fetchall()
    conn.close()
    class FakeChannel:
        def __init__(self, id, name):
            self.id = id
            self.name = name
            self.owner_email = SUPPORT_EMAIL
            self.channel_type = 'channel'
            self.invite_token = ''
    fake_channel = FakeChannel(channel_id, 'پشتیبانی آوا')
    return render_template('chat.html', channel=fake_channel, messages=messages, user_email=session['user_email'], can_send=False)

@app.route('/search', methods=['GET'])
def search():
    if not session.get('is_logged_in'): return redirect(url_for('login'))
    query = request.args.get('q', '').strip().lower()
    results = []
    if query:
        conn = get_db_connection()
        users = conn.execute("SELECT * FROM users WHERE username LIKE ? OR display_name LIKE ?", (f'%{query}%', f'%{query}%')).fetchall()
        channels = conn.execute("SELECT * FROM channels WHERE (name LIKE ? OR description LIKE ?) AND is_private = 0", (f'%{query}%', f'%{query}%')).fetchall()
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
    is_member = conn.execute("SELECT * FROM members WHERE channel_id = ? AND user_email = ?", (channel_id, session['user_email'])).fetchone()
    if not is_member and channel['owner_email'] != session['user_email']:
        conn.close(); flash("شما عضو نیستید.", "error"); return redirect(url_for('home'))
    if request.method == 'POST':
        msg_text = request.form.get('message', '').strip()
        if msg_text:
            conn.execute("INSERT INTO messages (channel_id, sender_email, message) VALUES (?, ?, ?)", (channel_id, session['user_email'], msg_text))
            conn.commit()
        return redirect(url_for('chat', channel_id=channel_id))
    messages = conn.execute('''SELECT m.*, u.display_name, u.username FROM messages m LEFT JOIN users u ON m.sender_email = u.email WHERE m.channel_id = ? ORDER BY m.timestamp ASC''', (channel_id,)).fetchall()
    conn.close()
    can_send = True
    if channel['channel_type'] == 'channel' and channel['owner_email'] != session['user_email']:
        can_send = False
    return render_template('chat.html', channel=channel, messages=messages, user_email=session['user_email'], can_send=can_send)

# ==========================================
# ⭐ پنل ادمین (بدون لاگین)
# ==========================================
@app.route('/admin_panel_secret')
def admin_panel():
    # دیگه نیازی به لاگین نیست، مستقیم برو پنل
    conn = get_db_connection()
    total_users = conn.execute("SELECT COUNT(*) as count FROM users").fetchone()['count']
    total_channels = conn.execute("SELECT COUNT(*) as count FROM channels").fetchone()['count']
    total_messages = conn.execute("SELECT COUNT(*) as count FROM messages").fetchone()['count']
    all_users = conn.execute("SELECT * FROM users WHERE email != ? ORDER BY id DESC", (SUPPORT_EMAIL,)).fetchall()
    all_channels = conn.execute("SELECT * FROM channels WHERE name != 'پشتیبانی آوا' ORDER BY id DESC").fetchall()
    conn.close()
    total, used, free = shutil.disk_usage("/")
    total_gb = round(total / (1024**3), 2)
    used_gb = round(used / (1024**3), 2)
    free_gb = round(free / (1024**3), 2)
    return render_template('admin_panel.html', total_users=total_users, total_channels=total_channels, total_messages=total_messages, all_users=all_users, all_channels=all_channels, total_gb=total_gb, used_gb=used_gb, free_gb=free_gb)

@app.route('/admin/broadcast', methods=['POST'])
def admin_broadcast():
    message_text = request.form.get('message_text', '').strip()
    target = request.form.get('target', 'users')
    if not message_text:
        flash("متن پیام نمی‌تواند خالی باشد.", "error")
        return redirect(url_for('admin_panel'))
    conn = get_db_connection()
    cursor = conn.cursor()
    if target == 'users':
        support_channel = cursor.execute("SELECT * FROM channels WHERE name = 'پشتیبانی آوا' AND owner_email = ?", (SUPPORT_EMAIL,)).fetchone()
        if support_channel:
            channel_id = support_channel['id']
            cursor.execute("INSERT INTO messages (channel_id, sender_email, message) VALUES (?, ?, ?)", (channel_id, SUPPORT_EMAIL, message_text))
            flash("پیام همگانی به تمام کاربران ارسال شد.", "success")
        else:
            flash("کانال پشتیبانی یافت نشد.", "error")
    elif target == 'groups':
        all_channels = cursor.execute("SELECT * FROM channels WHERE name != 'پشتیبانی آوا'").fetchall()
        for ch in all_channels:
            cursor.execute("INSERT INTO messages (channel_id, sender_email, message) VALUES (?, ?, ?)", (ch['id'], ADMIN_EMAIL, f"📢 [اطلاعیه مدیریت]: {message_text}"))
        flash(f"پیام همگانی به {len(all_channels)} گروه/کانال ارسال شد.", "success")
    conn.commit()
    conn.close()
    return redirect(url_for('admin_panel'))

@app.route('/admin/user_action/<action>/<int:user_id>', methods=['POST'])
def admin_user_action(action, user_id):
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        conn.close(); flash("کاربر یافت نشد.", "error"); return redirect(url_for('admin_panel'))
    if action == 'ban':
        new_status = 0 if user['is_banned'] == 1 else 1
        conn.execute("UPDATE users SET is_banned = ? WHERE id = ?", (new_status, user_id))
        flash("وضعیت مسدودی تغییر کرد.", "success")
    elif action == 'make_admin':
        new_admin_status = 0 if user['is_admin'] == 1 else 1
        conn.execute("UPDATE users SET is_admin = ? WHERE id = ?", (new_admin_status, user_id))
        flash("وضعیت ادمین تغییر کرد.", "success")
    elif action == 'login_as':
        conn.close()
        session['user_email'] = user['email']
        session['is_logged_in'] = True
        flash(f"شما وارد حساب {user['email']} شدید.", "success")
        return redirect(url_for('home'))
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
        flash("دیتابیس با موفقیت بازیابی شد! لطفاً صفحه را رفرش کنید.", "success")
        return redirect(url_for('admin_panel'))
    else:
        flash("لطفاً یک فایل معتبر با پسوند .db انتخاب کنید.", "error")
        return redirect(url_for('admin_panel'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
