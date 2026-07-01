from django.contrib import admin
from django.core.exceptions import ValidationError
from import_export import resources, fields
from import_export.admin import ImportExportModelAdmin
from import_export.widgets import ForeignKeyWidget

from .resources import GradeResource, StudentProfileResource, TeacherProfileResource
from .models import (
    CustomUser,
    Group,
    Department,
    Course,
    OTPCode,
    ScheduleEntry,
    Semester,
    Room,
    TimeSlot,
    CourseOffering,
    Lesson,
    Attendance,
    Grade,
    ABTest,
    StudentProfile,
    TeacherProfile,
)


class CustomUserResource(resources.ModelResource):
    group = fields.Field(
        column_name="group", attribute="group", widget=ForeignKeyWidget(Group, "name")
    )
    department = fields.Field(
        column_name="department",
        attribute="department",
        widget=ForeignKeyWidget(Department, "name"),
    )

    class Meta:
        model = CustomUser
        fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "phone_number",
            "role",
            "group",
            "department",
        )
        import_id_fields = ("email",)
        skip_unchanged = True


@admin.register(CustomUser)
class CustomUserAdmin(ImportExportModelAdmin):
    resource_classes = [CustomUserResource]
    list_display = ("email", "first_name", "last_name", "role", "group", "department")
    list_filter = ("role", "group", "department")
    search_fields = ("email", "first_name", "last_name")
    fields = (
        "email",
        "first_name",
        "last_name",
        "phone_number",
        "role",
        "group",
        "department",
        "record_book_number",
        "is_password_changed",
        "is_staff",
        "is_superuser",
        "is_active",
    )


