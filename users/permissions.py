from rest_framework import permissions


class IsTeacherOrAdminOrReadOnlyForStudent(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.role in ["ADMIN", "TEACHER"]:
            return True

        if (
            request.user.role == "STUDENT"
            and request.method in permissions.SAFE_METHODS
        ):
            return True

        return False
