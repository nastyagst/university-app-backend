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
