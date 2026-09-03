from django.urls import path

from apps.inventory.views import inventory as views

app_name = "inventory"

urlpatterns = [
    path("", views.StockItemListView.as_view(), name="list"),
    path("low-stock/", views.LowStockView.as_view(), name="low_stock"),
    path("<uuid:pk>/", views.StockItemDetailView.as_view(), name="detail"),
    path("<uuid:pk>/edit/", views.StockItemUpdateView.as_view(), name="edit"),
    path("<uuid:pk>/deactivate/", views.StockItemDeactivateView.as_view(), name="deactivate"),
    path("<uuid:pk>/stock-in/", views.StockInView.as_view(), name="stock_in"),
    path("<uuid:pk>/stock-out/", views.StockOutView.as_view(), name="stock_out"),
    path("<uuid:pk>/adjust/", views.AdjustStockView.as_view(), name="adjust"),
]
