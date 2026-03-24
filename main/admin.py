import openpyxl
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.template.defaultfilters import default
from django.utils.html import format_html
from django.urls import path
from django.shortcuts import render, redirect
from django import forms
from django.http import HttpResponse
import pandas as pd
from datetime import datetime

from .models import (
    CustomUser, Shipment, Manifest, CustomerMaster, Branch, Fleet,
    VendorMaster, TripOutToVendor, Content
)
from .forms import ManifestForm

admin.site.site_header = "Varsha Transport - ADMIN"
admin.site.site_title = "Varsha Transport - TMS"
admin.site.index_title = "Welcome to Transport Management System"


# -------------------- CUSTOM USER --------------------
@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = (
        'username', 'email', 'first_name', 'last_name',
        'role', 'usertype', 'company_name', 'user_status', 'is_staff'
    )
    list_filter = (
        'role', 'usertype', 'user_status', 'is_staff', 'is_superuser'
    )
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal Info', {
            'fields': (
                'first_name', 'last_name', 'email',
                'gender', 'phone_number',
                'usertype', 'company_name', 'branch'
            )
        }),
        ('Permissions', {
            'fields': (
                'is_active', 'is_staff', 'is_superuser',
                'groups', 'user_permissions'
            )
        }),
        ('Transport Role Info', {'fields': ('role', 'user_status')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'username', 'password1', 'password2',
                'first_name', 'last_name', 'email',
                'gender', 'phone_number',
                'usertype', 'company_name', 'branch',
                'role', 'user_status',
                'is_active', 'is_staff', 'is_superuser',
                'groups', 'user_permissions',
            ),
        }),
    )
    search_fields = ('username', 'email', 'first_name', 'last_name')
    ordering = ('username',)


# -------------------- CONTENT --------------------
@admin.register(Content)
class ContentAdmin(admin.ModelAdmin):
    list_display = (
        'batch_id',
        'shipment',
        'count_of_box',
        'box_weight',
        'dimensions_display',
        'volume_per_box_display',
        'total_volumetric_display'
    )
    search_fields = ('batch_id', 'shipment__consignment_no')
    list_filter = ('shipment__status', 'count_of_box')
    readonly_fields = ('batch_id', 'volume_per_box_display', 'total_volumetric_display')

    def dimensions_display(self, obj):
        """Display dimensions in a readable format"""
        return f"{obj.box_length} × {obj.box_width} × {obj.box_height} cm"

    dimensions_display.short_description = "Dimensions (L×W×H)"

    def volume_per_box_display(self, obj):
        """Display volume per box in CFT"""
        return f"{obj.volume_per_box} CFT"

    volume_per_box_display.short_description = "Volume/Box"

    def total_volumetric_display(self, obj):
        """Display total volumetric weight"""
        return f"{obj.total_volumetric} cm³"

    total_volumetric_display.short_description = "Total Volume"

    fieldsets = (
        ('Shipment Info', {
            'fields': ('shipment', 'batch_id', 'count_of_box')
        }),
        ('Dimensions (cm)', {
            'fields': (
                ('box_length', 'box_width', 'box_height'),
                'box_weight',
            )
        }),
        ('Calculated Values', {
            'fields': ('volume_per_box_display', 'total_volumetric_display'),
            'classes': ('collapse',)
        }),
    )


# -------------------- SHIPMENT --------------------
class ShipmentUploadForm(forms.Form):
    file = forms.FileField()


