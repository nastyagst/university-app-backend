from django.db import transaction
from rest_framework import serializers
from users.models import (
    CustomUser,
    OTPCode,
    ScheduleEntry,
    Lesson,
    Attendance,
    Grade,
    ABTest,
)


class OTPRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        if not CustomUser.objects.filter(email=value).exists():
            raise serializers.ValidationError(
                "Contact not found. Please reach out to your university administrator."
            )
        return value


class OTPVerifySerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(max_length=6)

    def validate(self, data):
        email = data.get("email")
        code = data.get("code")

        try:
            user = CustomUser.objects.get(email=email)
        except CustomUser.DoesNotExist:
            raise serializers.ValidationError("User not found.")

        with transaction.atomic():
            otp_entry = (
                OTPCode.objects.select_for_update()
                .filter(user=user, is_used=False)
                .last()
            )

            if not otp_entry:
                raise serializers.ValidationError("No active verification code found.")

            if otp_entry.attempts >= 5:
                otp_entry.is_used = True
                otp_entry.save()
                raise serializers.ValidationError(
                    "Too many wrong attempts. Please request a new code."
                )

            if otp_entry.code != code:
                otp_entry.attempts += 1
                otp_entry.save()
                remaining = 5 - otp_entry.attempts
                raise serializers.ValidationError(
                    f"Invalid code. {remaining} attempts remaining."
                )

            if otp_entry.is_expired():
                otp_entry.is_used = True
                otp_entry.save()
                raise serializers.ValidationError(
                    "Code has expired. Please request a new one."
                )

        data["user"] = user
        data["otp_entry"] = otp_entry
        return data


class FirstLoginSerializer(serializers.ModelSerializer):
    """
    Handles filling in first and last name and setting the permanent password.
    """

    first_name = serializers.CharField(required=True, min_length=2, max_length=150)
    last_name = serializers.CharField(required=True, min_length=2, max_length=150)
    password = serializers.CharField(write_only=True, required=True, min_length=8)

    class Meta:
        model = CustomUser
        fields = ["first_name", "last_name", "password"]

    def update(self, instance, validated_data):
        instance.first_name = validated_data["first_name"]
        instance.last_name = validated_data["last_name"]

        instance.set_password(validated_data["password"])

        instance.is_password_changed = True
        instance.save()
        return instance


class UserShortSerializer(serializers.ModelSerializer):
    """
    Short serializer to display classmates in lists.
    """

    full_name = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = ["id", "full_name", "email", "phone_number"]

    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}"


class UserProfileSerializer(serializers.ModelSerializer):
    group_name = serializers.CharField(source="group.name", read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True)
    classmates = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = [
            "id",
            "email",
            "phone_number",
            "first_name",
            "last_name",
            "role",
            "record_book_number",
            "is_password_changed",
            "group_name",
            "department_name",
            "classmates",
        ]

        read_only_fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "role",
            "record_book_number",
            "is_password_changed",
        ]

    def get_classmates(self, obj):
        if obj.role == CustomUser.Role.STUDENT and obj.group:
            classmates_queryset = CustomUser.objects.filter(group=obj.group).exclude(
                id=obj.id
            )
            return UserShortSerializer(classmates_queryset, many=True).data
        return []


class ScheduleEntrySerializer(serializers.ModelSerializer):
    """
    Serializer for Read-Only Schedule API.
    """

    subject = serializers.CharField(
        source="course_offering.course.name", read_only=True
    )
    teacher_first_name = serializers.CharField(
        source="course_offering.teacher.first_name", read_only=True
    )
    teacher_last_name = serializers.CharField(
        source="course_offering.teacher.last_name", read_only=True
    )
    group = serializers.CharField(source="course_offering.group.name", read_only=True)
    time_slot = serializers.CharField(source="time_slot.__str__", read_only=True)
    auditorium = serializers.CharField(source="room.__str__", read_only=True)

    class Meta:
        model = ScheduleEntry
        fields = [
            "id",
            "day_of_week",
            "time_slot",
            "subject",
            "teacher_first_name",
            "teacher_last_name",
            "group",
            "auditorium",
        ]


class LessonSerializer(serializers.ModelSerializer):
    course_name = serializers.CharField(
        source="course_offering.course.name", read_only=True
    )
    group_name = serializers.CharField(
        source="course_offering.group.name", read_only=True
    )
    time_slot_str = serializers.CharField(source="time_slot.__str__", read_only=True)

    class Meta:
        model = Lesson
        fields = [
            "id",
            "course_offering",
            "course_name",
            "group_name",
            "date",
            "time_slot",
            "time_slot_str",
            "room",
            "topic",
        ]


class AttendanceSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.last_name", read_only=True)

    class Meta:
        model = Attendance
        fields = ["id", "lesson", "student", "student_name", "status"]


class GradeSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.last_name", read_only=True)

    class Meta:
        model = Grade
        fields = ["id", "lesson", "student", "student_name", "score", "comment"]


class ABTestSerializer(serializers.ModelSerializer):
    class Meta:
        model = ABTest
        fields = ["id", "user", "test_name", "group"]
