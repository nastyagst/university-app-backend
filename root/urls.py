from django.contrib import admin
from django.urls import path
from django.http import JsonResponse


# test view
def hello_world(request):
    return JsonResponse({"message": "Hello world!"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", hello_world),
]
