import random
from django.core.mail import send_mail
from django.conf import settings
from .models import OTPCode


def generate_and_send_otp(user, purpose="ACTIVATION"):
    """
    Generates a 6-digit code, saves it to the database and sends it
    via the official Django email service.
    """
    code = str(random.randint(100000, 999999))
    OTPCode.objects.filter(user=user, purpose=purpose, is_used=False).update(
        is_used=True
    )
    OTPCode.objects.create(user=user, code=code, purpose=purpose)
    subject = "Your University App Verification Code"
    message = (
        f"Hello, {user.first_name} {user.last_name}!\n\n"
        f"Your 6-digit verification code is: {code}\n"
        f"This code will expire in 3 minutes.\n\n"
        f"If you did not request this code, please ignore this email."
    )
    from_email = settings.DEFAULT_FROM_EMAIL
    recipient_list = [user.email]
    send_mail(
        subject=subject,
        message=message,
        from_email=from_email,
        recipient_list=recipient_list,
        fail_silently=False,
    )