class ScheduleResource(resources.ModelResource):
    day = fields.Field(column_name="Day", attribute="day_of_week")
    time_slot_name = fields.Field(column_name="Time Slot", readonly=True)
    subject = fields.Field(column_name="Subject", readonly=True)
    teacher_name = fields.Field(column_name="Teacher Name", readonly=True)
    group_name = fields.Field(column_name="Group Name", readonly=True)
    auditorium = fields.Field(column_name="Auditorium", readonly=True)

    course_offering_id = fields.Field(
        column_name="_course_offering_id", attribute="course_offering_id"
    )
    room_id = fields.Field(column_name="_room_id", attribute="room_id")
    time_slot_id = fields.Field(column_name="_time_slot_id", attribute="time_slot_id")

    class Meta:
        model = ScheduleEntry
        fields = (
            "id",
            "day",
            "time_slot_name",
            "subject",
            "teacher_name",
            "group_name",
            "auditorium",
            "course_offering_id",
            "room_id",
            "time_slot_id",
        )
        export_order = (
            "day",
            "time_slot_name",
            "subject",
            "teacher_name",
            "group_name",
            "auditorium",
        )
        use_bulk = False

    def skip_row(self, instance, original, row, import_validation_errors=None):
        required_fields = [
            "Day",
            "Time Slot",
            "Subject",
            "Teacher Name",
            "Group Name",
            "Auditorium",
        ]
        if not any(row.get(field) for field in required_fields):
            return True
        return super().skip_row(instance, original, row, import_validation_errors)

    def before_import(self, dataset, **kwargs):
        for col_name in ["id", "_course_offering_id", "_room_id", "_time_slot_id"]:
            if col_name not in dataset.headers:
                dataset.append_col([None] * len(dataset), header=col_name)

        ScheduleEntry.objects.all().delete()

        self.courses_cache = {c.name.strip().lower(): c for c in Course.objects.all()}
        self.groups_cache = {g.name.strip().lower(): g for g in Group.objects.all()}
        self.rooms_cache = {r.number.strip().lower(): r for r in Room.objects.all()}
        self.time_slots_cache = {t.number: t for t in TimeSlot.objects.all()}

        self.teachers_cache = {}
        for user in CustomUser.objects.filter(role="TEACHER"):
            if user.last_name:
                self.teachers_cache[user.last_name.strip().lower()] = user

        self.semester = Semester.objects.last()

        self.booked_slots = set()

    def before_import_row(self, row, **kwargs):
        if not self.semester:
            raise ValidationError("Створіть хоча б один семестр в адмінці.")

        def get_clean_str(field_name):
            val = row.get(field_name)
            return str(val).strip() if val is not None else ""

        day_val = get_clean_str("Day")
        subject_name = get_clean_str("Subject")
        raw_teacher = get_clean_str("Teacher Name")
        raw_group = get_clean_str("Group Name")
        raw_room = get_clean_str("Auditorium")
        raw_slot = get_clean_str("Time Slot")

        if not any([day_val, subject_name, raw_teacher, raw_group, raw_room, raw_slot]):
            return

        course = self.courses_cache.get(subject_name.lower())
        if not course:
            raise ValidationError(f"Предмет '{subject_name}' не знайдено.")

        teacher_surname = raw_teacher.split()[0].lower() if raw_teacher else ""
        teacher = self.teachers_cache.get(teacher_surname)
        if not teacher:
            raise ValidationError(f"Викладача '{raw_teacher}' не знайдено.")

        group = self.groups_cache.get(raw_group.lower())
        if not group:
            raise ValidationError(f"Групу '{raw_group}' не знайдено.")

        room = self.rooms_cache.get(raw_room.lower())
        if not room:
            raise ValidationError(f"Аудиторію '{raw_room}' не знайдено.")

        slot_number_str = "".join(filter(str.isdigit, raw_slot))
        try:
            slot_number = int(slot_number_str) if slot_number_str else 0
        except ValueError:
            raise ValidationError(f"Невірний формат часового слоту '{raw_slot}'.")

        time_slot = self.time_slots_cache.get(slot_number)
        if not time_slot:
            raise ValidationError(f"Часовий слот '{raw_slot}' не знайдено.")

        day_key = day_val.lower()
        room_conflict = (day_key, time_slot.id, f"room_{room.id}")
        group_conflict = (day_key, time_slot.id, f"group_{group.id}")
        teacher_conflict = (day_key, time_slot.id, f"teacher_{teacher.id}")

        if room_conflict in self.booked_slots:
            raise ValidationError(
                f"Конфлікт: Аудиторія '{raw_room}' вже зайнята на {day_val}, слот '{raw_slot}'."
            )
        if group_conflict in self.booked_slots:
            raise ValidationError(
                f"Конфлікт: Група '{raw_group}' вже має заняття на {day_val}, слот '{raw_slot}'."
            )
        if teacher_conflict in self.booked_slots:
            raise ValidationError(
                f"Конфлікт: Викладач '{raw_teacher}' вже має заняття на {day_val}, слот '{raw_slot}'."
            )

        self.booked_slots.add(room_conflict)
        self.booked_slots.add(group_conflict)
        self.booked_slots.add(teacher_conflict)

        course_offering, _ = CourseOffering.objects.get_or_create(
            course=course, teacher=teacher, semester=self.semester, group=group
        )

        row["_course_offering_id"] = course_offering.id
        row["_room_id"] = room.id
        row["_time_slot_id"] = time_slot.id


@admin.register(ScheduleEntry)
class ScheduleEntryAdmin(ImportExportModelAdmin):
    resource_classes = [ScheduleResource]
    list_display = (
        "day_of_week",
        "time_slot",
        "get_course",
        "get_teacher",
        "get_group",
        "room",
    )
    list_filter = ("day_of_week", "room")

    def get_course(self, obj):
        try:
            return obj.course_offering.course.name
        except AttributeError:
            return "-"

    get_course.short_description = "Subject"

    def get_teacher(self, obj):
        try:
            return f"{obj.course_offering.teacher.last_name}"
        except AttributeError:
            return "-"

    get_teacher.short_description = "Teacher"

    def get_group(self, obj):
        try:
            return obj.course_offering.group.name
        except AttributeError:
            return "-"

    get_group.short_description = "Group Name"


class LessonResource(resources.ModelResource):
    id = fields.Field(column_name="lesson_id", attribute="id")

    course_offering = fields.Field(
        column_name="course_offering_id",
        attribute="course_offering",
        widget=ForeignKeyWidget(CourseOffering, "id"),
    )

    class Meta:
        model = Lesson
        fields = ("id", "course_offering", "date", "topic", "type")
        import_id_fields = ("id",)
        use_transactions = True


