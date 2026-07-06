from datetime import datetime
import django_filters
import tablib
from django.db import transaction
from django.http import HttpResponse
from rest_framework.decorators import (
    api_view,
    permission_classes,
    parser_classes,
    action,
)
from rest_framework.parsers import MultiPartParser
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from rest_framework.permissions import IsAuthenticated
from rest_framework import status, viewsets, permissions, serializers, generics
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.throttling import AnonRateThrottle
from drf_spectacular.utils import extend_schema, inline_serializer

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
    BulkGradeSerializer,
    DashboardResponseSerializer,
    ChangeRoomSerializer,
    CancelLessonSerializer,
    RescheduleLessonSerializer,
    CourseOfferingDetailSerializer,
    CourseOfferingUpdateSerializer,
)
from .models import (
    CustomUser,
    ScheduleEntry,
    Lesson,
    Attendance,
    Grade,
    ABTest,
    CourseOffering,
)
from .services import generate_and_send_otp
from .analytics import get_student_dashboard_data, get_teacher_dashboard_data


class OTPRequestThrottle(AnonRateThrottle):
    rate = "3/min"


class OTPRequestView(generics.GenericAPIView):
    serializer_class = OTPRequestSerializer
    throttle_classes = [OTPRequestThrottle]

    @extend_schema(
        summary="Request verification code",
        description="Sends a 6-digit OTP verification code to the provided email address.",
        responses={
            200: inline_serializer(
                name="OTPRequestSuccessResponse",
                fields={"message": serializers.CharField()},
            ),
            400: inline_serializer(
                name="OTPRequestErrorResponse",
                fields={"email": serializers.ListField(child=serializers.CharField())},
            ),
        },
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        user = CustomUser.objects.get(email=email)
        generate_and_send_otp(user=user, purpose="ACTIVATION")
        return Response(
            {"message": "Verification code has been sent to your email."},
            status=status.HTTP_200_OK,
        )


class OTPVerifyView(generics.GenericAPIView):
    serializer_class = OTPVerifySerializer

    @extend_schema(
        summary="Verify OTP and get JWT tokens",
        description="Validates the 6-digit OTP code and returns JWT access/refresh tokens along with user details.",
        responses={
            200: inline_serializer(
                name="OTPVerifySuccessResponse",
                fields={
                    "refresh": serializers.CharField(),
                    "access": serializers.CharField(),
                    "user": inline_serializer(
                        name="AuthUserDetails",
                        fields={
                            "email": serializers.EmailField(),
                            "first_name": serializers.CharField(),
                            "last_name": serializers.CharField(),
                            "role": serializers.CharField(),
                            "is_password_changed": serializers.BooleanField(),
                        },
                    ),
                },
            ),
            400: inline_serializer(
                name="OTPVerifyErrorResponse",
                fields={"detail": serializers.CharField()},
            ),
        },
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

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


class FirstLoginView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = FirstLoginSerializer

    @extend_schema(
        summary="Complete first login profile setup",
        description="Updates initial user profile details upon first successful login.",
        responses={
            200: inline_serializer(
                name="FirstLoginSuccessResponse",
                fields={
                    "message": serializers.CharField(),
                    "user": FirstLoginSerializer(),
                },
            ),
            400: inline_serializer(
                name="FirstLoginErrorResponse",
                fields={"detail": serializers.CharField()},
            ),
        },
    )
    def post(self, request, *args, **kwargs):
        user = request.user

        if user.is_password_changed:
            return Response(
                {"detail": "Profile data has already been set during the first login."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = self.get_serializer(user, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {
                "message": "Profile updated successfully.",
                "user": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class UserProfileView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserProfileSerializer

    def get_object(self):
        return self.request.user

    @extend_schema(summary="Retrieve user profile")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(summary="Update user profile")
    def patch(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    def put(self, request, *args, **kwargs):
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)


class ScheduleFilter(django_filters.FilterSet):
    group_id = django_filters.NumberFilter(field_name="course_offering__group_id")
    teacher_id = django_filters.NumberFilter(field_name="course_offering__teacher_id")
    day_of_week = django_filters.CharFilter(
        field_name="day_of_week", lookup_expr="iexact"
    )

    class Meta:
        model = ScheduleEntry
        fields = ["group_id", "teacher_id", "day_of_week"]


class ScheduleViewSet(viewsets.ModelViewSet):
    """
    GET /schedule/ - Retrieve a list of all schedule entries.
    POST /schedule/ - Create a new schedule entry.
    PATCH /schedule/{id}/ - Update a schedule entry.
    DELETE /schedule/{id}/ - Remove a schedule entry.
    """

    serializer_class = ScheduleEntrySerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = ScheduleFilter
    permission_classes = [IsTeacherOrAdminOrReadOnlyForStudent]

    def get_queryset(self):
        return ScheduleEntry.objects.select_related(
            "course_offering__course",
            "course_offering__teacher",
            "course_offering__group",
            "room",
            "time_slot",
        ).all()

    @extend_schema(
        summary="Change permanent schedule room",
        description="Teacher action: permanently changes the assigned room for a weekly schedule entry.",
        request=ChangeRoomSerializer,
        responses={200: ScheduleEntrySerializer},
    )
    @action(detail=True, methods=["post"], url_path="change-room")
    def change_room(self, request, pk=None):
        entry = self.get_object()
        serializer = ChangeRoomSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        entry.room_id = serializer.validated_data["new_room_id"]
        entry.save()

        return Response(ScheduleEntrySerializer(entry).data, status=status.HTTP_200_OK)


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
    filterset_fields = ["course_offering__group_id", "date", "is_cancelled"]
    permission_classes = [IsTeacherOrAdminOrReadOnlyForStudent]

    @extend_schema(
        summary="Reschedule a lesson",
        description="Teacher action: moves a lesson to a new date, time slot, and optionally a new room.",
        request=RescheduleLessonSerializer,
        responses={200: LessonSerializer},
    )
    @action(detail=True, methods=["post"], url_path="reschedule")
    def reschedule(self, request, pk=None):
        lesson = self.get_object()
        serializer = RescheduleLessonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        lesson.date = data["new_date"]
        lesson.time_slot_id = data["new_time_slot_id"]

        if data.get("new_room_id"):
            lesson.room_id = data["new_room_id"]

        lesson.is_cancelled = False
        lesson.save()

        return Response(LessonSerializer(lesson).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Change lesson room",
        description="Teacher action: assigns a new auditorium/room to an existing lesson.",
        request=ChangeRoomSerializer,
        responses={200: LessonSerializer},
    )
    @action(detail=True, methods=["post"], url_path="change-room")
    def change_room(self, request, pk=None):
        lesson = self.get_object()
        serializer = ChangeRoomSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        lesson.room_id = serializer.validated_data["new_room_id"]
        lesson.save()

        return Response(LessonSerializer(lesson).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Cancel a lesson",
        description="Teacher action: marks a lesson as cancelled.",
        request=CancelLessonSerializer,
        responses={200: LessonSerializer},
    )
    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        lesson = self.get_object()
        serializer = CancelLessonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        lesson.is_cancelled = True
        lesson.save()

        return Response(LessonSerializer(lesson).data, status=status.HTTP_200_OK)


class AttendanceViewSet(viewsets.ModelViewSet):
    queryset = Attendance.objects.select_related("lesson", "student").all()
    serializer_class = AttendanceSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["lesson", "student", "status"]
    permission_classes = [IsAuthenticated, IsTeacherOrAdminOrReadOnlyForStudent]


class GradeViewSet(viewsets.ModelViewSet):
    queryset = Grade.objects.select_related("lesson", "student").all()
    serializer_class = GradeSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["lesson", "student"]
    permission_classes = [IsAuthenticated, IsTeacherOrAdminOrReadOnlyForStudent]

    @swagger_auto_schema(
        operation_description="Bulk update or create grades for students. "
        "Used by the Teacher's Grade Journal.",
        request_body=openapi.Schema(
            type=openapi.TYPE_ARRAY,
            items=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "lesson": openapi.Schema(type=openapi.TYPE_INTEGER),
                    "student": openapi.Schema(type=openapi.TYPE_INTEGER),
                    "score": openapi.Schema(type=openapi.TYPE_INTEGER),
                    "comment": openapi.Schema(
                        type=openapi.TYPE_STRING, x_nullable=True
                    ),
                },
                required=["lesson", "student", "score"],
            ),
        ),
        responses={200: "Grades processed successfully.", 400: "Invalid data."},
    )
    @action(detail=False, methods=["post"])
    def bulk_update(self, request):
        serializer = BulkGradeSerializer(data=request.data, many=True)
        if serializer.is_valid():
            with transaction.atomic():
                grades = [Grade(**item) for item in serializer.validated_data]
                Grade.objects.bulk_create(
                    grades,
                    update_conflicts=True,
                    update_fields=["score", "comment"],
                    unique_fields=["lesson", "student"],
                )
            return Response(
                {"message": "Grades processed successfully."}, status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ABTestViewSet(viewsets.ModelViewSet):
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


class DashboardViewSet(viewsets.GenericViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = DashboardResponseSerializer

    @extend_schema(
        summary="Get user dashboard analytics",
        description="Returns GPA and grade statistics for students, or course overview for teachers.",
    )
    def list(self, request):
        user = request.user

        if user.role == CustomUser.Role.STUDENT:
            data = get_student_dashboard_data(user)
        elif user.role == CustomUser.Role.TEACHER:
            data = get_teacher_dashboard_data(user)
        else:
            data = {
                "role": user.role,
                "message": "No dashboard available for this role.",
            }

        return Response(data)


class CourseOfferingViewSet(viewsets.ModelViewSet):
    """
    GET /courses/ - Retrieve list of courses.
    GET /courses/{id}/ - Retrieve detailed course card and syllabus.
    PATCH /courses/{id}/ - Update course details (Teachers/Admins only).
    """

    queryset = (
        CourseOffering.objects.select_related("course", "teacher", "group", "semester")
        .prefetch_related("schedule_entries__room", "schedule_entries__time_slot")
        .all()
    )
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["group_id", "teacher_id", "semester_id"]
    permission_classes = [IsTeacherOrAdminOrReadOnlyForStudent]

    def get_serializer_class(self):
        if self.action in ["update", "partial_update"]:
            return CourseOfferingUpdateSerializer
        return CourseOfferingDetailSerializer
