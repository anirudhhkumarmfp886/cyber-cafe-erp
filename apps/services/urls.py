from django.urls import path

from apps.services.views import service as service_views

app_name = "services"

urlpatterns = [
    path("", service_views.ServiceListView.as_view(), name="list"),
    path("<uuid:pk>/", service_views.ServiceDetailView.as_view(), name="detail"),
    path("<uuid:pk>/deactivate/", service_views.ServiceDeactivateView.as_view(), name="deactivate"),
]
