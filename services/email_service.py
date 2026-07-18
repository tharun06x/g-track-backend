"""
Email Service for G-Track Backend

Provides the SMTP transport layer implementation of IEmailTransport.
This class ONLY handles network delivery of EmailMessage objects.
It does not contain any business logic or HTML templates.
"""

import os
from typing import Optional
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pydantic import BaseModel, EmailStr
from dotenv import load_dotenv
import logging

from services.email_interfaces import IEmailTransport, EmailMessage

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


class EmailConfig(BaseModel):
    """Email configuration from environment variables"""
    smtp_server: str
    smtp_port: int
    sender_email: EmailStr
    sender_name: str
    sender_password: str
    use_tls: bool = True

    @classmethod
    def from_env(cls):
        """Load configuration from environment variables"""
        return cls(
            smtp_server=os.getenv("SMTP_SERVER", "smtp.gmail.com"),
            smtp_port=int(os.getenv("SMTP_PORT", "587")),
            sender_email=os.getenv("SENDER_EMAIL", ""),
            sender_name=os.getenv("SENDER_NAME", "G-Track Admin"),
            sender_password=os.getenv("SENDER_PASSWORD", ""),
            use_tls=os.getenv("SMTP_USE_TLS", "True").lower() == "true",
        )


class SmtpEmailService(IEmailTransport):
    """Service for sending emails via SMTP (implements IEmailTransport)"""

    def __init__(self, config: Optional[EmailConfig] = None):
        """
        Initialize email service
        
        Args:
            config: EmailConfig instance. If None, loads from environment.
        """
        self.config = config or EmailConfig.from_env()
        self._validate_config()

    def _validate_config(self):
        """Validate SMTP configuration"""
        if not self.config.sender_email:
            logger.warning("SENDER_EMAIL not configured - email service disabled")
        if not self.config.sender_password:
            logger.warning("SENDER_PASSWORD not configured - email service disabled")

    def is_configured(self) -> bool:
        """Check if email service is properly configured"""
        return bool(self.config.sender_email and self.config.sender_password)

    async def send_email(self, message: EmailMessage) -> bool:
        """
        Send email via SMTP
        
        Args:
            message: EmailMessage object containing email details
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.is_configured():
            logger.error("Email service not configured - cannot send email")
            return False

        try:
            # Create MIME message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = message.subject
            msg["From"] = f"{self.config.sender_name} <{self.config.sender_email}>"
            msg["To"] = f"{message.to_name} <{message.to_email}>" if message.to_name else message.to_email

            if message.cc:
                msg["Cc"] = ", ".join(message.cc)
            if message.bcc:
                msg["Bcc"] = ", ".join(message.bcc)

            # Add plain text part (if provided)
            if message.plain_text_content:
                msg.attach(MIMEText(message.plain_text_content, "plain", "utf-8"))

            # Add HTML part (if provided)
            if message.html_content:
                msg.attach(MIMEText(message.html_content, "html", "utf-8"))

            # Prepare recipient list
            recipients = [message.to_email]
            if message.cc:
                recipients.extend(message.cc)
            if message.bcc:
                recipients.extend(message.bcc)

            # Port 465 expects implicit TLS; port 587 expects STARTTLS upgrade.
            implicit_tls = self.config.use_tls and self.config.smtp_port == 465
            async with aiosmtplib.SMTP(
                hostname=self.config.smtp_server,
                port=self.config.smtp_port,
                use_tls=implicit_tls,
                start_tls=False,
            ) as smtp:
                if self.config.use_tls and not implicit_tls:
                    await smtp.starttls()
                await smtp.login(self.config.sender_email, self.config.sender_password)
                await smtp.sendmail(self.config.sender_email, recipients, msg.as_string())

            logger.info(f"Email sent successfully to {message.to_email}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email to {message.to_email}: {str(e)}")
            return False


# Global email service instance
_email_service: Optional[SmtpEmailService] = None

def get_email_transport() -> IEmailTransport:
    """Get or create email transport instance"""
    global _email_service
    if _email_service is None:
        _email_service = SmtpEmailService()
    return _email_service
