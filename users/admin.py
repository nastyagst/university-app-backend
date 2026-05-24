from django.contrib import admin
from django.core.exceptions import ValidationError
from import_export import resources, fields
from import_export.admin import ImportExportModelAdmin
from import_export.widgets import ForeignKeyWidget
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

    @classmethod
    def get_display_name(cls):
        return "Schedule Template"

    def dehydrate_time_slot_name(self, schedule_entry):
        return (
            f"Пара {schedule_entry.time_slot.number}"
            if schedule_entry.time_slot
            else ""
        )

    def dehydrate_subject(self, schedule_entry):
        return (
            schedule_entry.course_offering.course.name
            if schedule_entry.course_offering
            else ""
        )

    def dehydrate_teacher_name(self, schedule_entry):
        return (
            schedule_entry.course_offering.teacher.last_name
            if schedule_entry.course_offering
            else ""
        )

    def dehydrate_group_name(self, schedule_entry):
        return (
            schedule_entry.course_offering.group.name
            if schedule_entry.course_offering
            else ""
        )

    def dehydrate_auditorium(self, schedule_entry):
        return schedule_entry.room.number if schedule_entry.room else ""

    def before_import(self, dataset, **kwargs):
        if "id" not in dataset.headers:
            dataset.append_col([None] * len(dataset), header="id")
        if "_course_offering_id" not in dataset.headers:
            dataset.append_col([None] * len(dataset), header="_course_offering_id")
        if "_room_id" not in dataset.headers:
            dataset.append_col([None] * len(dataset), header="_room_id")
        if "_time_slot_id" not in dataset.headers:
            dataset.append_col([None] * len(dataset), header="_time_slot_id")

        dry_run = kwargs.get("dry_run", False)
        if not dry_run:
            ScheduleEntry.objects.all().delete()

    def before_import_row(self, row, **kwargs):
        semester = Semester.objects.last()
        if not semester:
            raise ValidationError("Створіть хоча б один семестр в адмінці.")

        subject_name = str(row.get("Subject", "")).strip()
        course = Course.objects.filter(name__iexact=subject_name).first()
        if not course:
            raise ValidationError(f"Предмет '{subject_name}' не знайдено.")

        raw_teacher = str(row.get("Teacher Name", "")).strip()
        teacher = None
        for user in CustomUser.objects.filter(role="TEACHER"):
            if user.last_name in raw_teacher:
                teacher = user
                break
        if not teacher:
            raise ValidationError(f"Викладача '{raw_teacher}' не знайдено.")

        raw_group = str(row.get("Group Name", "")).strip()
        group = Group.objects.filter(name__iexact=raw_group).first()
        if not group:
            raise ValidationError(f"Групу '{raw_group}' не знайдено.")

        raw_room = str(row.get("Auditorium", "")).strip()
        room = Room.objects.filter(number__iexact=raw_room).first()
        if not room:
            raise ValidationError(f"Аудиторію '{raw_room}' не знайдено.")

        raw_slot = str(row.get("Time Slot", ""))
        slot_number = "".join(filter(str.isdigit, raw_slot))
        time_slot = TimeSlot.objects.filter(
            number=int(slot_number) if slot_number else 0
        ).first()
        if not time_slot:
            raise ValidationError(f"Часовий слот '{raw_slot}' не знайдено.")

        course_offering, _ = CourseOffering.objects.get_or_create(
            course=course, teacher=teacher, semester=semester, group=group
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


admin.site.register(Group)
admin.site.register(Department)
admin.site.register(Course)
admin.site.register(OTPCode)
admin.site.register(Semester)
admin.site.register(Room)
admin.site.register(TimeSlot)
admin.site.register(CourseOffering)
