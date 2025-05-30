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
import subprocess
import sys
import html # <--- THÊM DÒNG NÀY VÀO ĐÂY!

# Import hàm từ sign_in.py
from sign_in import tu_dong_dang_nhap_email_perplexity, PerplexityAuth # Import cả PerplexityAuth để có thể truy cập BASE_URL nếu cần

app = Flask(__name__)
CORS(app) # Cho phép CORS để frontend có thể gọi được API

# --- Cấu hình Email và Bot (từ perplexity3.4.py) ---
# Cảnh báo: KHÔNG AN TOÀN cho ứng dụng công khai!
# Sử dụng biến môi trường hoặc cấu hình an toàn hơn cho production.
EMAIL_ADDRESS = "vietanh94.thk@gmail.com"  # Thay thế bằng email thật của bạn
EMAIL_PASSWORD = "owus ncqr fhat bkzn" # Thay thế bằng password email thật của bạn hoặc app password
PERPLEXITY_EMAIL = "team@mail.perplexity.ai"  # Sender email
LOGIN_CODE_REQUEST_WINDOW_MINUTES = 5 # Thời gian tìm kiếm email
# ---------------------------------------------------

# Cấu hình logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
app.logger.setLevel(logging.INFO)
# Đặt mức độ debug cho logger của sign_in.py nếu cần
logging.getLogger("perplexity_auth").setLevel(logging.DEBUG)


@app.route('/')
def serve_index():
    """Phục vụ file index.html khi truy cập đường dẫn gốc."""
    return send_from_directory('.', 'index.html')

# --- Các hàm đọc Email và kích hoạt đăng nhập (Từ perplexity3.4.py) ---

def run_sign_in_script(email_address: str):
    """
    Chạy file sign_in.py để kích hoạt gửi email đăng nhập Perplexity.
    Sử dụng hàm từ sign_in.py trực tiếp thay vì subprocess để tránh overhead.
    """
    app.logger.info(f"Kích hoạt gửi email đăng nhập bằng PerplexityAuth cho {email_address}...")
    auth = PerplexityAuth()
    result = auth.login_with_email(email_address)
    if result.success:
        app.logger.info(f"Kích hoạt gửi email thành công: {result.message}")
        return True, result.message, result.data
    else:
        app.logger.error(f"Kích hoạt gửi email thất bại: {result.message}")
        return False, result.message, result.data


def get_sign_in_link_from_emails():
    """Lấy sign-in link từ email gần đây nhất từ Perplexity, trong 5 phút."""
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        mail.select("inbox")

        now_utc = datetime.utcnow().replace(tzinfo=pytz.utc)
        time_window_start = now_utc - timedelta(minutes=LOGIN_CODE_REQUEST_WINDOW_MINUTES)
        # IMAP SINCE search is based on the internal date, not necessarily the email header date
        # Use a more robust search if possible, but for simplicity, we stick to this.
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
            # Ensure date_obj is timezone-aware and converted to UTC for comparison
            if date_obj.tzinfo is None:
                date_obj = pytz.timezone('UTC').localize(date_obj) # Assume UTC if no tzinfo
            else:
                date_obj = date_obj.astimezone(pytz.utc)

            app.logger.debug(f"Email From: {sender}, Date: {date_obj}")

            # Kiểm tra người gửi và thời gian email
            if sender == PERPLEXITY_EMAIL and date_obj >= time_window_start and date_obj <= now_utc:
                for part in email_message.walk():
                    if part.get_content_type() == "text/html":
                        html_body = part.get_payload(decode=True).decode(errors='ignore') # ignore decoding errors
                        # Link mới nhất của Perplexity có thể là:
                        # https://www.perplexity.ai/api/auth/callback/email?callbackUrl=https%3A%2F%2Fwww.perplexity.ai%2F%3Flogin-source%3DemailLogin%23locale%3Den-US
                        # Link này thường nằm trong một thẻ <a>
                        
                        # Cố gắng tìm kiếm link trong cả href và text
                        match = re.search(r'(https://www\.perplexity\.ai/api/auth/callback/email\?callbackUrl=[^"\'>\s]+)', html_body)
                        if match:
                            link = html.unescape(match.group(1)) # Giải mã các ký tự HTML entity
                            app.logger.info(f"Đã tìm thấy liên kết: {link[:100]}...")
                            mail.close()
                            mail.logout()
                            return link
            else:
                app.logger.info(f"Email tìm thấy không khớp điều kiện (sender/date): {sender}, {date_obj}")
        else:
            app.logger.info("Không tìm thấy email nào từ Perplexity trong khoảng thời gian đã định.")
        
        mail.close()
        mail.logout()
        return None
    except imaplib.IMAP4.error as e:
        app.logger.error(f"Lỗi IMAP khi lấy email: {e}. Vui lòng kiểm tra địa chỉ/mật khẩu email hoặc cài đặt IMAP.", exc_info=True)
        return None
    except Exception as e:
        app.logger.error(f"Lỗi không xác định khi lấy email: {e}", exc_info=True)
        return None

# --- Endpoint mới cho Web App ---

@app.route('/api/trigger_login_email', methods=['POST'])
def trigger_login_email():
    """
    Endpoint để kích hoạt quá trình gửi email đăng nhập Perplexity.
    """
    app.logger.info("Nhận được yêu cầu API /api/trigger_login_email")
    
    data = request.get_json()
    if not data or 'email' not in data:
        app.logger.warning("Yêu cầu không hợp lệ: thiếu email")
        return jsonify({
            "success": False, 
            "message": "Vui lòng cung cấp địa chỉ email."
        }), 400
    
    email_to_use = data['email']
    
    # Thực hiện việc chạy sign_in.py hoặc gọi hàm tương đương
    success, message, additional_data = run_sign_in_script(email_address=email_to_use)
    
    response_data = {
        "success": success,
        "message": message,
        "additional_data": additional_data # Có thể chứa thông tin từ Perplexity
    }
    
    return jsonify(response_data), 200

@app.route('/api/check_login_link', methods=['GET'])
def check_login_link():
    """
    Endpoint để kiểm tra và trả về liên kết đăng nhập nếu tìm thấy trong email.
    """
    app.logger.info("Nhận được yêu cầu API /api/check_login_link")
    login_link = get_sign_in_link_from_emails()
    
    if login_link:
        app.logger.info("Đã tìm thấy liên kết đăng nhập!")
        return jsonify({
            "found": True,
            "link": login_link,
            "message": "Đã tìm thấy liên kết đăng nhập Perplexity Pro!"
        }), 200
    else:
        app.logger.info("Chưa tìm thấy liên kết đăng nhập trong email.")
        return jsonify({
            "found": False,
            "message": "Đang chờ liên kết đăng nhập từ Perplexity..."
        }), 200 # Luôn trả về 200 OK nếu không có lỗi server


if __name__ == '__main__':
    app.run(debug=True, port=5000)