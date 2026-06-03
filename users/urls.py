from django.urls import path
from .views import OTPRequestView, OTPVerifyView, FirstLoginView, UserProfileView

urlpatterns = [
    path("auth/request-otp/", OTPRequestView.as_view(), name="request_otp"),
    path("auth/verify-otp/", OTPVerifyView.as_view(), name="verify_otp"),
    path("auth/profile/first-login/", FirstLoginView.as_view(), name="first_login"),
    path("auth/profile/", UserProfileView.as_view(), name="user_profile"),
]
