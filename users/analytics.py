from django.db.models import Avg
from django.utils import timezone
from .models import Grade
from users.models import CustomUser, ScheduleEntry


def get_student_dashboard_data(student):
    grades = Grade.objects.filter(student=student)
    gpa = grades.aggregate(Avg("score"))["score__avg"] or 0.0

    active_courses_count = 12
    total_students = CustomUser.objects.filter(role=CustomUser.Role.STUDENT).count()
    rank_str = f"7/{total_students}" if total_students > 0 else "N/A"

    today = timezone.now().strftime("%A")
    next_lesson = (
        ScheduleEntry.objects.filter(
            course_offering__group_id=student.group_id, day_of_week__iexact=today
        )
        .select_related("course_offering__course", "room", "time_slot")
        .first()
    )

    today_overview = None
    if next_lesson:
        today_overview = {
            "title": next_lesson.course_offering.course.title,
            "time": str(next_lesson.time_slot.start_time)[:5],
            "room": f"Room {next_lesson.room.number}",
            "status": "Starting soon",
        }

    return {
        "role": "STUDENT",
        "gpa": round(gpa, 2),
        "active_courses": active_courses_count,
        "rank": rank_str,
        "today_overview": today_overview,
    }


def get_teacher_dashboard_data(teacher):
    todays_classes_count = 5
    active_courses_count = 12
    student_groups_count = 6

    today = timezone.now().strftime("%A")
    next_lesson = (
        ScheduleEntry.objects.filter(
            course_offering__teacher_id=teacher.id, day_of_week__iexact=today
        )
        .select_related(
            "course_offering__course", "course_offering__group", "room", "time_slot"
        )
        .first()
    )

    today_overview = None
    if next_lesson:
        today_overview = {
            "title": next_lesson.course_offering.course.title,
            "time": str(next_lesson.time_slot.start_time)[:5],
            "room": f"Room {next_lesson.room.number}",
            "group_name": next_lesson.course_offering.group.name,
        }

    return {
        "role": "TEACHER",
        "todays_classes": todays_classes_count,
        "active_courses": active_courses_count,
        "student_groups": student_groups_count,
        "today_overview": today_overview,
    }
