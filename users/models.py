from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone
from datetime import timedelta


class CustomUserManager(BaseUserManager):
    """
    Technical class for creating users.
    Login is done ONLY by Email (no username and no phone).
    """

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email обов'язковий")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, username=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_password_changed", True)
        extra_fields.setdefault("role", "ADMIN")

        return self.create_user(email, password, **extra_fields)


class CustomUser(AbstractUser):
    """
    Main user table (Students, Teachers, Admins).
    """

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        STUDENT = "STUDENT", "Student"
        TEACHER = "TEACHER", "Teacher"

    username = None

    email = models.EmailField(unique=True)
    # The phone number is just an information field in the profile.
    phone_number = models.CharField(max_length=20, null=True, blank=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.STUDENT)
    record_book_number = models.CharField(
        max_length=50, unique=True, null=True, blank=True
    )
    # First login flag. If False -> show the "Set permanent password" form
    is_password_changed = models.BooleanField(default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    objects = CustomUserManager()

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class OTPCode(models.Model):
    """
    Table for saving one-time codes (generation at first login or Reset Password).
    Limitations: code is valid for 3 minutes, max 5 entry attempts.
    """

    user = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="otp_codes"
    )
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    attempts = models.IntegerField(default=0)
    purpose = models.CharField(
        max_length=20, choices=[("ACTIVATION", "Activation"), ("RESET", "Reset")]
    )
    is_used = models.BooleanField(default=False)

    def is_expired(self):
        return timezone.now() > self.created_at + timedelta(minutes=3)

    def __str__(self):
        return f"Code for {self.user.email} - {self.purpose}"
