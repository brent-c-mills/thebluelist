import logging
from mailtrap import MailtrapClient
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)

class EmailService:
    def __init__(self):
        self.client = MailtrapClient(token=settings.MAILTRAP_API_TOKEN)
        self.sender = {
            "email": settings.MAILTRAP_SENDER_EMAIL,
            "name": "MyBlueList"
        }

    def send_email(self, to_email, subject, html_content, text_content=None):
        """
        Send an email using Mailtrap API
        """
        try:
            if text_content is None:
                text_content = strip_tags(html_content)

            response = self.client.send(
                category='Transactional',  # or 'Marketing' if needed
                from_=self.sender,
                to=[{"email": to_email}],
                subject=subject,
                html=html_content,
                text=text_content
            )
            
            logger.info(f"Email sent successfully to {to_email}. Message ID: {response['message_ids']}")
            return True, response['message_ids']

        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}", exc_info=True)
            return False, None

    def send_verification_email(self, user, verification_url):
        """
        Send account verification email
        """
        subject = "Verify your MyBlueList account"
        
        context = {
            'user': user,
            'verification_url': verification_url
        }
        
        html_content = render_to_string('users/emails/verification_email.html', context)
        text_content = render_to_string('users/emails/verification_email.txt', context)
        
        return self.send_email(user.email, subject, html_content, text_content)

    def send_password_reset_email(self, user, reset_url):
        """
        Send password reset email
        """
        subject = "Reset your MyBlueList password"
        
        context = {
            'user': user,
            'reset_url': reset_url
        }
        
        html_content = render_to_string('users/emails/password_reset_email.html', context)
        text_content = render_to_string('users/emails/password_reset_email.txt', context)
        
        return self.send_email(user.email, subject, html_content, text_content)