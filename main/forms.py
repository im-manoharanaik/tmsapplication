from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.forms import modelformset_factory
from .models import Shipment, Manifest, CustomUser, Content, VendorMaster, TripOutToVendor


class ShipmentForm(forms.ModelForm):
    class Meta:
        model = Shipment
        exclude = [
            'consignment_no',
            'no_article', 'item_count', 'actual_weight', 'charged_weight',
            'length_ft', 'width_ft', 'height', 'total_dfc',
            'delivery_date', 'pod_scan', 'pod_link',
            'created_at', 'updated_at',
        ]
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'pickedup_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'estimated_delivery_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'appointment_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),

            'value': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control'}),
            'pack_type': forms.TextInput(attrs={'class': 'form-control'}),
            # ... other widgets ...

            'total_quantity': forms.NumberInput(attrs={
                'min': 1,
                'class': 'form-control manual-input',
                'placeholder': 'Enter total quantity manually',
                'title': 'Manual entry - not auto-calculated',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        optional_fields = [
            'vendor', 'billto_customer', 'so_number', 'ro_number',
            'boe', 'ewaybill_number', 'additional_ref_number',
            'consignor_gst', 'consignee_gst',
            'estimated_delivery_date', 'appointment_date',
            'remark', 'pickedup_date',
        ]
        for field in optional_fields:
            if field in self.fields:
                self.fields[field].required = False


class ShipmentUpdateForm(forms.ModelForm):
    class Meta:
        model = Shipment
        exclude = [
            'consignment_no',
            'no_article', 'item_count', 'actual_weight', 'charged_weight',
            'length_ft', 'width_ft', 'height', 'total_dfc',
            'created_at', 'updated_at',
        ]
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'pickedup_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'estimated_delivery_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'appointment_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),

            'value': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control'}),
            'pack_type': forms.TextInput(attrs={'class': 'form-control'}),
            # ... other widgets ...

            'total_quantity': forms.NumberInput(attrs={
                'min': 1,
                'class': 'form-control manual-input',
                'placeholder': 'Enter total quantity manually',
                'title': 'Manual entry - not auto-calculated',
            }),

            'pod_scan': forms.FileInput(attrs={'accept': '.pdf,.jpg,.jpeg,.png', 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        optional_fields = [
            'pickedup_date', 'delivery_date', 'so_number', 'ro_number',
            'boe', 'ewaybill_number', 'additional_ref_number',
            'consignor_gst', 'consignee_gst', 'vendor',
            'billto_customer', 'remark', 'pod_scan', 'pod_link',
        ]
        for field in optional_fields:
            if field in self.fields:
                self.fields[field].required = False


class ContentForm(forms.ModelForm):
    """Form for individual content items - updated to match new model structure"""

    class Meta:
        model = Content
        fields = [
            "count_of_box", "box_weight", "box_height",
            "box_length", "box_width"
        ]

        widgets = {
            'count_of_box': forms.NumberInput(attrs={
                'min': '1',
                'step': '1',
                'class': 'form-control'
            }),
            'box_weight': forms.NumberInput(attrs={
                'min': '0.01',
                'step': '0.01',
                'class': 'form-control'
            }),
            'box_length': forms.NumberInput(attrs={
                'min': '0.01',
                'step': '0.01',
                'class': 'form-control',
                'placeholder': 'Length in cm'
            }),
            'box_width': forms.NumberInput(attrs={
                'min': '0.01',
                'step': '0.01',
                'class': 'form-control',
                'placeholder': 'Width in cm'
            }),
            'box_height': forms.NumberInput(attrs={
                'min': '0.01',
                'step': '0.01',
                'class': 'form-control',
                'placeholder': 'Height in cm'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Set all fields as required
        for field_name, field in self.fields.items():
            field.required = True


# ContentFormSet for managing multiple content items
ContentFormSet = modelformset_factory(
    Content,
    form=ContentForm,
    extra=1,  # Start with 1 extra form
    can_delete=True,
    min_num=1,  # At least 1 content item required
    validate_min=True
)


class CustomUserCreationForm(UserCreationForm):
    """Form for creating custom users"""

    class Meta:
        model = CustomUser
        fields = [
            'username',
            'email',
            'gender',
            'phone_number',
            'usertype',
            'company_name',
            'branch',
            'role',
            'password1',
            'password2',
        ]

        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'gender': forms.Select(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
            'usertype': forms.Select(attrs={'class': 'form-control'}),
            'company_name': forms.Select(attrs={'class': 'form-control'}),
            'branch': forms.Select(attrs={'class': 'form-control'}),
            'role': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Set optional fields
        optional_fields = ['company_name', 'branch']
        for field_name in optional_fields:
            if field_name in self.fields:
                self.fields[field_name].required = False

    def clean(self):
        cleaned_data = super().clean()
        usertype = cleaned_data.get('usertype')
        company_name = cleaned_data.get('company_name')

        if usertype == 'External' and not company_name:
            self.add_error('company_name', 'External users must have a company assigned.')

        if usertype == 'Internal' and company_name:
            self.add_error('company_name', 'Internal users should not have a company assigned.')

        return cleaned_data


class ManifestForm(forms.ModelForm):
    """Form for creating manifests"""

    class Meta:
        model = Manifest
        exclude = ['manifest_id', 'created_at', 'total_freight', 'balance_freight', 'total_articles']  # Exclude calculated fields
        widgets = {
            'base_freight': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter base freight',
                'step': '0.01'
            }),
            'advance_amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter advance amount',
                'step': '0.01'
            }),
            'additional_freight': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter additional freight',
                'step': '0.01'
            }),
            'origin_branch': forms.TextInput(attrs={'class': 'form-control'}),
            'destination_branch': forms.TextInput(attrs={'class': 'form-control'}),
            'vehicle_no': forms.TextInput(attrs={'class': 'form-control'}),
            'driver_name': forms.TextInput(attrs={'class': 'form-control'}),
            'driver_contact': forms.TextInput(attrs={'class': 'form-control'}),
            'shipments': forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Filter shipments to only show 'Booked' status
        self.fields['shipments'].queryset = Shipment.objects.filter(status='Booked')

        # Set optional fields
        optional_fields = [
            'vendor_name', 'origin_branch', 'destination_branch', 'vehicle_no',
            'driver_name', 'driver_contact', 'document', 'additional_freight'
        ]

        for field_name in optional_fields:
            if field_name in self.fields:
                self.fields[field_name].required = False

        # Set default values
        self.fields['base_freight'].initial = 0.00
        self.fields['additional_freight'].initial = 0.00
        self.fields['advance_amount'].initial = 0.00

    def clean(self):
        cleaned_data = super().clean()
        shipments = cleaned_data.get('shipments')
        base_freight = cleaned_data.get('base_freight', 0)
        additional_freight = cleaned_data.get('additional_freight', 0)
        advance_amount = cleaned_data.get('advance_amount', 0)

        # Validate shipments selection
        if not shipments or not shipments.exists():
            self.add_error('shipments', 'At least one shipment must be selected.')

        # Calculate server-side totals
        total_freight = base_freight + additional_freight
        balance_freight = total_freight - advance_amount

        # Store calculated values in cleaned_data for use in view
        cleaned_data['total_freight_calculated'] = total_freight
        cleaned_data['balance_freight_calculated'] = balance_freight

        if shipments and shipments.exists():
            total_articles = sum(s.no_article for s in shipments.all())
            cleaned_data['total_articles_calculated'] = total_articles

        return cleaned_data


class PODUploadForm(forms.ModelForm):
    """Form for uploading Proof of Delivery"""

    class Meta:
        model = Shipment
        fields = ['pod_scan', 'pod_link', 'delivery_date', 'status']

        widgets = {
            'pod_scan': forms.FileInput(attrs={
                'accept': '.pdf,.jpg,.jpeg,.png',
                'class': 'form-control'
            }),
            'pod_link': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://example.com/pod-link'
            }),
            'delivery_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
            'status': forms.Select(attrs={'class': 'form-control'})
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Limit status choices to delivery-related statuses
        delivery_statuses = [
            ('Delivered', 'Delivered'),
            ('Partial Delivered', 'Partial Delivered'),
            ('Failed Delivery', 'Failed Delivery'),
            ('Customer Not Available', 'Customer Not Available'),
            ('Address Issue', 'Address Issue'),
            ('Refused by Customer', 'Refused by Customer'),
        ]

        self.fields['status'].choices = delivery_statuses

        # Set optional fields
        optional_fields = ['pod_link', 'delivery_date']
        for field_name in optional_fields:
            if field_name in self.fields:
                self.fields[field_name].required = False

    def clean(self):
        cleaned_data = super().clean()
        pod_scan = cleaned_data.get('pod_scan')
        pod_link = cleaned_data.get('pod_link')
        status = cleaned_data.get('status')

        # Require either POD scan or POD link for delivered status
        if status in ['Delivered', 'Partial Delivered']:
            if not pod_scan and not pod_link:
                raise forms.ValidationError(
                    'Either POD scan file or POD link is required for delivered shipments.'
                )

        return cleaned_data


class VendorMasterForm(forms.ModelForm):
    """Form for managing vendors"""

    class Meta:
        model = VendorMaster
        fields = [
            'vendor_name', 'billing_address', 'city', 'state', 'country',
            'gstn', 'pan', 'short_intro', 'active_till', 'status'
        ]

        widgets = {
            'vendor_name': forms.TextInput(attrs={'class': 'form-control'}),
            'billing_address': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'city': forms.TextInput(attrs={'class': 'form-control'}),
            'state': forms.TextInput(attrs={'class': 'form-control'}),
            'country': forms.TextInput(attrs={'class': 'form-control'}),
            'gstn': forms.TextInput(attrs={'class': 'form-control'}),
            'pan': forms.TextInput(attrs={'class': 'form-control'}),
            'short_intro': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
            'active_till': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Set optional fields
        optional_fields = ['gstn', 'pan', 'short_intro', 'active_till']
        for field_name in optional_fields:
            if field_name in self.fields:
                self.fields[field_name].required = False


class TripOutToVendorForm(forms.ModelForm):
    """Form for managing trips to vendors"""

    class Meta:
        model = TripOutToVendor
        fields = [
            'vendor', 'vehicle_type', 'vehicle_capacity', 'from_location',
            'destination', 'kilometer', 'trip_charge', 'additional_charge',
            'status'
        ]

        widgets = {
            'vendor': forms.Select(attrs={'class': 'form-control'}),
            'vehicle_type': forms.TextInput(attrs={'class': 'form-control'}),
            'vehicle_capacity': forms.NumberInput(attrs={
                'step': '0.01',
                'class': 'form-control',
                'placeholder': 'Capacity in MT'
            }),
            'from_location': forms.TextInput(attrs={'class': 'form-control'}),
            'destination': forms.TextInput(attrs={'class': 'form-control'}),
            'kilometer': forms.NumberInput(attrs={
                'step': '0.01',
                'class': 'form-control'
            }),
            'trip_charge': forms.NumberInput(attrs={
                'step': '0.01',
                'class': 'form-control'
            }),
            'additional_charge': forms.NumberInput(attrs={
                'step': '0.01',
                'class': 'form-control',
                'value': '0.00'
            }),
            'status': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Set optional fields
        optional_fields = ['additional_charge']
        for field_name in optional_fields:
            if field_name in self.fields:
                self.fields[field_name].required = False

        # Set default value for additional_charge
        if 'additional_charge' in self.fields:
            self.fields['additional_charge'].initial = 0.00

    def clean(self):
        cleaned_data = super().clean()
        trip_charge = cleaned_data.get('trip_charge', 0)
        additional_charge = cleaned_data.get('additional_charge', 0)

        # Auto-calculate total_bill_amount (will be handled in model save method)
        if trip_charge is not None and additional_charge is not None:
            cleaned_data['total_bill_amount'] = trip_charge + additional_charge

        return cleaned_data


# Additional utility forms

class ShipmentSearchForm(forms.Form):
    """Form for searching shipments"""

    consignment_no = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter consignment number'
        })
    )

    start_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control'
        })
    )

    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control'
        })
    )

    status = forms.ChoiceField(
        choices=[('', 'All Statuses')] + Shipment.STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )


class BulkTrackingForm(forms.Form):
    """Form for bulk tracking shipments"""

    consignments = forms.CharField(
        widget=forms.Textarea(attrs={
            'rows': 5,
            'class': 'form-control',
            'placeholder': 'Enter consignment numbers (one per line or separated by commas/spaces)'
        }),
        help_text='Enter multiple consignment numbers separated by commas, spaces, or new lines'
    )

    def clean_consignments(self):
        consignments = self.cleaned_data['consignments']
        if not consignments.strip():
            raise forms.ValidationError('Please enter at least one consignment number.')

        # Clean and validate consignment numbers
        consignment_list = [
            cn.strip() for cn in
            consignments.replace(',', ' ').replace('\n', ' ').split()
            if cn.strip()
        ]

        if not consignment_list:
            raise forms.ValidationError('Please enter valid consignment numbers.')

        if len(consignment_list) > 50:
            raise forms.ValidationError('Maximum 50 consignment numbers allowed per search.')

        return ' '.join(consignment_list)
