from django.urls import path
from . import views


urlpatterns = [path("", views.SchemaUploadView.as_view())]
