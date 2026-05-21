from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from .serializers import (
    OTPRequestSerializer,
    OTPVerifySerializer,
    FirstLoginSerializer,
    UserProfileSerializer,
)
from .models import CustomUser
from .services import generate_and_send_otp


class OTPRequestView(APIView):
    """
    POST /api/auth/request-otp/
    """

    def post(self, request):
        serializer = OTPRequestSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data["email"]
            user = CustomUser.objects.get(email=email)
            generate_and_send_otp(user=user, purpose="ACTIVATION")
            return Response(
                {"message": "Verification code has been sent to your email."},
                status=status.HTTP_200_OK,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class OTPVerifyView(APIView):
    """
    POST /api/auth/verify-otp/
    """

    def post(self, request):
        serializer = OTPVerifySerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data["user"]
            otp_entry = serializer.validated_data["otp_entry"]

            otp_entry.is_used = True
            otp_entry.save()

            refresh = RefreshToken.for_user(user)
            refresh["role"] = user.role

            return Response(
                {
                    "refresh": str(refresh),
                    "access": str(refresh.access_token),
                    "user": {
                        "email": user.email,
                        "first_name": user.first_name,
                        "last_name": user.last_name,
                        "role": user.role,
                        "is_password_changed": user.is_password_changed,
                    },
                },
                status=status.HTTP_200_OK,
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class FirstLoginView(APIView):
    """
    POST /api/auth/profile/first-login/
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user

        if user.is_password_changed:
            return Response(
                {"detail": "Profile data has already been set during the first login."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = FirstLoginSerializer(user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {
                    "message": "Profile updated successfully.",
                    "user": serializer.data,
                },
                status=status.HTTP_200_OK,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserProfileView(APIView):
    """
    GET /api/auth/profile/ - Retrieve current user profile
    PATCH /api/auth/profile/ - Update personal data
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request):
        serializer = UserProfileSerializer(
            request.user, data=request.data, partial=True
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
