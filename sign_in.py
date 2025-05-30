import requests
import logging
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass


@dataclass
class LoginResponse:
    """Lớp dữ liệu để chứa kết quả đăng nhập."""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    status_code: Optional[int] = None


class PerplexityAuth:
    """Lớp xử lý xác thực với Perplexity.ai."""
    
    BASE_URL = "https://www.perplexity.ai"
    CSRF_ENDPOINT = "/api/auth/csrf"
    EMAIL_SIGNIN_ENDPOINT = "/api/auth/signin/email"
    
    def __init__(self, logger=None):
        """
        Khởi tạo đối tượng xác thực Perplexity.
        
        Args:
            logger: Đối tượng logger tùy chọn. Nếu không được cung cấp, sẽ tạo mới.
        """
        self.logger = logger or self._setup_logger()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Referer": self.BASE_URL + "/",
            "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"macOS"'
        })
    
    @staticmethod
    def _setup_logger() -> logging.Logger:
        """Thiết lập và trả về logger."""
        logger = logging.getLogger("perplexity_auth")
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> Tuple[bool, Dict[str, Any], int]:
        """
        Thực hiện request HTTP và xử lý lỗi.
        
        Args:
            method: Phương thức HTTP ("get" hoặc "post").
            endpoint: Endpoint API.
            **kwargs: Các tham số bổ sung cho requests.
            
        Returns:
            Tuple[bool, Dict[str, Any], int]: (thành công, dữ liệu response, status code)
        """
        url = f"{self.BASE_URL}{endpoint}"
        self.logger.debug(f"Gửi request {method.upper()} đến {url}")
        
        try:
            if method.lower() == "get":
                response = self.session.get(url, timeout=10, **kwargs)
            else:
                response = self.session.post(url, timeout=10, **kwargs)
            
            response.raise_for_status()
            
            try:
                data = response.json()
            except ValueError:
                self.logger.warning(f"Response không phải dạng JSON: {response.text[:100]}...")
                data = {"raw_response": response.text}
            
            return True, data, response.status_code
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Lỗi request ({method.upper()} {url}): {str(e)}")
            return False, {"error": str(e)}, getattr(e.response, "status_code", 0) if hasattr(e, "response") else 0
    
    def get_csrf_token(self) -> Optional[str]:
        """
        Lấy CSRF Token từ API endpoint.
        
        Returns:
            Optional[str]: CSRF token nếu thành công, None nếu thất bại.
        """
        success, data, _ = self._make_request("get", self.CSRF_ENDPOINT)
        
        if not success:
            return None
            
        csrf_token = data.get("csrfToken")
        if not csrf_token:
            self.logger.error("Không tìm thấy CSRF Token trong response")
            return None
            
        self.logger.debug(f"Đã lấy CSRF token: {csrf_token[:10]}...")
        return csrf_token
    
    def login_with_email(self, email: str, callback_url: str = None) -> LoginResponse:
        """
        Đăng nhập bằng email với Perplexity.ai.
        
        Args:
            email: Địa chỉ email người dùng.
            callback_url: URL callback sau khi đăng nhập (tùy chọn).
            
        Returns:
            LoginResponse: Kết quả đăng nhập.
        """
        # Lấy CSRF token
        csrf_token = self.get_csrf_token()
        if not csrf_token:
            return LoginResponse(
                success=False,
                message="Không thể lấy CSRF token"
            )
        
        # Chuẩn bị dữ liệu đăng nhập
        default_callback = f"{self.BASE_URL}/?login-source=loginButton#locale=en-US"
        login_data = {
            "email": email,
            "callbackUrl": callback_url or default_callback,
            "redirect": "false",
            "csrfToken": csrf_token,
            "json": "true"
        }
        
        # Thêm header cho request đăng nhập
        self.session.headers.update({
            "Content-Type": "application/x-www-form-urlencoded"
        })
        
        # Gửi request đăng nhập
        success, data, status_code = self._make_request(
            "post", 
            self.EMAIL_SIGNIN_ENDPOINT, 
            data=login_data
        )
        
        if success:
            self.logger.info(f"Đăng nhập email thành công! Status code: {status_code}")
            self.logger.info(f"Email đã sử dụng: {email}")
            self.logger.info("Vui lòng kiểm tra email của bạn để lấy mã đăng nhập và nhập vào Perplexity.ai.")
            
            return LoginResponse(
                success=True,
                message="Đăng nhập thành công, vui lòng kiểm tra email của bạn",
                data=data,
                status_code=status_code
            )
        else:
            return LoginResponse(
                success=False,
                message=f"Đăng nhập thất bại: {data.get('error', 'Lỗi không xác định')}",
                data=data,
                status_code=status_code
            )


def tu_dong_dang_nhap_email_perplexity(email_address: str = "vietanh94.thk@gmail.com") -> LoginResponse:
    """
    Tự động gửi request đăng nhập email đến Perplexity.ai.
    
    Args:
        email_address: Địa chỉ email bạn muốn đăng nhập (mặc định là vietanh94.thk@gmail.com).
    
    Returns:
        LoginResponse: Kết quả của quá trình đăng nhập.
    """
    auth = PerplexityAuth()
    return auth.login_with_email(email_address)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Đăng nhập Perplexity.ai bằng email")
    parser.add_argument("--email", type=str, default="vietanh94.thk@gmail.com",
                        help="Địa chỉ email để đăng nhập (mặc định: vietanh94.thk@gmail.com)")
    parser.add_argument("--debug", action="store_true", help="Bật chế độ debug")
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger("perplexity_auth").setLevel(logging.DEBUG)
    
    result = tu_dong_dang_nhap_email_perplexity(args.email)
    
    if result.success:
        print("\n✅ Đăng nhập thành công!")
    else:
        print(f"\n❌ Đăng nhập thất bại: {result.message}")