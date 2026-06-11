import django_filters
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, viewsets
from rest_framework_simplejwt.tokens import RefreshToken
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.throttling import AnonRateThrottle
from .permissions import IsTeacherOrAdminOrReadOnlyForStudent
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
    Supports query parameters for filtering:
    - ?group_id={id} : Filter by student group
    - ?teacher_id={id} : Filter by teacher
    - ?day_of_week={day} : Filter by specific day (e.g., Monday)
    GET /schedule/{id}/ - Retrieve details of a specific schedule entry by its ID.
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
    Supports filtering by:
    - ?course_offering__group_id={id} : Filter by group
    - ?date={YYYY-MM-DD} : Filter by specific date
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
    Supports filtering by:
    - ?lesson_id={id} : Filter by specific lesson
    - ?student_id={id} : Filter by student
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
    Supports filtering by:
    - ?lesson_id={id} : Filter by specific lesson
    - ?student_id={id} : Filter by student
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
