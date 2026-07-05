from datetime import timedelta
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone


class CustomUserManager(BaseUserManager):
    """
    Technical class for creating users.
    Login is done only by email.
    """

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, username=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_password_changed", True)
        extra_fields.setdefault("role", "STUDENT")

        return self.create_user(email, password, **extra_fields)


class Group(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name


class Department(models.Model):
    name = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.name


class Course(models.Model):
    name = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.name


class CustomUser(AbstractUser):
    class Role(models.TextChoices):
        STUDENT = "STUDENT", "Student"
        ADMIN = "ADMIN", "Admin"
        TEACHER = "TEACHER", "Teacher"

    class LanguageChoices(models.TextChoices):
        ENGLISH = "en", "English"
        ITALIAN = "it", "Italiano"
        GERMAN = "de", "Deutsch"
        SPANISH = "es", "Espanol"
        UKRAINIAN = "uk", "Ukrainian"

    username = None

    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=20, null=True, blank=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.STUDENT)
    language = models.CharField(
        max_length=2,
        choices=LanguageChoices.choices,
        default=LanguageChoices.ENGLISH,
    )
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


class Semester(models.Model):
    number = models.PositiveSmallIntegerField(help_text="Semester number (1 or 2)")
    year = models.CharField(max_length=9)
    date_start = models.DateField(null=True, blank=True)
    date_end = models.DateField(null=True, blank=True)

    class Meta:
        unique_together = ("year", "number")
        verbose_name = "Semester"
        verbose_name_plural = "Semesters"

    def __str__(self):
        return f"{self.year} — Semester {self.number}"


class Room(models.Model):
    building = models.CharField(max_length=50)
    number = models.CharField(max_length=20, help_text="Room number")
    type = models.CharField(max_length=50, blank=True)

    class Meta:
        unique_together = ("building", "number")
        verbose_name = "Room"
        verbose_name_plural = "Rooms"

    def __str__(self):
        return f"Bldg. {self.building}, room {self.number}"


class TimeSlot(models.Model):
    number = models.PositiveSmallIntegerField(unique=True)
    time_start = models.TimeField()
    time_end = models.TimeField()

    class Meta:
        ordering = ["number"]
        verbose_name = "Time Slot"
        verbose_name_plural = "Time Slots"

    def __str__(self):
        return f"Slot {self.number} ({self.time_start.strftime('%H:%M')} - {self.time_end.strftime('%H:%M')})"


class CourseOffering(models.Model):
    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="offerings"
    )
    teacher = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        limit_choices_to={"role": "TEACHER"},
        related_name="course_offerings",
    )
    semester = models.ForeignKey(
        Semester, on_delete=models.CASCADE, related_name="course_offerings"
    )
    group = models.ForeignKey(
        Group, on_delete=models.CASCADE, related_name="course_offerings"
    )
    description = models.TextField(blank=True, null=True)
    telegram_group_url = models.URLField(max_length=255, blank=True, null=True)

    class Meta:
        unique_together = ("course", "teacher", "semester", "group")
        verbose_name = "Course Offering"
        verbose_name_plural = "Course Offerings"

    def __str__(self):
        return f"{self.course.name} | {self.teacher.last_name} | {self.group.name}"


class ScheduleEntry(models.Model):
    course_offering = models.ForeignKey(
        CourseOffering, on_delete=models.CASCADE, related_name="schedule_entries"
    )
    room = models.ForeignKey(
        Room, on_delete=models.CASCADE, related_name="schedule_entries"
    )
    time_slot = models.ForeignKey(
        TimeSlot, on_delete=models.CASCADE, related_name="schedule_entries"
    )
    day_of_week = models.CharField(max_length=20, verbose_name="Day of week")

    class Meta:
        verbose_name = "Schedule Entry"
        verbose_name_plural = "Schedule Entries"

    def __str__(self):
        return f"{self.day_of_week} | {self.time_slot} | {self.course_offering.group.name} | {self.room}"


class Lesson(models.Model):
    course_offering = models.ForeignKey(
        CourseOffering, on_delete=models.CASCADE, related_name="lessons"
    )
    date = models.DateField()
    time_slot = models.ForeignKey(
        TimeSlot, on_delete=models.SET_NULL, null=True, related_name="lessons"
    )
    room = models.ForeignKey(Room, on_delete=models.SET_NULL, null=True, blank=True)
    topic = models.CharField(
        max_length=255, blank=True, null=True, help_text="Lesson topic"
    )
    is_cancelled = models.BooleanField(default=False)

    class Meta:
        ordering = ["-date", "time_slot"]
        verbose_name = "Lesson"
        verbose_name_plural = "Lessons"

    def __str__(self):
        return f"{self.course_offering.course.name} | {self.date}"


class Attendance(models.Model):
    class Status(models.TextChoices):
        PRESENT = "PRESENT", "Present"
        ABSENT = "ABSENT", "Absent"
        LATE = "LATE", "Late"

    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.CASCADE,
        related_name="attendances",
        null=True,
        blank=True,
    )
    student = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        limit_choices_to={"role": "STUDENT"},
        related_name="attendances",
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PRESENT
    )

    class Meta:
        unique_together = ("lesson", "student")
        verbose_name = "Attendance"
        verbose_name_plural = "Attendance Records"

    def __str__(self):
        return f"{self.student.last_name} - {self.lesson} ({self.status})"


class Grade(models.Model):
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="grades")
    student = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="grades",
    )
    score = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    comment = models.TextField(blank=True, null=True)

    @property
    def ects_letter(self):
        if 90 <= self.score <= 100:
            return "A"
        elif 82 <= self.score <= 89:
            return "B"
        elif 74 <= self.score <= 81:
            return "C"
        elif 64 <= self.score <= 73:
            return "D"
        elif 60 <= self.score <= 63:
            return "E"
        elif 35 <= self.score <= 59:
            return "FX"
        else:
            return "F"

    class Meta:
        unique_together = ("lesson", "student")
        verbose_name = "Grade"
        verbose_name_plural = "Grades"

    def __str__(self):
        return f"{self.student.last_name} - {self.lesson}: {self.score} ({self.ects_letter})"


class ABTest(models.Model):
    user = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="ab_tests"
    )
    test_name = models.CharField(max_length=100)
    group = models.CharField(max_length=50)

    class Meta:
        unique_together = ("user", "test_name")
        verbose_name = "A/B Test Record"
        verbose_name_plural = "A/B Test Records"

    def __str__(self):
        return f"{self.user.email} | {self.test_name}: Group {self.group}"


class StudentProfile(models.Model):
    user = models.OneToOneField(
        CustomUser, on_delete=models.CASCADE, related_name="student_profile"
    )
    enrollment_year = models.PositiveIntegerField(null=True, blank=True)
    faculty = models.CharField(max_length=255, null=True, blank=True)
    degree_level = models.CharField(
        max_length=50, null=True, blank=True, help_text="Bachelor/Master"
    )

    def __str__(self):
        return f"Student profile: {self.user.last_name}"


class TeacherProfile(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE)
    position = models.CharField(max_length=100, null=True, blank=True)
    office_room = models.CharField(max_length=50, null=True, blank=True)
    telegram_url = models.URLField(max_length=255, null=True, blank=True)

    def __str__(self):
        return f"Teacher profile: {self.user.last_name}"
