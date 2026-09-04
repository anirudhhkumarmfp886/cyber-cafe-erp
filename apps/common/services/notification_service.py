"""
NotificationService — format and dispatch customer receipts and shop alerts.

Supports:
1. WhatsApp Click-to-Chat URL generation (instant sharing from browser/mobile
   to customer or owner without requiring paid API keys).
2. Clean plain-text receipt formatting suitable for SMS / WhatsApp / Clipboard.
3. Low-stock summary formatting for owner alerts.
4. Optional SMS provider gateway dispatcher (via settings / env).
"""
import urllib.parse

from django.conf import settings


class NotificationService:
    @staticmethod
    def normalize_phone(phone: str | None) -> str:
        """Strip non-digits and normalize 10-digit Indian numbers with country code 91."""
        if not phone:
            return ""
        digits = "".join(ch for ch in str(phone) if ch.isdigit())
        if len(digits) == 10:
            return f"91{digits}"
        if len(digits) == 11 and digits.startswith("0"):
            return f"91{digits[1:]}"
        if len(digits) == 12 and digits.startswith("91"):
            return digits
        return digits

    @classmethod
    def format_invoice_text(cls, invoice) -> str:
        """Format an invoice as a clean, friendly receipt message."""
        company_name = getattr(settings, "ERP_COMPANY_NAME", "AK Nazar Cyber Cafe")
        lines_text = []
        for line in invoice.lines.all():
            qty_val = int(line.qty) if line.qty == int(line.qty) else line.qty
            qty_str = f" x {qty_val}" if qty_val != 1 else ""
            line_str = f"• {line.description}{qty_str} — ₹{line.amount}"
            if line.pass_through_amount > 0:
                line_str += f"\n  (Cash Given: ₹{line.pass_through_amount} | Fee: ₹{line.income_amount})"
            elif line.withdrawal_summary:
                line_str += f"\n  ({line.withdrawal_summary})"
            lines_text.append(line_str)

        items_block = "\n".join(lines_text) if lines_text else "• Services"

        paid_status = "✅ PAID" if invoice.status == "PAID" else "⏳ UNPAID / DUE"
        payment_mode_str = invoice.get_payment_mode_display() if hasattr(invoice, "get_payment_mode_display") else invoice.payment_mode

        message = (
            f"🧾 *{company_name}*\n"
            f"Invoice #{invoice.invoice_number}\n"
            f"Date: {invoice.billed_on.strftime('%d-%b-%Y')}\n"
            f"Customer: {invoice.customer_display}\n"
            f"--------------------------------\n"
            f"{items_block}\n"
            f"--------------------------------\n"
            f"*Total Amount:* ₹{invoice.total}\n"
            f"*Status:* {paid_status} ({payment_mode_str})\n"
        )

        if invoice.status != "PAID" and hasattr(invoice, "outstanding_amount") and invoice.outstanding_amount > 0:
            message += f"*Balance Due:* ₹{invoice.outstanding_amount}\n"

        message += "\nThank you for visiting AK Nazar Cyber Cafe! 🙏"
        return message

    @classmethod
    def get_invoice_whatsapp_url(cls, invoice, phone: str | None = None) -> str:
        """Generate a wa.me Click-to-Chat link with prefilled receipt text."""
        target_phone = phone or (invoice.customer.phone if invoice.customer else "")
        normalized = cls.normalize_phone(target_phone)
        text = cls.format_invoice_text(invoice)
        encoded_text = urllib.parse.quote(text)
        if normalized:
            return f"https://wa.me/{normalized}?text={encoded_text}"
        return f"https://wa.me/?text={encoded_text}"

    @classmethod
    def format_low_stock_summary(cls, low_stock_items) -> str:
        """Format a summary of items running below reorder levels for the owner."""
        company_name = getattr(settings, "ERP_COMPANY_NAME", "AK Nazar Cyber Cafe")
        items_list = []
        for item in low_stock_items:
            unit_display = item.get_unit_display() if hasattr(item, "get_unit_display") else item.unit
            items_list.append(
                f"⚠️ *{item.name}*: Current: {item.current_stock} {unit_display} (Reorder: {item.reorder_level})"
            )

        items_block = "\n".join(items_list) if items_list else "All items are sufficiently stocked."

        return (
            f"🚨 *{company_name} — Low Stock Alert*\n"
            f"Date: {__import__('datetime').date.today().strftime('%d-%b-%Y')}\n"
            f"--------------------------------\n"
            f"{items_block}\n"
            f"--------------------------------\n"
            f"Please arrange replenishment soon."
        )

    @classmethod
    def get_low_stock_whatsapp_url(cls, low_stock_items, owner_phone: str | None = None) -> str:
        """Generate WhatsApp link for the owner to receive the low stock alert."""
        normalized = cls.normalize_phone(owner_phone) if owner_phone else ""
        text = cls.format_low_stock_summary(low_stock_items)
        encoded_text = urllib.parse.quote(text)
        if normalized:
            return f"https://wa.me/{normalized}?text={encoded_text}"
        return f"https://wa.me/?text={encoded_text}"

    @classmethod
    def format_stock_item_text(cls, item) -> str:
        """Format an individual stock item's summary for sharing via WhatsApp."""
        company_name = getattr(settings, "ERP_COMPANY_NAME", "AK Nazar Cyber Cafe")
        unit_str = item.get_unit_display() if hasattr(item, "get_unit_display") else item.unit
        status_str = "⚠️ LOW STOCK" if item.is_low_stock else "✅ IN STOCK"

        return (
            f"📦 *{company_name} — Inventory Status*\n"
            f"Item: *{item.name}*\n"
            f"Category: {item.category or 'General'}\n"
            f"Current Stock: *{item.current_stock} {unit_str}*\n"
            f"Reorder Level: {item.reorder_level} {unit_str}\n"
            f"Avg Unit Cost: ₹{item.unit_cost}\n"
            f"Total Stock Value: ₹{item.stock_value}\n"
            f"Status: {status_str}\n"
        )

    @classmethod
    def get_stock_item_whatsapp_url(cls, item, phone: str | None = None) -> str:
        """Generate a wa.me link for an individual stock item."""
        normalized = cls.normalize_phone(phone) if phone else ""
        text = cls.format_stock_item_text(item)
        encoded_text = urllib.parse.quote(text)
        if normalized:
            return f"https://wa.me/{normalized}?text={encoded_text}"
        return f"https://wa.me/?text={encoded_text}"
