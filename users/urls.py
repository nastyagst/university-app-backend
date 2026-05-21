from django.urls import path
from .views import OTPRequestView, OTPVerifyView

urlpatterns = [
    path("auth/request-otp/", OTPRequestView.as_view(), name="request_otp"),
    path("auth/verify-otp/", OTPVerifyView.as_view(), name="verify_otp"),
]
