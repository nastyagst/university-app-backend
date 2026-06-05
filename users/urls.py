from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    OTPRequestView,
    OTPVerifyView,
    FirstLoginView,
    UserProfileView,
    ScheduleViewSet,
)

router = DefaultRouter()
router.register(r"schedule", ScheduleViewSet, basename="schedule")

urlpatterns = [
    path("auth/request-otp/", OTPRequestView.as_view(), name="request_otp"),
    path("auth/verify-otp/", OTPVerifyView.as_view(), name="verify_otp"),
    path("auth/profile/first-login/", FirstLoginView.as_view(), name="first_login"),
    path("auth/profile/", UserProfileView.as_view(), name="user_profile"),
    path("", include(router.urls)),
]
