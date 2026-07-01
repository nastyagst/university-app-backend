from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget, Widget
from .models import Grade, Lesson, CustomUser, TeacherProfile, StudentProfile


class LessonByDateWidget(Widget):
    def clean(self, value, row=None, *args, **kwargs):
        date_val = value
        course_offering_id = row.get("course_offering_id")

        if not course_offering_id or not date_val:
            return None

        try:
            lesson, created = Lesson.objects.get_or_create(
                course_offering_id=course_offering_id,
                date=date_val,
                defaults={"topic": "Imported Lesson"},
            )
            return lesson
        except Exception:
            return None

    def render(self, value, obj=None):
        return value.date if value else ""


class GradeResource(resources.ModelResource):
    student_id = fields.Field(
        column_name="student_id",
        attribute="student_id",
    )

    lesson = fields.Field(
        column_name="date", attribute="lesson", widget=LessonByDateWidget()
    )

    score = fields.Field(column_name="value", attribute="score")

    class Meta:
        model = Grade
        fields = ("student_id", "lesson", "score")
        export_order = ("student_id", "lesson", "score")
        import_id_fields = ("student_id", "lesson")
        use_bulk = True
        batch_size = 2000

    def before_import_row(self, row, **kwargs):
        if "value" in row and row["value"]:
            try:
                row["value"] = int(float(row["value"]))
            except ValueError:
                row["value"] = 0


class StudentProfileResource(resources.ModelResource):
    user = fields.Field(
        column_name="student_id",
        attribute="user",
        widget=ForeignKeyWidget(CustomUser, "id"),
    )
    enrollment_year = fields.Field(
        column_name="entry_year", attribute="enrollment_year"
    )

    class Meta:
        model = StudentProfile
        import_id_fields = ("user",)
        fields = ("user", "enrollment_year")
        use_transactions = True


class TeacherProfileResource(resources.ModelResource):
    user = fields.Field(
        column_name="teacher_id",
        attribute="user",
        widget=ForeignKeyWidget(CustomUser, "id"),
    )

    class Meta:
        model = TeacherProfile
        import_id_fields = ("user",)
        fields = ("user",)
        use_transactions = True
