"""Forms for the daily work log."""
from django import forms

from apps.employees.models import Employee, WorkLogEntry, WorkLogStatus


class WorkLogEntryForm(forms.ModelForm):
    """Create a work log entry. Hours are derived from times when provided."""

    employee = forms.ModelChoiceField(
        queryset=Employee.objects.select_related("user").order_by("full_name"),
        label="Employee",
    )

    class Meta:
        model = WorkLogEntry
        fields = ["employee", "work_date", "start_time", "end_time", "hours_worked", "notes"]
        widgets = {
            "work_date": forms.DateInput(attrs={"type": "date"}),
            "start_time": forms.TimeInput(attrs={"type": "time"}),
            "end_time": forms.TimeInput(attrs={"type": "time"}),
            "hours_worked": forms.NumberInput(attrs={"step": "0.25", "min": "0"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_time")
        end = cleaned.get("end_time")
        hours = cleaned.get("hours_worked")
        if start and end and end <= start:
            self.add_error("end_time", "End time must be after start time.")
        if not hours and not (start and end):
            self.add_error("hours_worked", "Enter hours worked or provide both start and end times.")
        return cleaned


class WorkLogFilterForm(forms.Form):
    employee = forms.ModelChoiceField(
        queryset=Employee.objects.select_related("user").order_by("full_name"),
        required=False,
        label="Employee",
    )
    status = forms.ChoiceField(
        choices=[("", "All statuses")] + list(WorkLogStatus.choices),
        required=False,
        label="Status",
    )
    from_date = forms.DateField(
        required=False,
        label="From",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    to_date = forms.DateField(
        required=False,
        label="To",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
