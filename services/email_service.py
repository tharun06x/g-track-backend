"""
Email Service for G-Track Backend

Handles sending emails via SMTP with templates for various notifications.
Supports both HTML and plain text emails.
"""

import os
from typing import Optional
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pydantic import BaseModel, EmailStr
from dotenv import load_dotenv
import logging

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


class EmailMessage(BaseModel):
    """Email message structure"""
    to_email: EmailStr
    to_name: Optional[str] = None
    subject: str
    html_content: Optional[str] = None
    plain_text_content: Optional[str] = None
    cc: Optional[list[EmailStr]] = None
    bcc: Optional[list[EmailStr]] = None

    def __post_init__(self):
        """Ensure at least one content type is provided"""
        if not self.html_content and not self.plain_text_content:
            raise ValueError("Either html_content or plain_text_content must be provided")


class EmailService:
    """Service for sending emails via SMTP"""

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

    async def send_welcome_email(self, email: str, name: str, password: str) -> bool:
        """Send welcome email to new user"""
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                    <h1 style="color: #333; margin-bottom: 20px;">Welcome to G-Track! 🎉</h1>
                    
                    <p style="color: #666; font-size: 16px; line-height: 1.5;">
                        Hello <strong>{name}</strong>,
                    </p>
                    
                    <p style="color: #666; font-size: 16px; line-height: 1.5;">
                        Thank you for registering with G-Track. Your account has been successfully created!
                    </p>
                    
                    <div style="background-color: #f0f0f0; padding: 15px; border-left: 4px solid #4CAF50; margin: 20px 0;">
                        <p style="margin: 0; color: #333;">
                            <strong>Email:</strong> {email}<br>
                            <strong>Temporary Password:</strong> {password}
                        </p>
                        <p style="margin: 10px 0 0 0; color: #e74c3c; font-size: 14px;">
                            ⚠️ Please change your password on first login.
                        </p>
                    </div>
                    
                    <h3 style="color: #333; margin-top: 25px; margin-bottom: 15px;">Getting Started:</h3>
                    <ol style="color: #666; font-size: 16px; line-height: 1.8;">
                        <li>Log in to your account with your email and temporary password</li>
                        <li>Update your profile information</li>
                        <li>Change your password to something secure</li>
                        <li>Start tracking your gas usage!</li>
                    </ol>
                    
                    <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee;">
                        <p style="color: #999; font-size: 14px; margin: 0;">
                            If you have any questions, please contact our support team.
                        </p>
                        <p style="color: #999; font-size: 12px; margin: 10px 0 0 0;">
                            © 2024 G-Track. All rights reserved.
                        </p>
                    </div>
                </div>
            </body>
        </html>
        """
        
        plain_text = f"""Welcome to G-Track!

Hello {name},

Thank you for registering with G-Track. Your account has been successfully created!

Email: {email}
Temporary Password: {password}

⚠️ Please change your password on first login.

Getting Started:
1. Log in to your account with your email and temporary password
2. Update your profile information
3. Change your password to something secure
4. Start tracking your gas usage!

If you have any questions, please contact our support team.

© 2024 G-Track. All rights reserved.
"""
        
        message = EmailMessage(
            to_email=email,
            to_name=name,
            subject="Welcome to G-Track - Your Account is Ready! 🎉",
            html_content=html_content,
            plain_text_content=plain_text,
        )
        
        return await self.send_email(message)

    async def send_complaint_confirmation(self, email: str, name: str, complaint_id: str, status: str) -> bool:
        """Send complaint submission confirmation email"""
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                    <h1 style="color: #333; margin-bottom: 20px;">Complaint Received ✓</h1>
                    
                    <p style="color: #666; font-size: 16px; line-height: 1.5;">
                        Hi <strong>{name}</strong>,
                    </p>
                    
                    <p style="color: #666; font-size: 16px; line-height: 1.5;">
                        We have successfully received your complaint. Our team will review it and get back to you soon.
                    </p>
                    
                    <div style="background-color: #e8f5e9; padding: 15px; border-left: 4px solid #4CAF50; margin: 20px 0;">
                        <p style="margin: 0; color: #333;">
                            <strong>Complaint ID:</strong> {complaint_id}<br>
                            <strong>Status:</strong> <span style="color: #4CAF50; font-weight: bold;">{status.upper()}</span>
                        </p>
                    </div>
                    
                    <p style="color: #666; font-size: 16px; line-height: 1.5;">
                        You can track the status of your complaint using the ID above in your account dashboard.
                    </p>
                    
                    <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee;">
                        <p style="color: #999; font-size: 14px; margin: 0;">
                            Thank you for choosing G-Track!
                        </p>
                    </div>
                </div>
            </body>
        </html>
        """
        
        plain_text = f"""Complaint Received ✓

Hi {name},

We have successfully received your complaint. Our team will review it and get back to you soon.

Complaint ID: {complaint_id}
Status: {status.upper()}

You can track the status of your complaint using the ID above in your account dashboard.

Thank you for choosing G-Track!
"""
        
        message = EmailMessage(
            to_email=email,
            to_name=name,
            subject=f"Complaint Confirmation - ID: {complaint_id}",
            html_content=html_content,
            plain_text_content=plain_text,
        )
        
        return await self.send_email(message)

    async def send_refill_reminder(self, email: str, name: str, gas_level: float, threshold: float) -> bool:
        """Send gas refill reminder email"""
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                    <h1 style="color: #ff9800; margin-bottom: 20px;">Gas Level Low ⚠️</h1>
                    
                    <p style="color: #666; font-size: 16px; line-height: 1.5;">
                        Hi <strong>{name}</strong>,
                    </p>
                    
                    <p style="color: #666; font-size: 16px; line-height: 1.5;">
                        Your gas level is running low and approaching your threshold limit.
                    </p>
                    
                    <div style="background-color: #fff3e0; padding: 15px; border-left: 4px solid #ff9800; margin: 20px 0;">
                        <p style="margin: 0; color: #333;">
                            <strong>Current Gas Level:</strong> {gas_level:.1f}%<br>
                            <strong>Threshold Limit:</strong> {threshold:.1f}%
                        </p>
                    </div>
                    
                    <p style="color: #666; font-size: 16px; line-height: 1.5;">
                        Consider ordering a refill soon to ensure uninterrupted service. You can request a refill through your G-Track dashboard.
                    </p>
                    
                    <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee;">
                        <p style="color: #999; font-size: 14px; margin: 0;">
                            Stay connected with G-Track!
                        </p>
                    </div>
                </div>
            </body>
        </html>
        """
        
        plain_text = f"""Gas Level Low ⚠️

