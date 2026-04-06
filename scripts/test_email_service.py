"""
Email Service Testing Guide for G-Track Backend

This script provides various testing methods for the email service.
Run from project root directory.
"""

import asyncio
import os
import sys
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load environment variables
load_dotenv()

from services.email_service import EmailService, EmailMessage, EmailConfig
from services.email_helper import EmailHelper

print("=" * 80)
print("📧 G-TRACK EMAIL SERVICE TEST SUITE")
print("=" * 80)


# ============================================================================
# TEST 1: Check Configuration
# ============================================================================

async def test_configuration():
    """Test 1: Verify SMTP configuration is loaded correctly"""
    print("\n[TEST 1] Configuration Check")
    print("-" * 80)
    
    try:
        config = EmailConfig.from_env()
        
        print(f"✓ Configuration loaded successfully")
        print(f"  - SMTP Server: {config.smtp_server}")
        print(f"  - SMTP Port: {config.smtp_port}")
        print(f"  - Use TLS: {config.use_tls}")
        print(f"  - Sender Name: {config.sender_name}")
        
        if config.sender_email:
            print(f"  - Sender Email: {config.sender_email}")
        else:
            print(f"  - Sender Email: ⚠️ NOT SET (emails disabled)")
        
        if config.sender_password:
            print(f"  - Sender Password: {'*' * len(config.sender_password)}")
        else:
            print(f"  - Sender Password: ⚠️ NOT SET (emails disabled)")
        
        return True
    except Exception as e:
        print(f"✗ Configuration Error: {str(e)}")
        return False


# ============================================================================
# TEST 2: Check Email Service Instance
# ============================================================================

async def test_email_service_instance():
    """Test 2: Verify email service can be instantiated"""
    print("\n[TEST 2] Email Service Instance Check")
    print("-" * 80)
    
    try:
        service = EmailService()
        
        if service.is_configured():
            print(f"✓ Email service is CONFIGURED and ready to send emails")
            return True
        else:
            print(f"⚠️ Email service is NOT CONFIGURED")
            print(f"   Set SENDER_EMAIL and SENDER_PASSWORD in .env to enable")
            return None  # Not a failure, just not configured
    except Exception as e:
        print(f"✗ Service Error: {str(e)}")
        return False


# ============================================================================
# TEST 3: SMTP Connection Test (Without Sending)
# ============================================================================

async def test_smtp_connection():
    """Test 3: Attempt SMTP connection without sending email"""
    print("\n[TEST 3] SMTP Connection Test")
    print("-" * 80)
    
    service = EmailService()
    
    if not service.is_configured():
        print("⚠️ Email service not configured - skipping connection test")
        return None
    
    try:
        config = service.config
        print(f"Attempting to connect to {config.smtp_server}:{config.smtp_port}...")
        
        import aiosmtplib
        
        async with aiosmtplib.SMTP(hostname=config.smtp_server, port=config.smtp_port) as smtp:
            print(f"✓ Successfully connected to SMTP server")
            
            if config.use_tls:
                await smtp.starttls()
                print(f"✓ TLS connection established")
            
            # Try login without actually sending
            try:
                await smtp.login(config.sender_email, config.sender_password)
                print(f"✓ Authentication successful")
                await smtp.quit()
                return True
            except Exception as e:
                await smtp.quit()
                print(f"✗ Authentication failed: {str(e)}")
                print(f"  Check your SENDER_EMAIL and SENDER_PASSWORD")
                return False
    
    except Exception as e:
        print(f"✗ Connection Error: {str(e)}")
        print(f"  - Check SMTP server address and port")
        print(f"  - Check internet connection")
        print(f"  - Check firewall/ISP blocking SMTP")
        return False


# ============================================================================
# TEST 4: Send Test Email
# ============================================================================

