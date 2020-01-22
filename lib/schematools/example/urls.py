from django.urls import path, include
from rest_framework.routers import DefaultRouter
import views

# Create a router and register our viewsets with it.
router = DefaultRouter()
for dataset_name, viewset in views.fetch_viewsets().items():
    router.register(dataset_name, viewset)

# urlpatterns = router.urls

urlpatterns = [
    path("api/", include(router.urls)),
]
