from typing import Protocol, Optional, Any, List
from pydantic import EmailStr, BaseModel


class EmailMessage(BaseModel):
    """Email message structure passed to the transport layer."""
    to_email: EmailStr
    to_name: Optional[str] = None
    subject: str
    html_content: Optional[str] = None
    plain_text_content: Optional[str] = None
    cc: Optional[List[EmailStr]] = None
    bcc: Optional[List[EmailStr]] = None

    def __post_init__(self):
        """Ensure at least one content type is provided"""
        if not self.html_content and not self.plain_text_content:
            raise ValueError("Either html_content or plain_text_content must be provided")


class IEmailTransport(Protocol):
    """Protocol for sending raw email messages over the network."""
    def is_configured(self) -> bool:
        ...

    async def send_email(self, message: EmailMessage) -> bool:
        ...


class ITemplateRenderer(Protocol):
    """Protocol for rendering email templates."""
    def render_html(self, template_name: str, **kwargs: Any) -> str:
        ...
    
    def render_text(self, template_name: str, **kwargs: Any) -> str:
        ...


class INotificationService(Protocol):
    """High-level protocol for business notifications."""
    async def send_welcome_email(self, email: EmailStr, name: str, password: Optional[str] = None) -> bool:
        ...

    async def send_complaint_confirmation(self, email: EmailStr, name: str, complaint_id: str, status: str = "submitted") -> bool:
        ...

    async def send_refill_reminder(self, email: EmailStr, name: str, gas_level: float, threshold: float) -> bool:
        ...

    async def send_leak_detection_alert(self, email: EmailStr, name: str, drop_rate: float, threshold: float) -> bool:
        ...

    async def send_refill_approval(self, email: EmailStr, name: str, request_id: str) -> bool:
        ...

    async def send_refill_rejection(self, email: EmailStr, name: str, request_id: str, reason: str = "") -> bool:
        ...

    async def send_complaint_status_update(self, email: EmailStr, name: str, complaint_id: str, status: str, remark: str = "") -> bool:
        ...

    async def send_password_reset(self, email: EmailStr, name: str, reset_token: str, reset_url: str) -> bool:
        ...
        
    async def send_custom_email(self, to_email: EmailStr, subject: str, html_content: Optional[str] = None, plain_text_content: Optional[str] = None, to_name: Optional[str] = None) -> bool:
        ...
