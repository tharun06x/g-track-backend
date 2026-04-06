"""
Email utilities and helpers for G-Track Backend

Provides convenience functions for common email operations
and integration examples for routers.
"""

from services.email_service import get_email_service, EmailMessage
from pydantic import EmailStr
import logging

logger = logging.getLogger(__name__)


class EmailHelper:
    """Helper class for common email operations"""

    @staticmethod
    async def send_welcome_email(email: EmailStr, name: str, password: str) -> bool:
        """
        Send welcome email to new user
        
        Args:
            email: User email
            name: User name
            password: Temporary password
            
        Returns:
            True if sent successfully
            
        Example:
            await EmailHelper.send_welcome_email(
                email="user@example.com",
                name="John Doe",
                password="temp_password"
            )
        """
        email_service = get_email_service()
        return await email_service.send_welcome_email(email, name, password)

    @staticmethod
    async def send_complaint_confirmation(
        email: EmailStr,
        name: str,
        complaint_id: str,
        status: str = "submitted"
    ) -> bool:
        """
        Send complaint submission confirmation
        
        Args:
            email: User email
            name: User name
            complaint_id: Complaint reference ID
            status: Current complaint status
            
        Returns:
            True if sent successfully
            
        Example:
            await EmailHelper.send_complaint_confirmation(
                email="user@example.com",
                name="John Doe",
                complaint_id="COMP-2024-001",
                status="submitted"
            )
        """
        email_service = get_email_service()
        return await email_service.send_complaint_confirmation(email, name, complaint_id, status)

    @staticmethod
    async def send_refill_reminder(
        email: EmailStr,
        name: str,
        gas_level: float,
        threshold: float
    ) -> bool:
        """
        Send gas refill reminder email
        
        Args:
            email: User email
            name: User name
            gas_level: Current gas percentage (0-100)
            threshold: Threshold percentage (0-100)
            
        Returns:
            True if sent successfully
            
        Example:
            await EmailHelper.send_refill_reminder(
                email="user@example.com",
                name="John Doe",
                gas_level=15.5,
                threshold=20.0
            )
        """
        email_service = get_email_service()
        return await email_service.send_refill_reminder(email, name, gas_level, threshold)

    @staticmethod
    async def send_password_reset(
        email: EmailStr,
        name: str,
        reset_token: str,
        reset_url: str
    ) -> bool:
        """
        Send password reset email
        
        Args:
            email: User email
            name: User name
            reset_token: Password reset token
            reset_url: Full URL for password reset (with token)
            
        Returns:
            True if sent successfully
            
        Example:
            await EmailHelper.send_password_reset(
                email="user@example.com",
                name="John Doe",
                reset_token="abc123def456",
                reset_url="https://app.com/reset?token=abc123def456"
            )
        """
        email_service = get_email_service()
        return await email_service.send_password_reset_email(email, name, reset_token, reset_url)

    @staticmethod
    async def send_custom_email(
        to_email: EmailStr,
        subject: str,
        html_content: str = None,
        plain_text_content: str = None,
        to_name: str = None,
        cc: list[EmailStr] = None,
        bcc: list[EmailStr] = None
    ) -> bool:
        """
        Send custom email with provided content
        
        Args:
            to_email: Recipient email
            subject: Email subject
            html_content: HTML content (optional)
            plain_text_content: Plain text content (optional)
            to_name: Recipient name (optional)
            cc: CC recipients list (optional)
            bcc: BCC recipients list (optional)
            
        Returns:
            True if sent successfully
            
        Example:
            await EmailHelper.send_custom_email(
                to_email="user@example.com",
                subject="Custom Notification",
                html_content="<p>Hello User</p>",
                plain_text_content="Hello User"
            )
        """
        email_service = get_email_service()
        message = EmailMessage(
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            html_content=html_content,
            plain_text_content=plain_text_content,
            cc=cc,
            bcc=bcc
        )
        return await email_service.send_email(message)

    @staticmethod
    def is_email_enabled() -> bool:
        """
        Check if email service is properly configured
        
        Returns:
            True if email sending is enabled
            
        Example:
            if EmailHelper.is_email_enabled():
                await EmailHelper.send_welcome_email(...)
        """
        email_service = get_email_service()
        return email_service.is_configured()


# For use in dependency injection
async def email_service_dependency():
    """FastAPI dependency for email service"""
    return get_email_service()
