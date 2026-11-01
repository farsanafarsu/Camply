"""Django email backend that sends through Resend."""

import resend
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend


class ResendEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        resend.api_key = settings.RESEND_API_KEY
        sent = 0
        for message in email_messages:
            params = {
                "from": message.from_email or settings.DEFAULT_FROM_EMAIL,
                "to": list(message.to),
                "subject": message.subject,
                "text": message.body,
            }
            if message.cc:
                params["cc"] = list(message.cc)
            if message.bcc:
                params["bcc"] = list(message.bcc)
            for content, mimetype in getattr(message, "alternatives", []):
                if mimetype == "text/html":
                    params["html"] = content
            try:
                resend.Emails.send(params)
                sent += 1
            except Exception:
                if not self.fail_silently:
                    raise
        return sent
