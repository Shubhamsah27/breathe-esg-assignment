from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    OrganizationViewSet, PlantLookupViewSet, IngestionSourceViewSet, 
    IngestionBatchViewSet, NormalizedEmissionRecordViewSet, 
    FileUploadView, TravelIngestionView, DashboardAnalyticsView, SeedDatabaseView,
    RawIngestedRecordViewSet
)

router = DefaultRouter()
router.register('organizations', OrganizationViewSet)
router.register('plants', PlantLookupViewSet)
router.register('sources', IngestionSourceViewSet)
router.register('batches', IngestionBatchViewSet)
router.register('records', NormalizedEmissionRecordViewSet)
router.register('raw-records', RawIngestedRecordViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('upload-file/', FileUploadView.as_view(), name='upload_file'),
    path('submit-travel/', TravelIngestionView.as_view(), name='submit_travel'),
    path('analytics/', DashboardAnalyticsView.as_view(), name='analytics'),
    path('seed/', SeedDatabaseView.as_view(), name='seed_db'),
]