# Content Inline for Shipment Admin
class ContentInline(admin.TabularInline):
    model = Content
    extra = 1
    readonly_fields = ('batch_id',)
    fields = (
        'batch_id', 'count_of_box', 'box_weight',
        'box_length', 'box_width', 'box_height'
    )


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    inlines = [ContentInline]  # Add content inline

    list_display = (
        'consignment_no', 'billto_customer', 'date', 'origin', 'destination',
        'vehicle_no', 'vendor', 'payment_mode', 'status', 'estimated_delivery_date',
        'delivery_date', 'no_article', 'actual_weight', 'total_quantity', 'pod_preview', 'pod_link_display'
    )
    list_filter = ('status', 'payment_mode', 'shipment_type', 'origin', 'destination')
    search_fields = (
        'consignment_no', 'vehicle_no', 'driver_details',
        'consignor_name', 'consignee_name', 'invoice_ref_number'
    )
    date_hierarchy = 'date'
    readonly_fields = ('consignment_no', 'pod_preview', 'no_article', 'actual_weight', 'charged_weight')

    fieldsets = (
        ('Shipment Identification', {
            'fields': ('consignment_no', 'billto_customer')
        }),
        ('Shipment Info', {
            'fields': ('date', 'freight', 'payment_mode', 'shipment_type', 'shipment_mode', 'status')
        }),
        ('Route & Vehicle', {
            'fields': ('origin', 'origin_pin', 'destination', 'destination_pin', 'vendor',
                       'vehicle_no', 'vehicle_type', 'driver_details')
        }),
        ('Consignor (Shipper)', {
            'fields': ('consignor_name', 'consignor_address', 'consignor_contact', 'consignor_gst')
        }),
        ('Consignee (Receiver)', {
            'fields': ('consignee_name', 'consignee_address', 'consignee_contact', 'consignee_gst')
        }),
        ('Reference Numbers', {
            'fields': ('invoice_ref_number', 'so_number', 'ro_number', 'boe_num', 'ewaybill_number',
                       'additional_ref_number')
        }),
        ('Cargo Details', {
            'fields': ('value', 'pack_type', 'total_quantity'),
            'description': 'Total Quantity is manually entered.'
        }),
        ('Auto-calculated Fields', {
            'fields': ('no_article', 'actual_weight', 'charged_weight'),
            'description': 'These fields are automatically calculated from content items.',
            'classes': ('collapse',)
        }),
        ('Delivery Info', {
            'fields': ('pickedup_date', 'estimated_delivery_date', 'delivery_date')
        }),
        ('Appointment Details', {
            'fields': ('appointment_delivery', 'appointment_date')
        }),
        ('Proof of Delivery', {
            'fields': ('pod_scan', 'pod_link', 'pod_preview')
        }),
        ('Additional Information', {
            'fields': ('remark',),
            'classes': ('collapse',)
        }),
    )

    list_editable = ['status', 'estimated_delivery_date', 'delivery_date', 'total_quantity']

    @admin.display(description='POD Preview', ordering='pod_scan')
    def pod_preview(self, obj):
        if obj.pod_scan:
            return format_html('<a href="{}" target="_blank">📄 View POD</a>', obj.pod_scan.url)
        return "No POD uploaded"

    def pod_link_display(self, obj):
        if obj.pod_link:
            return format_html('<a href="{}" target="_blank">🔗 View POD</a>', obj.pod_link)
        return "-"

    pod_link_display.short_description = "POD Link"

    change_list_template = "admin/shipment_upload.html"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('upload-shipments/', self.upload_shipments, name='upload-shipments'),
            path('download-template/', self.admin_site.admin_view(self.download_template),
                 name='shipment_download_template'),
        ]
        return custom_urls + urls

    def upload_shipments(self, request):
        if request.method == "POST":
            form = ShipmentUploadForm(request.POST, request.FILES)
            if form.is_valid():
                file = form.cleaned_data['file']
                try:
                    if file.name.endswith('.csv'):
                        df = pd.read_csv(file)
                    else:
                        df = pd.read_excel(file)

                    created_count = 0
                    for _, row in df.iterrows():
                        # Initialize date variables
                        date = None
                        estimated_delivery_date = None
                        delivery_date = None
                        appointment_date = None
                        pickedup_date = None

                        # Convert date strings to datetime objects
                        try:
                            if pd.notna(row.get('date')) and row['date']:
                                date = pd.to_datetime(row['date']).date()
                            if pd.notna(row.get('estimated_delivery_date')) and row['estimated_delivery_date']:
                                estimated_delivery_date = pd.to_datetime(row['estimated_delivery_date']).date()
                            if pd.notna(row.get('delivery_date')) and row['delivery_date']:
                                delivery_date = pd.to_datetime(row['delivery_date']).date()
                            if pd.notna(row.get('appointment_date')) and row['appointment_date']:
                                appointment_date = pd.to_datetime(row['appointment_date']).date()
                            if pd.notna(row.get('pickedup_date')) and row['pickedup_date']:
                                pickedup_date = pd.to_datetime(row['pickedup_date']).date()
                        except Exception as e:
                            self.message_user(request,
                                              f"❌ Error in date format for row {row.get('consignment_no', 'Unknown')}: {e}",
                                              level=messages.ERROR)
                            continue

                        # Create shipment (including manual total_quantity)
                        shipment = Shipment.objects.create(
                            date=date,
                            freight=float(row.get('freight', 0)),
                            shipment_type=row.get('shipment_type', 'PTL'),
                            shipment_mode=row.get('shipment_mode', 'By_Road'),
                            payment_mode=row.get('payment_mode', 'TO-PAY'),
                            origin=row.get('origin', ''),
                            origin_pin=str(row.get('origin_pin', '')),
                            destination=row.get('destination', ''),
                            destination_pin=str(row.get('destination_pin', '')),
                            vehicle_no=row.get('vehicle_no', ''),
                            vehicle_type=row.get('vehicle_type', 'LCV'),
                            driver_details=row.get('driver_details', ''),
                            consignor_name=row.get('consignor_name', ''),
                            consignor_address=row.get('consignor_address', ''),
                            consignor_gst=row.get('consignor_gst', ''),
                            consignor_contact=str(row.get('consignor_contact', '')),
                            consignee_name=row.get('consignee_name', ''),
                            consignee_address=row.get('consignee_address', ''),
                            consignee_gst=row.get('consignee_gst', ''),
                            consignee_contact=str(row.get('consignee_contact', '')),
                            invoice_ref_number=row.get('invoice_ref_number', ''),
                            so_number=row.get('so_number', ''),
                            ro_number=row.get('ro_number', ''),
                            boe_num=row.get('boe_num', ''),
                            ewaybill_number=row.get('ewaybill_number', ''),
                            additional_ref_number=row.get('additional_ref_number', ''),
                            value=float(row.get('value', 0)),
                            pack_type=row.get('pack_type', 'Box'),
                            # Manual total_quantity field
                            total_quantity=int(row.get('total_quantity', 0)) if pd.notna(row.get('total_quantity')) else 0,
                            status=row.get('status', 'Booked'),
                            pickedup_date=pickedup_date,
                            estimated_delivery_date=estimated_delivery_date,
                            delivery_date=delivery_date,
                            appointment_delivery=bool(row.get('appointment_delivery', False)),
                            appointment_date=appointment_date,
                            remark=row.get('remark', ''),
                            pod_link=row.get('pod_link', ''),
                        )
                        created_count += 1

                    self.message_user(request, f"✅ Successfully uploaded {created_count} shipments.",
                                      level=messages.SUCCESS)
                    return redirect("..")
                except Exception as e:
                    self.message_user(request, f"❌ Error: {e}", level=messages.ERROR)
        else:
            form = ShipmentUploadForm()

        context = {
            'form': form,
            'title': 'Upload Shipments from File',
        }
        return render(request, "admin/upload_form.html", context)

    def download_template(self, request):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Shipment Template"

        # Updated headers (with total_quantity as manual field)
        headers = [
            "date", "freight", "shipment_type", "shipment_mode", "payment_mode",
            "origin", "origin_pin", "destination", "destination_pin",
            "vehicle_no", "vehicle_type", "driver_details",
            "consignor_name", "consignor_address", "consignor_gst", "consignor_contact",
            "consignee_name", "consignee_address", "consignee_gst", "consignee_contact",
            "invoice_ref_number", "so_number", "ro_number", "boe_num",
            "ewaybill_number", "additional_ref_number",
            "value", "pack_type", "total_quantity", "status",
            "pickedup_date", "estimated_delivery_date", "delivery_date",
            "appointment_delivery", "appointment_date", "remark", "pod_link"
        ]

        ws.append(headers)

        # Example row (with total_quantity example)
        ws.append([
            "2025-08-13", 1500.00, "PTL", "By_Road", "TO-PAY",
            "Bengaluru", "560001", "Chennai", "600001",
            "KA01AB1234", "LCV", "John Doe",
            "ABC Corp", "123 Street, Bengaluru", "29ABCDE1234F1Z5", "9876543210",
            "XYZ Pvt Ltd", "456 Street, Chennai", "33FGHIJ5678L9M", "9876501234",
            "INV-001", "SO-001", "RO-001", "BOE-001",
            "EWB12345", "ADD-001",
            50000.00, "Box", 5, "Booked",  # total_quantity = 5 (manual entry)
            "2025-08-13", "2025-08-15", "2025-08-20",
            False, "", "Handle with care", "http://example.com/pod.pdf"
        ])

        response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = 'attachment; filename="shipment_template.xlsx"'
        wb.save(response)
        return response


