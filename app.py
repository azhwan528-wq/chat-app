import os
import requests
from flask import Flask, render_template, request, redirect, url_for, session, flash
from libsql_client import create_client
from datetime import datetime

app = Flask(__name__)
app.secret_key = "your_super_secret_key" # حتما تغییر بده

# --- CONFIGURATION ---
TURSO_URL = "libsql://avadb-azhwan528-wq.aws-us-east-1.turso.io"
TURSO_TOKEN = "*******"
IMGBB_API_KEY = "dece02b308514ea957c6d0d2cea464e"

# اتصال به دیتابیس Turso
db = create_client(url=TURSO_URL, auth_token=TURSO_TOKEN)

# --- LIMITS CONFIGURATION ---
DAILY_TOTAL_LIMIT_MB = 25
DAILY_PHOTO_LIMIT_MB = 10
DAILY_VIDEO_LIMIT_MB = 25

def get_user_usage(user_id):
    """محاسبه حجم مصرف شده توسط کاربر در امروز"""
    today = datetime.now().strftime('%Y-%m-%d')
    query = """
    SELECT 
        SUM(CASE WHEN file_type = 'photo' THEN file_size ELSE 0 END) as photo_usage,
        SUM(CASE WHEN file_type = 'video' THEN file_size ELSE 0 END) as video_usage,
        SUM(file_size) as total_usage
    FROM media_usage 
    WHERE user_id = ? AND usage_date = ?
    """
    result = db.execute(query, [user_id, today])
    row = result.fetchone()
    if row:
        return {
            "photo": row[0] or 0,
            "video": row[1] or 0,
            "total": row[2] or 0
        }
    return {"photo": 0, "video": 0, "total": 0}

def check_limits(user_id, file_size_mb, file_type):
    """بررسی اینکه آیا کاربر سهمیه دارد یا خیر"""
    usage = get_user_usage(user_id)
    
    if usage['total'] + file_size_mb > DAILY_TOTAL_LIMIT_MB:
        return False, "سهمیه کلی روزانه (25MB) تمام شده است."
    
    if file_type == 'photo' and (usage['photo'] + file_size_mb > DAILY_PHOTO_LIMIT_MB):
        return False, "سهمیه روزانه عکس (10MB) تمام شده است."
    
    if file_type == 'video' and (usage['video'] + file_size_mb > DAILY_VIDEO_LIMIT_MB):
        return False, "سهمیه روزانه ویدیو (25MB) تمام شده است."
    
    return True, "OK"

@app.route('/upload', methods=['POST'])
def upload_media():
    user_id = session.get('user_id') # فرض بر اینکه کاربر لاگین کرده
    if not user_id:
        return "لطفا ابتدا وارد شوید", 403

    file = request.files.get('file')
    if not file:
        return "فایلی یافت نشد", 400

    file_size_mb = len(file.read()) / (1024 * 1024)
    file.seek(0) # بازگرداندن اشاره‌گر فایل به اول برای آپلود
    
    file_type = 'video' if file.content_type.startswith('video') else 'photo'

    # ۱. بررسی محدودیت‌ها
    allowed, message = check_limits(user_id, file_size_mb, file_type)
    if not allowed:
        flash(message)
        return redirect(url_for('index'))

    # ۲. آپلود در ImgBB
    try:
        files = {'image': file}
        payload = {'key': IMGBB_API_KEY}
        response = requests.post("https://api.imgbb.com/1/upload", data=payload, files=files)
        res_data = response.json()

        if res_data.get('success'):
            media_url = res_data['data']['url']
            
            # ۳. ذخیره در دیتابیس (پیام و ثبت مصرف حجم)
            # ثبت پیام در جدول messages
            db.execute("INSERT INTO messages (user_id, content, media_url, media_type) VALUES (?, ?, ?, ?)",
                       [user_id, "New Media", media_url, file_type])
            
            # ثبت حجم مصرف شده در جدول media_usage
            db.execute("INSERT INTO media_usage (user_id, file_size, file_type, usage_date) VALUES (?, ?, ?, ?)",
                       [user_id, file_size_mb, file_type, datetime.now().strftime('%Y-%m-%d')])
            
            db.commit()
            flash("آپلود با موفقیت انجام شد!")
        else:
            flash("خطا در آپلود به ImgBB")
    except Exception as e:
        flash(f"خطای سیستمی: {str(e)}")

    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
