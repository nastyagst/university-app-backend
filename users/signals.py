from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import CustomUser, StudentProfile, TeacherProfile


@receiver(post_save, sender=CustomUser)
def create_user_profile(sender, instance, created, **kwargs):
    """Автоматично створює відповідний профіль при створенні користувача"""
    if created:
        if instance.role == CustomUser.Role.STUDENT:
            StudentProfile.objects.create(user=instance)
        elif instance.role == CustomUser.Role.TEACHER:
            TeacherProfile.objects.create(user=instance)


@receiver(post_save, sender=CustomUser)
def save_user_profile(sender, instance, **kwargs):
    """Автоматично зберігає профіль, якщо основний користувач оновлюється"""
    if instance.role == CustomUser.Role.STUDENT:
        if hasattr(instance, "student_profile"):
            instance.student_profile.save()
    elif instance.role == CustomUser.Role.TEACHER:
        if hasattr(instance, "teacher_profile"):
            instance.teacher_profile.save()