@admin.register(Lesson)
class LessonAdmin(ImportExportModelAdmin):
    resource_classes = [LessonResource]
    list_display = ("course_offering", "date", "time_slot", "room")
    list_filter = ("date",)
    search_fields = ("topic",)


@admin.register(Attendance)
class AttendanceAdmin(ImportExportModelAdmin):
    list_display = ("student", "lesson", "status")
    list_filter = ("status", "lesson__date")
    search_fields = ("student__last_name", "student__first_name")


@admin.register(Grade)
class GradeAdmin(ImportExportModelAdmin):
    resource_classes = [GradeResource]
    list_display = ("student", "lesson", "score")
    list_filter = ("lesson__date",)
    search_fields = ("student__last_name", "student__first_name")


@admin.register(ABTest)
class ABTestAdmin(admin.ModelAdmin):
    list_display = ("user", "test_name", "group")
    list_filter = ("test_name", "group")


@admin.register(StudentProfile)
class StudentProfileAdmin(ImportExportModelAdmin):
    resource_classes = [StudentProfileResource]
    list_display = (
        "user",
        "enrollment_year",
        "faculty",
        "degree_level",
        "get_student_name",
        "enrollment_year",
    )

    def get_student_name(self, obj):
        if hasattr(obj.user, "first_name") and obj.user.first_name:
            return f"{obj.user.first_name} {obj.user.last_name}"
        return getattr(obj.user, "email", "Unknown user")

    search_fields = ("user__email", "user__last_name", "user__first_name")
    list_filter = ("faculty", "degree_level")


@admin.register(TeacherProfile)
class TeacherProfileAdmin(ImportExportModelAdmin):
    resource_classes = [TeacherProfileResource]
    list_display = ("user", "position", "office_room", "get_teacher_name")
    def get_teacher_name(self, obj):
        if hasattr(obj.user, "first_name") and obj.user.first_name:
            return f"{obj.user.first_name} {obj.user.last_name}"
        return getattr(obj.user, "email", "Unknown user")
    search_fields = ("user__email", "user__last_name", "user__first_name")
    list_filter = ("position",)


@admin.register(Group)
class GroupAdmin(ImportExportModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name",)


@admin.register(Department)
class DepartmentAdmin(ImportExportModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name",)


@admin.register(Course)
class CourseAdmin(ImportExportModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name",)


@admin.register(Semester)
class SemesterAdmin(ImportExportModelAdmin):
    list_display = ("id", "number", "year", "date_start", "date_end")
    list_filter = ("year", "number")


@admin.register(Room)
class RoomAdmin(ImportExportModelAdmin):
    list_display = ("id", "building", "number", "type")
    list_filter = ("building", "type")
    search_fields = ("number",)


@admin.register(TimeSlot)
class TimeSlotAdmin(ImportExportModelAdmin):
    list_display = ("id", "number", "time_start", "time_end")


class CourseOfferingResource(resources.ModelResource):
    id = fields.Field(column_name="course_offering_id", attribute="id")
    course = fields.Field(
        column_name="course_id",
        attribute="course",
        widget=ForeignKeyWidget(Course, "id"),
    )
    group = fields.Field(
        column_name="group_id", attribute="group", widget=ForeignKeyWidget(Group, "id")
    )
    teacher = fields.Field(
        column_name="teacher_id",
        attribute="teacher",
        widget=ForeignKeyWidget(CustomUser, "id"),
    )
    semester = fields.Field(
        column_name="semester_id",
        attribute="semester",
        widget=ForeignKeyWidget(Semester, "id"),
    )

    class Meta:
        model = CourseOffering
        fields = ("id", "course", "group", "teacher", "semester")
        import_id_fields = ("id",)


@admin.register(CourseOffering)
class CourseOfferingAdmin(ImportExportModelAdmin):
    resource_classes = [CourseOfferingResource]
    list_display = ("id", "course", "group", "teacher", "semester")
    list_filter = ("semester", "course")
    search_fields = ("course__name", "teacher__last_name", "group__name")


@admin.register(OTPCode)
class OTPCodeAdmin(admin.ModelAdmin):
    list_display = ("user", "code", "created_at")
