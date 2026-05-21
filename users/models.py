from datetime import timedelta
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone


class CustomUserManager(BaseUserManager):
    """
    Technical class for creating users.
    Login is done only by email
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


class Group(models.Model):
    """
    Academic groups
    """

    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name


class Department(models.Model):
    """
    University departments/faculties
    """

    name = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.name


class Course(models.Model):
    """
    Subjects/Courses taught at the university
    """

    name = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.name


class CustomUser(AbstractUser):
    """
    Main user table (Students, Teachers, Admins)
    """

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        STUDENT = "STUDENT", "Student"
        TEACHER = "TEACHER", "Teacher"

    username = None

    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=20, null=True, blank=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.STUDENT)
    record_book_number = models.CharField(
        max_length=50, unique=True, null=True, blank=True
    )
    is_password_changed = models.BooleanField(default=False)

    group = models.ForeignKey(
        Group,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="students",
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="teachers",
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    objects = CustomUserManager()

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.role})"


class OTPCode(models.Model):
    """
    Table for saving one-time codes (generation at first login or reset password).
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
