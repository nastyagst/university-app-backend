from django.contrib import admin
from import_export import resources, fields
from import_export.admin import ImportExportModelAdmin
from import_export.widgets import ForeignKeyWidget
from .models import CustomUser, Group, Department, Course, OTPCode


class CustomUserResource(resources.ModelResource):
    """
    Parsing rules for mapping Excel/CSV columns to our database.
    """

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
    """
    Integrate import/export functionality into the user admin panel.
    """

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


admin.site.register(Group)
admin.site.register(Department)
admin.site.register(Course)
admin.site.register(OTPCode)