async def test_send_email():
    """Test 4: Actually send a test email"""
    print("\n[TEST 4] Send Test Email")
    print("-" * 80)
    
    service = EmailService()
    
    if not service.is_configured():
        print("⚠️ Email service not configured - skipping send test")
        return None
    
    # Use your own email for testing
    test_email = os.getenv("SENDER_EMAIL")
    
    if not test_email:
        print("⚠️ SENDER_EMAIL not set - cannot test")
        return None
    
    print(f"Sending test email to: {test_email}")
    
    try:
        message = EmailMessage(
            to_email=test_email,
            to_name="Test User",
            subject="G-Track Email Service Test ✓",
            plain_text_content="If you see this, the email service is working correctly!",
            html_content="""
            <html>
                <body style="font-family: Arial; padding: 20px;">
                    <h1 style="color: #4CAF50;">✓ Email Service Working!</h1>
                    <p>If you received this email, your G-Track email configuration is complete and working correctly.</p>
                    <p><strong>Test Details:</strong></p>
                    <ul>
                        <li>SMTP Connection: ✓ Success</li>
                        <li>Authentication: ✓ Success</li>
                        <li>Email Delivery: ✓ Success</li>
                    </ul>
                    <p style="color: #999; margin-top: 30px;">
                        Sent from G-Track Backend
                    </p>
                </body>
            </html>
            """
        )
        
        result = await service.send_email(message)
        
        if result:
            print(f"✓ Email sent successfully!")
            print(f"  Check your inbox for the test email")
            return True
        else:
            print(f"✗ Email failed to send - check logs")
            return False
    
    except Exception as e:
        print(f"✗ Error: {str(e)}")
        return False


# ============================================================================
# TEST 5: Welcome Email Template
# ============================================================================

async def test_welcome_email():
    """Test 5: Send welcome email template"""
    print("\n[TEST 5] Welcome Email Template Test")
    print("-" * 80)
    
    service = EmailService()
    
    if not service.is_configured():
        print("⚠️ Email service not configured - skipping")
        return None
    
    test_email = os.getenv("SENDER_EMAIL")
    if not test_email:
        return None
    
    print(f"Sending welcome email template to: {test_email}")
    
    try:
        result = await service.send_welcome_email(
            email=test_email,
            name="Test User",
            password="TempPassword123"
        )
        
        if result:
            print(f"✓ Welcome email sent successfully")
            return True
        else:
            print(f"✗ Failed to send welcome email")
            return False
    
    except Exception as e:
        print(f"✗ Error: {str(e)}")
        return False


# ============================================================================
# TEST 6: Complaint Confirmation Template
# ============================================================================

async def test_complaint_email():
    """Test 6: Send complaint confirmation template"""
    print("\n[TEST 6] Complaint Confirmation Template Test")
    print("-" * 80)
    
    service = EmailService()
    
    if not service.is_configured():
        print("⚠️ Email service not configured - skipping")
        return None
    
    test_email = os.getenv("SENDER_EMAIL")
    if not test_email:
        return None
    
    print(f"Sending complaint email template to: {test_email}")
    
    try:
        result = await service.send_complaint_confirmation(
            email=test_email,
            name="Test User",
            complaint_id="COMP-20240406-0001",
            status="submitted"
        )
        
        if result:
            print(f"✓ Complaint email sent successfully")
            return True
        else:
            print(f"✗ Failed to send complaint email")
            return False
    
    except Exception as e:
        print(f"✗ Error: {str(e)}")
        return False


# ============================================================================
# TEST 7: Refill Reminder Template
# ============================================================================

async def test_refill_email():
    """Test 7: Send refill reminder template"""
    print("\n[TEST 7] Refill Reminder Template Test")
    print("-" * 80)
    
    service = EmailService()
    
    if not service.is_configured():
        print("⚠️ Email service not configured - skipping")
        return None
    
    test_email = os.getenv("SENDER_EMAIL")
    if not test_email:
        return None
    
    print(f"Sending refill reminder to: {test_email}")
    
    try:
        result = await service.send_refill_reminder(
            email=test_email,
            name="Test User",
            gas_level=15.5,
            threshold=20.0
        )
        
        if result:
            print(f"✓ Refill reminder sent successfully")
            return True
        else:
            print(f"✗ Failed to send refill reminder")
            return False
    
    except Exception as e:
        print(f"✗ Error: {str(e)}")
        return False


