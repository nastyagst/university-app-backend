from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget, Widget
from .models import Grade, Lesson, CustomUser


class LessonByDateWidget(Widget):

    def clean(self, value, row=None, *args, **kwargs):
        course_offering_id = row.get("course_offering_id")
        date_val = row.get("date")

        if not course_offering_id or not date_val:
            return None

        try:
            lesson, created = Lesson.objects.get_or_create(
                course_offering_id=course_offering_id,
                date=date_val,
                defaults={"topic": "Imported Lesson"},
            )
            return lesson
        except Lesson.MultipleObjectsReturned:
            return Lesson.objects.filter(
                course_offering_id=course_offering_id, date=date_val
            ).first()

    def render(self, value, obj=None):
        return value.date if value else ""


class GradeResource(resources.ModelResource):
    student = fields.Field(
        column_name="student_id",
        attribute="student",
        widget=ForeignKeyWidget(CustomUser, field="id"),
    )

    lesson = fields.Field(
        column_name="date", attribute="lesson", widget=LessonByDateWidget()
    )

    score = fields.Field(column_name="value", attribute="score")

    class Meta:
        model = Grade
        fields = ("id", "student", "lesson", "score")
        export_order = ("id", "student", "lesson", "score")
        import_id_fields = ("student", "lesson")
        use_transactions = True

    def before_import_row(self, row, **kwargs):
        if "value" in row and row["value"]:
            try:
                row["value"] = int(float(row["value"]))
            except ValueError:
                row["value"] = 0
