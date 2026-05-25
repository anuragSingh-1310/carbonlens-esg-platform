from django.contrib import admin
from django.urls import path, include

from carbon_app.views import test_api

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('carbon_app.urls')),
    path('api/test/', test_api),
]