# -------------------- MANIFEST --------------------
@admin.register(Manifest)
class ManifestAdmin(admin.ModelAdmin):
    form = ManifestForm
    list_display = (
        'manifest_id', 'vendor_name', 'vehicle_no', 'origin_branch', 'destination_branch',
        'total_articles', 'total_freight', 'created_at'
    )
    search_fields = (
        'manifest_id', 'vehicle_no', 'driver_name',
        'origin_branch', 'destination_branch'
    )
    list_filter = ('vendor_name', 'origin_branch', 'destination_branch', 'created_at')
    filter_horizontal = ('shipments',)
    readonly_fields = ('manifest_id',)


# -------------------- CUSTOMER --------------------
@admin.register(CustomerMaster)
class CustomerAdmin(admin.ModelAdmin):
    list_display = (
        'customer_id', 'company_name',
        'city', 'state', 'country',
        'contact_person', 'contact_number',
        'email_id', 'status',
        'contract_date_from', 'contract_date_to',
    )
    list_filter = ('status', 'state', 'country')
    search_fields = (
        'customer_id', 'company_name', 'gstn',
        'pan', 'cin', 'contact_person',
        'contact_number', 'email_id',
    )
    ordering = ('company_name',)
    date_hierarchy = 'contract_date_from'
    readonly_fields = ('customer_id',)

    fieldsets = (
        ('Basic Info', {
            'fields': ('customer_id', 'company_name', 'status')
        }),
        ('Address Info', {
            'fields': ('billing_address', 'city', 'pin_code', 'state', 'country')
        }),
        ('Legal Info', {
            'fields': ('gstn', 'pan', 'cin')
        }),
        ('Contact Info', {
            'fields': ('contact_person', 'contact_number', 'email_id')
        }),
        ('Contract Period', {
            'fields': ('contract_date_from', 'contract_date_to')
        }),
    )


