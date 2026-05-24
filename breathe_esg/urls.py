from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.path if hasattr(admin.site, 'path') else admin.site.urls),
    path('api/v1/', include('ingestion.urls')),
]