# ============================================================================
# TEST 8: Helper Functions
# ============================================================================

async def test_helper_functions():
    """Test 8: Test EmailHelper convenience functions"""
    print("\n[TEST 8] EmailHelper Functions Test")
    print("-" * 80)
    
    # Check if enabled
    enabled = EmailHelper.is_email_enabled()
    print(f"Email service enabled: {enabled}")
    
    if not enabled:
        print("⚠️ Email service not configured - skipping helper tests")
        return None
    
    test_email = os.getenv("SENDER_EMAIL")
    if not test_email:
        return None
    
    try:
        # Test send_custom_email
        result = await EmailHelper.send_custom_email(
            to_email=test_email,
            subject="Custom Helper Email Test",
            html_content="<h2>Helper Function Test</h2><p>This email was sent using EmailHelper.send_custom_email()</p>",
            plain_text_content="Helper Function Test"
        )
        
        if result:
            print(f"✓ EmailHelper.send_custom_email() works")
            return True
        else:
            print(f"✗ EmailHelper.send_custom_email() failed")
            return False
    
    except Exception as e:
        print(f"✗ Error: {str(e)}")
        return False


# ============================================================================
# MAIN TEST RUNNER
# ============================================================================

async def run_all_tests():
    """Run all tests"""
    results = {}
    
    # Test 1: Configuration
    results["Configuration Check"] = await test_configuration()
    
    # Test 2: Service Instance
    results["Service Instance"] = await test_email_service_instance()
    
    # Only continue if service is configured
    if results["Service Instance"] is False:
        print("\n" + "=" * 80)
        print("⚠️ STOPPING - Service not configured properly")
        print("=" * 80)
        return results
    
    # Test 3: SMTP Connection
    results["SMTP Connection"] = await test_smtp_connection()
    
    if results["SMTP Connection"] is False:
        print("\n" + "=" * 80)
        print("⚠️ STOPPING - Cannot connect to SMTP server")
        print("=" * 80)
        return results
    
    # Test 4: Send Email
    if results["SMTP Connection"] is True:
        results["Send Test Email"] = await test_send_email()
    
    # Test 5: Templates
    if results["Send Test Email"] is True:
        results["Welcome Email"] = await test_welcome_email()
        results["Complaint Email"] = await test_complaint_email()
        results["Refill Reminder"] = await test_refill_email()
    
    # Test 6: Helper Functions
    results["Helper Functions"] = await test_helper_functions()
    
    return results


# ============================================================================
# RESULTS SUMMARY
# ============================================================================

async def print_summary(results):
    """Print test results summary"""
    print("\n" + "=" * 80)
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 80)
    
    passed = 0
    failed = 0
    skipped = 0
    
    for test_name, result in results.items():
        if result is True:
            print(f"✓ {test_name}: PASSED")
            passed += 1
        elif result is False:
            print(f"✗ {test_name}: FAILED")
            failed += 1
        elif result is None:
            print(f"⊘ {test_name}: SKIPPED")
            skipped += 1
    
    print("-" * 80)
    print(f"Total: {passed} passed, {failed} failed, {skipped} skipped")
    print("=" * 80)
    
    if failed == 0 and passed > 0:
        print("\n✅ All tests passed! Email service is working correctly.\n")
    elif failed > 0:
        print("\n❌ Some tests failed. Check configuration and try again.\n")
    else:
        print("\n⚠️ Email service not configured. Set up SMTP credentials to proceed.\n")


# ============================================================================
# ENTRY POINT
# ============================================================================

async def main():
    """Main entry point"""
    try:
        results = await run_all_tests()
        await print_summary(results)
    except KeyboardInterrupt:
        print("\n\n⚠️ Tests interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Run tests
    asyncio.run(main())