# -------------------- BRANCH --------------------
@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ('branch_code', 'name', 'city', 'state', 'phone_number', 'is_active')
    list_filter = ('state', 'is_active')
    search_fields = ('branch_code', 'name', 'city', 'state')
    ordering = ('branch_code',)


# -------------------- FLEET --------------------
@admin.register(Fleet)
class FleetMasterAdmin(admin.ModelAdmin):
    list_display = (
        'vehicle_number', 'vehicle_type', 'capacity_mt', 'status',
        'insurance_expiry', 'fitness_certificate_expiry'
    )
    search_fields = ('vehicle_number', 'vehicle_type', 'owner_name')
    list_filter = ('vehicle_type', 'status', 'branch')
    readonly_fields = ('insurance_expiry', 'fitness_certificate_expiry')
    ordering = ('vehicle_number',)

    fieldsets = (
        ('Vehicle Details', {
            'fields': ('vehicle_number', 'vehicle_type', 'capacity_mt', 'status')
        }),
        ('Vehicle Specifications', {
            'fields': ('make', 'model', 'year_of_manufacture')
        }),
        ('Ownership & Branch', {
            'fields': ('owner_name', 'owner_contact', 'branch')
        }),
        ('Document Validity', {
            'fields': (
                'insurance_validity', 'insurance_expiry',
                'fitness_validity', 'fitness_certificate_expiry',
                'permit_validity', 'pollution_validity'
            )
        }),
        ('Additional Info', {
            'fields': ('remarks',),
            'classes': ('collapse',)
        }),
    )


# -------------------- VENDOR --------------------
@admin.register(VendorMaster)
class VendorAdmin(admin.ModelAdmin):
    list_display = (
        "vendor_code", "vendor_name", "city", "state",
        "gstn", "pan", "status", "created_at",
    )
    search_fields = ("vendor_code", "vendor_name", "city", "state", "gstn", "pan")
    list_filter = ("status", "state", "created_at")
    ordering = ("-created_at",)
    readonly_fields = ('vendor_code',)

    fieldsets = (
        ('Basic Info', {
            'fields': ('vendor_code', 'vendor_name', 'status')
        }),
        ('Address Info', {
            'fields': ('billing_address', 'city', 'state', 'country')
        }),
        ('Tax Info', {
            'fields': ('gstn', 'pan')
        }),
        ('Additional Info', {
            'fields': ('short_intro', 'active_till'),
            'classes': ('collapse',)
        }),
    )


# -------------------- TRIP --------------------
@admin.register(TripOutToVendor)
class TripOutToVendorAdmin(admin.ModelAdmin):
    list_display = (
        "trip_id", "vendor", "vehicle_type", "vehicle_capacity",
        "from_location", "destination", "kilometer",
        "trip_charge", "additional_charge", "total_bill_amount",
        "status", "created_at",
    )
    search_fields = (
        "trip_id", "vendor__vendor_name", "vehicle_type",
        "from_location", "destination",
    )
    list_filter = ("status", "vendor", "created_at")
    ordering = ("-created_at",)
    readonly_fields = ('trip_id', 'total_bill_amount')

    fieldsets = (
        ('Trip Info', {
            'fields': ('trip_id', 'vendor', 'status')
        }),
        ('Vehicle & Route', {
            'fields': (
                'vehicle_type', 'vehicle_capacity',
                'from_location', 'destination', 'kilometer'
            )
        }),
        ('Financial Details', {
            'fields': ('trip_charge', 'additional_charge', 'total_bill_amount')
        }),
    )

    def save_model(self, request, obj, form, change):
        # Auto calculate total bill if missing
        if not obj.total_bill_amount:
            obj.total_bill_amount = (obj.trip_charge or 0) + (obj.additional_charge or 0)
        super().save_model(request, obj, form, change)
