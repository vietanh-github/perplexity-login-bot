# app.py
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import logging
import os
import imaplib
import email
from datetime import datetime, timedelta
import pytz
import re
import html
# from dotenv import load_dotenv
# load_dotenv() # Tải biến môi trường từ .env file

# --- Bỏ import từ sign_in.py nếu bạn loại bỏ hoàn toàn việc kích hoạt ---
# from sign_in import tu_dong_dang_nhap_email_perplexity, PerplexityAuth

app = Flask(__name__)
CORS(app)

# --- Cấu hình Email và Bot ---
# Cảnh báo: KHÔNG AN TOÀN cho ứng dụng công khai!
# Sử dụng biến môi trường hoặc cấu hình an toàn hơn cho production.
# Đảm bảo bạn đã cấu hình biến môi trường trên Render
EMAIL_ADDRESS = "vietanh94.thk@gmail.com" # Thay thế bằng email thật của bạn
EMAIL_PASSWORD = "owus ncqr fhat bkzn" # Thay thế bằng password email thật của bạn hoặc app password
# EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS", "vietanh94.thk@gmail.com") # Lấy từ biến môi trường, cung cấp giá trị mặc định nếu không tìm thấy
# EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "password") # Lấy từ biến môi trường, cung cấp giá trị mặc định nếu không tìm thấy

PERPLEXITY_EMAIL = "team@mail.perplexity.ai"  # Sender email
# Thời gian tìm kiếm email, sẽ được kiểm soát bởi frontend
LOGIN_CODE_REQUEST_WINDOW_MINUTES = 5 # Giữ nguyên giá trị này để hàm get_sign_in_link_from_emails hoạt động đúng
# ---------------------------------------------------

# Cấu hình logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
app.logger.setLevel(logging.INFO)
# Đặt mức độ debug cho logger nếu cần
# logging.getLogger("perplexity_auth").setLevel(logging.DEBUG) # Loại bỏ nếu không dùng sign_in.py

@app.route('/')
def serve_index():
    """Phục vụ file index.html khi truy cập đường dẫn gốc."""
    return send_from_directory('.', 'index.html')

# --- Các hàm đọc Email (Từ perplexity3.4.py) ---

def get_sign_in_link_from_emails_in_window(window_minutes: int):
    """
    Lấy sign-in link từ email gần đây nhất từ Perplexity, trong khoảng thời gian đã cho.
    """
    if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
        app.logger.error("EMAIL_ADDRESS hoặc EMAIL_PASSWORD chưa được cấu hình.")
        return None, "Cấu hình email bị thiếu."

    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        mail.select("inbox")

        now_utc = datetime.utcnow().replace(tzinfo=pytz.utc)
        time_window_start = now_utc - timedelta(minutes=window_minutes)
        time_window_start_str = time_window_start.strftime("%d-%b-%Y")

        search_criteria = f'(FROM "{PERPLEXITY_EMAIL}" SINCE "{time_window_start_str}")'
        app.logger.debug(f"Tìm kiếm email với tiêu chí: {search_criteria}")
        result, data = mail.search(None, search_criteria)
        mail_ids = data[0].split()

        if mail_ids:
            # Lấy email gần đây nhất (last ID in the list)
            latest_email_id = mail_ids[-1]
            app.logger.debug(f"Tìm thấy email ID: {latest_email_id}")

            result, data = mail.fetch(latest_email_id, "(RFC822)")
            raw_email = data[0][1]
            email_message = email.message_from_bytes(raw_email)

            sender = email.utils.parseaddr(email_message["From"])[1]
            date_str = email_message["Date"]
            date_obj = email.utils.parsedate_to_datetime(date_str)
            if date_obj.tzinfo is None:
                date_obj = pytz.timezone('UTC').localize(date_obj)
            else:
                date_obj = date_obj.astimezone(pytz.utc)

            app.logger.debug(f"Email From: {sender}, Date: {date_obj}")

            if sender == PERPLEXITY_EMAIL and date_obj >= time_window_start and date_obj <= now_utc:
                for part in email_message.walk():
                    if part.get_content_type() == "text/html":
                        html_body = part.get_payload(decode=True).decode(errors='ignore')
                        match = re.search(r'(https://www\.perplexity\.ai/api/auth/callback/email\?callbackUrl=[^"\'>\s]+)', html_body)
                        if match:
                            link = html.unescape(match.group(1))
                            app.logger.info(f"Đã tìm thấy liên kết: {link[:100]}...")
                            mail.close()
                            mail.logout()
                            return link, None
            else:
                app.logger.info(f"Email tìm thấy không khớp điều kiện (sender/date): {sender}, {date_obj}")
        else:
            app.logger.info("Không tìm thấy email nào từ Perplexity trong khoảng thời gian đã định.")
        
        mail.close()
        mail.logout()
        return None, "Không tìm thấy liên kết đăng nhập trong email."
    except imaplib.IMAP4.error as e:
        app.logger.error(f"Lỗi IMAP khi lấy email: {e}. Vui lòng kiểm tra địa chỉ/mật khẩu email hoặc cài đặt IMAP.", exc_info=True)
        return None, f"Lỗi IMAP: {e}. Kiểm tra cấu hình email."
    except Exception as e:
        app.logger.error(f"Lỗi không xác định khi lấy email: {e}", exc_info=True)
        return None, f"Lỗi không xác định: {e}"

# --- Endpoint mới cho Web App ---

# Loại bỏ @app.route('/api/trigger_login_email', methods=['POST'])

@app.route('/api/check_login_link', methods=['POST']) # Thay đổi sang POST để nhận window_minutes
def check_login_link():
    """
    Endpoint để kiểm tra và trả về liên kết đăng nhập nếu tìm thấy trong email.
    Frontend sẽ truyền tham số window_minutes.
    """
    app.logger.info("Nhận được yêu cầu API /api/check_login_link")
    
    data = request.get_json()
    # Mặc định kiểm tra trong 1 phút nếu không có tham số
    window_minutes = data.get('window_minutes', 1) 
    
    login_link, error_message = get_sign_in_link_from_emails_in_window(window_minutes)
    
    if login_link:
        app.logger.info("Đã tìm thấy liên kết đăng nhập!")
        return jsonify({
            "found": True,
            "link": login_link,
            "message": "Đã tìm thấy liên kết đăng nhập Perplexity Pro!"
        }), 200
    else:
        app.logger.info(f"Chưa tìm thấy liên kết đăng nhập trong email: {error_message}")
        return jsonify({
            "found": False,
            "message": error_message
        }), 200 # Luôn trả về 200 OK nếu không có lỗi server


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False) # Đặt debug=False cho production