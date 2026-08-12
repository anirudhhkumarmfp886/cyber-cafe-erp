from django.urls import path

from apps.workentry.views import workentry as workentry_views

app_name = "workentry"

urlpatterns = [
    path("", workentry_views.WorkEntryListView.as_view(), name="list"),
    path("<uuid:pk>/", workentry_views.WorkEntryBillView.as_view(), name="bill"),
]
