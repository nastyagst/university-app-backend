from datetime import datetime
import django_filters
import tablib
from django.http import HttpResponse
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, viewsets
from rest_framework_simplejwt.tokens import RefreshToken
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.throttling import AnonRateThrottle

from .permissions import IsTeacherOrAdminOrReadOnlyForStudent
from .resources import GradeResource
from .serializers import (
    OTPRequestSerializer,
    OTPVerifySerializer,
    FirstLoginSerializer,
    UserProfileSerializer,
    ScheduleEntrySerializer,
    LessonSerializer,
    AttendanceSerializer,
    GradeSerializer,
    ABTestSerializer,
)
from .models import CustomUser, ScheduleEntry, Lesson, Attendance, Grade, ABTest
from .services import generate_and_send_otp


class OTPRequestThrottle(AnonRateThrottle):
    rate = "3/min"


class OTPRequestView(APIView):
    """
    POST /api/auth/request-otp/
    """

    throttle_classes = [OTPRequestThrottle]

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
        serializer = FirstLoginSerializer(user, data=request.data)
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


class ScheduleFilter(django_filters.FilterSet):
    group_id = django_filters.NumberFilter(field_name="course_offering__group_id")
    teacher_id = django_filters.NumberFilter(field_name="course_offering__teacher_id")
    day_of_week = django_filters.CharFilter(
        field_name="day_of_week", lookup_expr="iexact"
    )

    class Meta:
        model = ScheduleEntry
        fields = ["group_id", "teacher_id", "day_of_week"]


class ScheduleViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /schedule/ - Retrieve a list of all schedule entries.
    """

    serializer_class = ScheduleEntrySerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = ScheduleFilter

    def get_queryset(self):
        return ScheduleEntry.objects.select_related(
            "course_offering__course",
            "course_offering__teacher",
            "course_offering__group",
            "room",
            "time_slot",
        ).all()


class LessonViewSet(viewsets.ModelViewSet):
    """
    GET /lessons/ - Retrieve a list of all lessons.
    POST /lessons/ - Create a new lesson.
    """

    queryset = Lesson.objects.select_related(
        "course_offering__course", "course_offering__group", "time_slot", "room"
    ).all()
    serializer_class = LessonSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["course_offering__group_id", "date"]


class AttendanceViewSet(viewsets.ModelViewSet):
    """
    GET /attendance/ - Retrieve attendance records.
    POST /attendance/ - Mark student attendance.
    """

    queryset = Attendance.objects.select_related("lesson", "student").all()
    serializer_class = AttendanceSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["lesson", "student", "status"]
    permission_classes = [IsAuthenticated, IsTeacherOrAdminOrReadOnlyForStudent]


class GradeViewSet(viewsets.ModelViewSet):
    """
    GET /grades/ - Retrieve student grades.
    POST /grades/ - Add a new grade.
    """

    queryset = Grade.objects.select_related("lesson", "student").all()
    serializer_class = GradeSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["lesson", "student"]
    permission_classes = [IsAuthenticated, IsTeacherOrAdminOrReadOnlyForStudent]


class ABTestViewSet(viewsets.ModelViewSet):
    """
    GET /ab-tests/ - Retrieve A/B test analytics data.
    """

    queryset = ABTest.objects.all()
    serializer_class = ABTestSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["test_name", "group"]


@swagger_auto_schema(
    method="post",
    tags=["Teacher Grades"],
    operation_description="Import grades. Upload a .csv or .xlsx file.",
    manual_parameters=[
        openapi.Parameter(
            name="excel_file",
            in_=openapi.IN_FORM,
            type=openapi.TYPE_FILE,
            required=True,
            description="Grades file (CSV/Excel)",
        )
    ],
    responses={
        200: "Successful import",
        400: "Data validation failed or invalid file format",
        403: "Access denied. Teachers only",
    },
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser])
def teacher_import_view(request):
    if request.user.role != "TEACHER" and not request.user.is_superuser:
        return Response(
            {"error": "Access is restricted to teachers only."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if "excel_file" not in request.FILES:
        return Response(
            {
                "error": "No file provided. Please upload a file in the 'excel_file' field."
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    excel_file = request.FILES["excel_file"]
    dataset = tablib.Dataset()

    try:
        if excel_file.name.endswith(".xlsx"):
            dataset.load(excel_file.read(), format="xlsx")
        else:
            dataset.load(excel_file.read().decode("utf-8"), format="csv")
    except Exception as e:
        return Response(
            {"error": f"Failed to read the file: {str(e)}"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    grade_resource = GradeResource()
    result = grade_resource.import_data(dataset, dry_run=True, raise_errors=False)

    if result.has_errors():
        error_list = [f"Row {r[0]}: {r[1][0].error}" for r in result.row_errors()]
        return Response(
            {"error": "Data validation failed", "details": error_list},
            status=status.HTTP_400_BAD_REQUEST,
        )

    grade_resource.import_data(dataset, dry_run=False)

    return Response(
        {"message": f"Success! {len(dataset)} grades have been imported."},
        status=status.HTTP_200_OK,
    )


@swagger_auto_schema(
    method="get",
    tags=["Teacher Grades"],
    operation_description="Export all grades to a CSV file.",
    responses={200: "CSV file download", 403: "Access denied. Teachers only"},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def teacher_export_view(request):
    if request.user.role != "TEACHER" and not request.user.is_superuser:
        return Response(
            {"error": "Access is restricted to teachers only."},
            status=status.HTTP_403_FORBIDDEN,
        )

    grade_resource = GradeResource()
    queryset = Grade.objects.select_related("student", "lesson").all()
    dataset = grade_resource.export(queryset)

    current_date = datetime.now().strftime("%Y-%m-%d")
    teacher_name = request.user.email.split("@")[0]
    filename = f"grades_{teacher_name}_{current_date}.csv"

    response = HttpResponse(
        dataset.export("csv"),
        content_type="text/csv",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