Hi {name},

Your gas level is running low and approaching your threshold limit.

Current Gas Level: {gas_level:.1f}%
Threshold Limit: {threshold:.1f}%

Consider ordering a refill soon to ensure uninterrupted service. You can request a refill through your G-Track dashboard.

Stay connected with G-Track!
"""
        
        message = EmailMessage(
            to_email=email,
            to_name=name,
            subject="Gas Level Reminder - Please Order Refill Soon",
            html_content=html_content,
            plain_text_content=plain_text,
        )
        
        return await self.send_email(message)

    async def send_password_reset_email(self, email: str, name: str, reset_token: str, reset_link: str) -> bool:
        """Send password reset email"""
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                    <h1 style="color: #333; margin-bottom: 20px;">Password Reset Request</h1>
                    
                    <p style="color: #666; font-size: 16px; line-height: 1.5;">
                        Hi <strong>{name}</strong>,
                    </p>
                    
                    <p style="color: #666; font-size: 16px; line-height: 1.5;">
                        We received a request to reset your password. Click the button below to reset it:
                    </p>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{reset_link}" style="background-color: #4CAF50; color: white; padding: 12px 30px; text-decoration: none; border-radius: 4px; font-weight: bold; display: inline-block;">
                            Reset Password
                        </a>
                    </div>
                    
                    <p style="color: #999; font-size: 14px; line-height: 1.5; margin: 20px 0;">
                        <strong>Or copy this token:</strong><br>
                        <code style="background-color: #f5f5f5; padding: 8px; border-radius: 4px; font-family: monospace;">{reset_token}</code>
                    </p>
                    
                    <div style="background-color: #fff3cd; padding: 15px; border-left: 4px solid #ffc107; margin: 20px 0;">
                        <p style="margin: 0; color: #333; font-size: 14px;">
                            This link will expire in 24 hours. If you didn't request this, please ignore this email.
                        </p>
                    </div>
                    
                    <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee;">
                        <p style="color: #999; font-size: 14px; margin: 0;">
                            © 2024 G-Track. All rights reserved.
                        </p>
                    </div>
                </div>
            </body>
        </html>
        """
        
        plain_text = f"""Password Reset Request

Hi {name},

We received a request to reset your password. Click the link below to reset it:

{reset_link}

Or copy this token: {reset_token}

This link will expire in 24 hours. If you didn't request this, please ignore this email.

© 2024 G-Track. All rights reserved.
"""
        
        message = EmailMessage(
            to_email=email,
            to_name=name,
            subject="Reset Your G-Track Password",
            html_content=html_content,
            plain_text_content=plain_text,
        )
        
        return await self.send_email(message)

    async def send_admin_notification(self, email: str, subject: str, content: str) -> bool:
        """Send administrative notification email"""
        message = EmailMessage(
            to_email=email,
            subject=subject,
            html_content=f"""
            <html>
                <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
                    <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px;">
                        {content}
                    </div>
                </body>
            </html>
            """,
            plain_text_content=content,
        )
        
        return await self.send_email(message)


# Global email service instance
_email_service: Optional[EmailService] = None


def get_email_service() -> EmailService:
    """Get or create email service instance"""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service
