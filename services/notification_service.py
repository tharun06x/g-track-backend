"""
Notification Service for G-Track Backend

Orchestrates the business logic of notifications by combining
the TemplateRenderer (presentation) and EmailTransport (network).
"""

from pydantic import EmailStr
import logging
from typing import Optional

from services.email_interfaces import INotificationService, IEmailTransport, ITemplateRenderer, EmailMessage

logger = logging.getLogger(__name__)


class NotificationService(INotificationService):
    """
    High-level service for sending domain-specific emails.
    Depends on an IEmailTransport and an ITemplateRenderer.
    """

    def __init__(self, transport: IEmailTransport, renderer: ITemplateRenderer):
        self.transport = transport
        self.renderer = renderer

    async def send_welcome_email(self, email: EmailStr, name: str, password: Optional[str] = None) -> bool:
        html = self.renderer.render_html("welcome", name=name)
        text = self.renderer.render_text("welcome", name=name)
        
        message = EmailMessage(
            to_email=email,
            to_name=name,
            subject="Welcome to G-Track - Smart Gas Management Starts Here! 🚀",
            html_content=html,
            plain_text_content=text,
        )
        return await self.transport.send_email(message)

    async def send_complaint_confirmation(
        self, email: EmailStr, name: str, complaint_id: str, status: str = "submitted"
    ) -> bool:
        html = self.renderer.render_html("complaint_confirmation", name=name, complaint_id=complaint_id, status=status)
        text = f"Complaint Received ✓\nHi {name},\nComplaint ID: {complaint_id}\nStatus: {status.upper()}"
        
        message = EmailMessage(
            to_email=email,
            to_name=name,
            subject=f"Complaint Confirmation - ID: {complaint_id}",
            html_content=html,
            plain_text_content=text,
        )
        return await self.transport.send_email(message)

    async def send_refill_reminder(
        self, email: EmailStr, name: str, gas_level: float, threshold: float
    ) -> bool:
        html = self.renderer.render_html("refill_reminder", name=name, gas_level=gas_level, threshold=threshold)
        text = f"Gas Level Low ⚠️\nHi {name},\nCurrent Gas Level: {gas_level:.1f}%\nThreshold Limit: {threshold:.1f}%"
        
        message = EmailMessage(
            to_email=email,
            to_name=name,
            subject="Gas Level Reminder - Please Order Refill Soon",
            html_content=html,
            plain_text_content=text,
        )
        return await self.transport.send_email(message)

    async def send_leak_detection_alert(
        self, email: EmailStr, name: str, drop_rate: float, threshold: float
    ) -> bool:
        html = self.renderer.render_html("leak_alert", name=name, drop_rate=drop_rate, threshold=threshold)
        text = f"⚠️ GAS LEAK DETECTED!\nHi {name},\nCurrent Drop Rate: {drop_rate:.6f} kg/s\nAlert Threshold: {threshold:.6f} kg/s"
        
        message = EmailMessage(
            to_email=email,
            to_name=name,
            subject="🚨 URGENT: Gas Leak Detected - Take Action Now!",
            html_content=html,
            plain_text_content=text,
        )
        return await self.transport.send_email(message)

    async def send_refill_approval(
        self, email: EmailStr, name: str, request_id: str
    ) -> bool:
        html = self.renderer.render_html("refill_approval", name=name, request_id=request_id)
        text = f"✓ Refill Request Approved!\nHi {name},\nRequest ID: {request_id}\nStatus: APPROVED"
        
        message = EmailMessage(
            to_email=email,
            to_name=name,
            subject=f"Refill Request Approved - ID: {request_id}",
            html_content=html,
            plain_text_content=text,
        )
        return await self.transport.send_email(message)

    async def send_refill_rejection(
        self, email: EmailStr, name: str, request_id: str, reason: str = ""
    ) -> bool:
        html = self.renderer.render_html("refill_rejection", name=name, request_id=request_id, reason=reason)
        text = f"Refill Request Status\nHi {name},\nRequest ID: {request_id}\nStatus: REJECTED\nReason: {reason}"
        
        message = EmailMessage(
            to_email=email,
            to_name=name,
            subject=f"Refill Request Rejected - ID: {request_id}",
            html_content=html,
            plain_text_content=text,
        )
        return await self.transport.send_email(message)

    async def send_complaint_status_update(
        self, email: EmailStr, name: str, complaint_id: str, status: str, remark: str = ""
    ) -> bool:
        status_color_map = {
            "Open": "#ff9800",
            "In Progress": "#2196F3",
            "Resolved": "#4CAF50",
            "Closed": "#424242"
        }
        status_color = status_color_map.get(status, "#333")
        
        html = self.renderer.render_html("complaint_update", name=name, complaint_id=complaint_id, status=status, remark=remark, status_color=status_color)
        text = f"Complaint Status Updated\nHi {name},\nComplaint ID: {complaint_id}\nStatus: {status.upper()}\nRemark: {remark}"
        
        message = EmailMessage(
            to_email=email,
            to_name=name,
            subject=f"Complaint Status Update - ID: {complaint_id}",
            html_content=html,
            plain_text_content=text,
        )
        return await self.transport.send_email(message)

    async def send_password_reset(
        self, email: EmailStr, name: str, reset_token: str, reset_url: str
    ) -> bool:
        html = self.renderer.render_html("password_reset", name=name, reset_token=reset_token, reset_url=reset_url)
        text = f"Password Reset Request\nHi {name},\nReset URL: {reset_url}\nToken: {reset_token}"
        
        message = EmailMessage(
            to_email=email,
            to_name=name,
            subject="Reset Your G-Track Password",
            html_content=html,
            plain_text_content=text,
        )
        return await self.transport.send_email(message)

    async def send_custom_email(
        self, to_email: EmailStr, subject: str, html_content: Optional[str] = None, plain_text_content: Optional[str] = None, to_name: Optional[str] = None
    ) -> bool:
        if html_content and not plain_text_content:
            plain_text_content = html_content  # Fallback
            
        html = self.renderer.render_html("custom_email", custom_html_content=html_content)
        
        message = EmailMessage(
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            html_content=html,
            plain_text_content=plain_text_content,
        )
        return await self.transport.send_email(message)


# FastAPI Dependency
def get_notification_service() -> INotificationService:
    """Dependency injector for FastAPI routers."""
    from services.email_service import get_email_transport
    from services.template_engine import get_template_engine
    
    transport = get_email_transport()
    renderer = get_template_engine()
    return NotificationService(transport, renderer)
