from django.urls import path

from apps.services.views import service as service_views

app_name = "services"

urlpatterns = [
    path("", service_views.ServiceListView.as_view(), name="list"),
    path("custom-fields-json/", service_views.ServiceCustomFieldsJsonView.as_view(), name="custom_fields_json"),
    path("<uuid:pk>/", service_views.ServiceDetailView.as_view(), name="detail"),
    path("<uuid:pk>/deactivate/", service_views.ServiceDeactivateView.as_view(), name="deactivate"),
    path("<uuid:pk>/fields/", service_views.ServiceCustomFieldCreateView.as_view(), name="field_create"),
    path("<uuid:pk>/fields/<uuid:field_pk>/delete/", service_views.ServiceCustomFieldDeleteView.as_view(), name="field_delete"),
]
