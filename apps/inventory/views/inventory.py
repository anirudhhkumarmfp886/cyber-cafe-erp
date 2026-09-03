"""
Inventory views — thin CBVs delegating to the service layer.

Follows the same pattern as customers/services: list page has an inline
create form, detail shows the movement ledger, stock-in/out/adjust are
separate form pages.
"""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import DetailView, ListView, UpdateView

from apps.common.services.notification_service import NotificationService
from apps.inventory.forms.inventory_forms import (
    AdjustmentForm,
    StockInForm,
    StockItemForm,
    StockOutForm,
)
from apps.inventory.models import StockItem
from apps.inventory.selectors.inventory_selector import InventorySelector
from apps.inventory.services.inventory_service import InventoryService


class StockItemListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = "inventory.view_stockitem"
    template_name = "inventory/item_list.html"
    context_object_name = "items"
    paginate_by = 20

    def get_queryset(self):
        return InventorySelector.list_items(filters={
            "q": self.request.GET.get("q", ""),
            "category": self.request.GET.get("category", ""),
        })

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Inventory"
        context["q"] = self.request.GET.get("q", "")
        context["selected_category"] = self.request.GET.get("category", "")
        context["categories"] = InventorySelector.categories()
        context["low_stock_count"] = InventorySelector.count_low_stock()
        if context["low_stock_count"]:
            low_items = list(InventorySelector.low_stock_items())
            context["whatsapp_url"] = NotificationService.get_low_stock_whatsapp_url(low_items)
        if self.request.user.has_perm("inventory.add_stockitem"):
            context["item_form"] = StockItemForm()
        return context

    def get_form_error_response(self, form):
        self.object_list = self.get_queryset()
        context = self.get_context_data()
        context["item_form"] = form
        return self.render_to_response(context)

    def post(self, request):
        if not request.user.has_perm("inventory.add_stockitem"):
            return self.handle_no_permission()
        form = StockItemForm(request.POST)
        if form.is_valid():
            try:
                item = InventoryService.create_item(
                    data=form.cleaned_data, by=request.user,
                )
            except ValueError as exc:
                messages.error(request, str(exc))
                form.add_error(None, str(exc))
                return self.get_form_error_response(form)
            messages.success(request, f"Stock item '{item.name}' created.")
            return HttpResponseRedirect(
                reverse_lazy("inventory:detail", kwargs={"pk": item.pk})
            )
        return self.get_form_error_response(form)


class StockItemDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    permission_required = "inventory.view_stockitem"
    template_name = "inventory/item_detail.html"
    context_object_name = "item"

    def get_object(self, queryset=None):
        return get_object_or_404(StockItem, id=self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = self.object.name
        context["movements"] = InventorySelector.movement_history(self.object)
        context["whatsapp_url"] = NotificationService.get_stock_item_whatsapp_url(self.object)
        context["stock_text"] = NotificationService.format_stock_item_text(self.object)
        return context


class StockItemUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    permission_required = "inventory.change_stockitem"
    template_name = "inventory/item_form.html"
    form_class = StockItemForm
    model = StockItem

    def get_object(self, queryset=None):
        return get_object_or_404(StockItem, id=self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = f"Edit {self.object.name}"
        return context

    def form_valid(self, form):
        try:
            self.object = InventoryService.update_item(
                self.get_object(), data=form.cleaned_data, by=self.request.user,
            )
        except ValueError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        messages.success(self.request, "Stock item updated successfully.")
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse_lazy("inventory:detail", kwargs={"pk": self.object.pk})


class StockItemDeactivateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "inventory.delete_stockitem"
    http_method_names = ["post"]

    def post(self, request, pk):
        item = get_object_or_404(StockItem, id=pk)
        InventoryService.deactivate_item(item, by=request.user)
        messages.success(request, f"'{item.name}' has been deactivated.")
        return HttpResponseRedirect(reverse_lazy("inventory:list"))


class StockInView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "inventory.add_stockmovement"
    template_name = "inventory/stock_in.html"

    def get_item(self):
        return get_object_or_404(StockItem, id=self.kwargs["pk"])

    def get(self, request, pk):
        from django.shortcuts import render
        item = self.get_item()
        return render(request, self.template_name, {
            "page_title": f"Stock In — {item.name}",
            "item": item,
            "form": StockInForm(),
        })

    def post(self, request, pk):
        from django.shortcuts import render
        item = self.get_item()
        form = StockInForm(request.POST)
        if form.is_valid():
            try:
                movement = InventoryService.stock_in(
                    item,
                    quantity=form.cleaned_data["quantity"],
                    unit_cost=form.cleaned_data["unit_cost"],
                    movement_date=form.cleaned_data.get("movement_date"),
                    supplier_name=form.cleaned_data.get("supplier_name", ""),
                    payment_mode=form.cleaned_data.get("payment_mode", ""),
                    notes=form.cleaned_data.get("notes", ""),
                    by=request.user,
                )
            except ValueError as exc:
                messages.error(request, str(exc))
                return render(request, self.template_name, {
                    "page_title": f"Stock In — {item.name}",
                    "item": item,
                    "form": form,
                })
            item.refresh_from_db()
            messages.success(
                request,
                f"{movement.reference_number}: {movement.quantity} units added. "
                f"New stock: {item.current_stock}.",
            )
            return HttpResponseRedirect(
                reverse_lazy("inventory:detail", kwargs={"pk": item.pk})
            )
        return render(request, self.template_name, {
            "page_title": f"Stock In — {item.name}",
            "item": item,
            "form": form,
        })


class StockOutView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "inventory.add_stockmovement"
    template_name = "inventory/stock_out.html"

    def get_item(self):
        return get_object_or_404(StockItem, id=self.kwargs["pk"])

    def get(self, request, pk):
        from django.shortcuts import render
        item = self.get_item()
        return render(request, self.template_name, {
            "page_title": f"Stock Out — {item.name}",
            "item": item,
            "form": StockOutForm(),
        })

    def post(self, request, pk):
        from django.shortcuts import render
        item = self.get_item()
        form = StockOutForm(request.POST)
        if form.is_valid():
            try:
                movement = InventoryService.stock_out(
                    item,
                    quantity=form.cleaned_data["quantity"],
                    movement_type=form.cleaned_data["movement_type"],
                    reason=form.cleaned_data.get("reason", ""),
                    movement_date=form.cleaned_data.get("movement_date"),
                    notes=form.cleaned_data.get("notes", ""),
                    by=request.user,
                )
            except ValueError as exc:
                messages.error(request, str(exc))
                return render(request, self.template_name, {
                    "page_title": f"Stock Out — {item.name}",
                    "item": item,
                    "form": form,
                })
            item.refresh_from_db()
            messages.success(
                request,
                f"{movement.reference_number}: {movement.quantity} units removed. "
                f"Remaining stock: {item.current_stock}.",
            )
            return HttpResponseRedirect(
                reverse_lazy("inventory:detail", kwargs={"pk": item.pk})
            )
        return render(request, self.template_name, {
            "page_title": f"Stock Out — {item.name}",
            "item": item,
            "form": form,
        })


class AdjustStockView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "inventory.change_stockitem"
    template_name = "inventory/adjust.html"

    def get_item(self):
        return get_object_or_404(StockItem, id=self.kwargs["pk"])

    def get(self, request, pk):
        from django.shortcuts import render
        item = self.get_item()
        return render(request, self.template_name, {
            "page_title": f"Adjust Stock — {item.name}",
            "item": item,
            "form": AdjustmentForm(),
        })

    def post(self, request, pk):
        from django.shortcuts import render
        item = self.get_item()
        form = AdjustmentForm(request.POST)
        if form.is_valid():
            try:
                movement = InventoryService.adjust_stock(
                    item,
                    new_quantity=form.cleaned_data["new_quantity"],
                    reason=form.cleaned_data.get("reason", ""),
                    by=request.user,
                )
            except ValueError as exc:
                messages.error(request, str(exc))
                return render(request, self.template_name, {
                    "page_title": f"Adjust Stock — {item.name}",
                    "item": item,
                    "form": form,
                })
            item.refresh_from_db()
            messages.success(
                request,
                f"{movement.reference_number}: Stock adjusted to {item.current_stock}.",
            )
            return HttpResponseRedirect(
                reverse_lazy("inventory:detail", kwargs={"pk": item.pk})
            )
        return render(request, self.template_name, {
            "page_title": f"Adjust Stock — {item.name}",
            "item": item,
            "form": form,
        })


class LowStockView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = "inventory.view_stockitem"
    template_name = "inventory/low_stock.html"
    context_object_name = "items"
    paginate_by = 50

    def get_queryset(self):
        return InventorySelector.low_stock_items()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Low Stock Alerts"
        items = list(self.get_queryset())
        context["whatsapp_url"] = NotificationService.get_low_stock_whatsapp_url(items)
        context["alert_text"] = NotificationService.format_low_stock_summary(items)
        return context
