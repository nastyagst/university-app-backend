from rest_framework import serializers
from users.models import CustomUser, OTPCode


class OTPRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        if not CustomUser.objects.filter(email=value).exists():
            raise serializers.ValidationError(
                "Contact not found. Please reach out to your university administrator."
            )
        return value


class OTPVerifySerializer(serializers.Serializer):
    """
    Accepts email and a 6-digit code entered by the user.
    """

    email = serializers.EmailField()
    code = serializers.CharField(max_length=6)

    def validate(self, data):
        email = data.get("email")
        code = data.get("code")

        try:
            user = CustomUser.objects.get(email=email)
        except CustomUser.DoesNotExist:
            raise serializers.ValidationError("User not found.")

        otp_entry = OTPCode.objects.filter(user=user, is_used=False).last()

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
    """
    Detailed profile serializer tailored to the user's role (Student/Teacher/Admin).
    """

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
