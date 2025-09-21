import csv
import io
from io import BytesIO

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.urls import reverse
from django.contrib.auth import authenticate, login, logout
from django.utils.dateparse import parse_date
from django.template.loader import get_template
from django.forms import modelformset_factory
from django.contrib.auth.decorators import login_required

import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A6
from reportlab.lib.units import inch, mm
from reportlab.graphics.barcode import code128
from xhtml2pdf import pisa

# QR Code imports
import qrcode
import base64

from .models import Shipment, Manifest, Content, CustomerMaster, TripOutToVendor
from .forms import (
    ShipmentForm, ShipmentUpdateForm, ManifestForm,
    CustomUserCreationForm, PODUploadForm, ContentForm, ContentFormSet,
    VendorMasterForm, TripOutToVendorForm
)


# ---------------------------
# QR Code Generation Functions
# ---------------------------

def generate_qr_code_base64(consignment_no):
    """Generate QR code and return as base64 string for embedding in HTML"""
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=4,
            border=2,
        )
        qr.add_data(str(consignment_no))
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        buffer = BytesIO()
        img.save(buffer, format='PNG')
        img_data = buffer.getvalue()
        buffer.close()

        qr_base64 = base64.b64encode(img_data).decode('utf-8')
        return f"data:image/png;base64,{qr_base64}"

    except Exception as e:
        print(f"QR code generation error: {e}")
        return None


def generate_qr_code_url(request, consignment_no):
    """Generate QR code and return as image response for URL-based access"""
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=5,
            border=2,
        )
        qr.add_data(str(consignment_no))
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        response = HttpResponse(content_type='image/png')
        img.save(response, format='PNG')
        return response

    except Exception as e:
        return HttpResponse(status=404)


def generate_tracking_qr_code(consignment_no, tracking_url_base=None):
    """Generate QR code with full tracking URL for better user experience"""
    try:
        if tracking_url_base:
            # Create full tracking URL for QR code
            tracking_data = f"{tracking_url_base}/track/{consignment_no}"
        else:
            # Just use consignment number
            tracking_data = str(consignment_no)

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=4,
            border=2,
        )
        qr.add_data(tracking_data)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        buffer = BytesIO()
        img.save(buffer, format='PNG')
        img_data = buffer.getvalue()
        buffer.close()

        qr_base64 = base64.b64encode(img_data).decode('utf-8')
        return f"data:image/png;base64,{qr_base64}"

    except Exception as e:
        print(f"Tracking QR code generation error: {e}")
        return None


# ---------------------------
# Auth & Basic Pages
# ---------------------------

def main(request):
    return render(request, 'main.html')


def register_user(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'User registered successfully.')
            return redirect('login')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = CustomUserCreationForm()
    return render(request, 'register.html', {'form': form})


def user_logout(request):
    logout(request)
    return redirect(reverse('login'))


def user_login(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user:
            if user.user_status == 'Active':
                login(request, user)
                return redirect('dashboard')
            messages.error(request, 'Your account is inactive. Please contact admin.')
        else:
            messages.error(request, 'Invalid username or password.')
    return render(request, 'main.html')


from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.utils import timezone
from datetime import datetime, timedelta
from .models import Shipment, Content, Manifest
from django.http import JsonResponse
from django.contrib.auth.models import User

@login_required
def dashboard(request):
    """Enhanced dashboard with real-time statistics and data"""

    # Get current date for filtering
    today = timezone.now().date()
    current_month = today.replace(day=1)
    last_month = (current_month - timedelta(days=1)).replace(day=1)

    # Calculate shipment statistics
    shipment_stats = get_shipment_statistics(current_month, last_month)

    # Get recent shipments for quick access
    recent_shipments = Shipment.objects.select_related().order_by('-created_at')[:5] if hasattr(Shipment,
                                                                                                'created_at') else Shipment.objects.order_by(
        '-date')[:5]

    # Calculate fleet utilization (placeholder - adjust based on your fleet model)
    fleet_utilization = calculate_fleet_utilization()

    # Get user-specific data based on user type
    user_permissions = get_user_permissions(request.user)

    # Prepare quick action links based on user permissions
    quick_actions = get_quick_actions(request.user)

    context = {
        'shipment_stats': shipment_stats,
        'recent_shipments': recent_shipments,
        'fleet_utilization': fleet_utilization,
        'user_permissions': user_permissions,
        'quick_actions': quick_actions,
        'current_date': today,
        'user_greeting': get_time_based_greeting(),
    }

    return render(request, 'dashboard.html', context)


def get_shipment_statistics(current_month, last_month):
    """Calculate comprehensive shipment statistics"""

    # Current month stats
    current_total = Shipment.objects.filter(date__gte=current_month).count()
    current_delivered = Shipment.objects.filter(
        date__gte=current_month,
        status__iexact='delivered'
    ).count()
    current_transit = Shipment.objects.filter(
        date__gte=current_month,
        status__iexact='in-transit'
    ).count()
    current_pending = Shipment.objects.filter(
        date__gte=current_month,
        status__iexact='booked'
    ).count()

    # Last month stats for comparison
    last_total = Shipment.objects.filter(
        date__gte=last_month,
        date__lt=current_month
    ).count()
    last_delivered = Shipment.objects.filter(
        date__gte=last_month,
        date__lt=current_month,
        status__iexact='delivered'
    ).count()
    last_transit = Shipment.objects.filter(
        date__gte=last_month,
        date__lt=current_month,
        status__iexact='in-transit'
    ).count()
    last_pending = Shipment.objects.filter(
        date__gte=last_month,
        date__lt=current_month,
        status__iexact='booked'
    ).count()

    # Calculate percentage changes
    def calculate_change(current, previous):
        if previous == 0:
            return 100 if current > 0 else 0
        return round(((current - previous) / previous) * 100, 1)

    return {
        'total_shipments': {
            'current': current_total,
            'change': calculate_change(current_total, last_total),
            'trend': 'positive' if current_total >= last_total else 'negative'
        },
        'delivered': {
            'current': current_delivered,
            'change': calculate_change(current_delivered, last_delivered),
            'trend': 'positive' if current_delivered >= last_delivered else 'negative'
        },
        'in_transit': {
            'current': current_transit,
            'change': calculate_change(current_transit, last_transit),
            'trend': 'positive' if current_transit >= last_transit else 'negative'
        },
        'pending': {
            'current': current_pending,
            'change': calculate_change(current_pending, last_pending),
            'trend': 'positive' if current_pending >= last_pending else 'negative'
        }
    }


def calculate_fleet_utilization():
    """Calculate fleet utilization based on active shipments"""
    # This is a placeholder - adjust based on your fleet/vehicle model
    total_vehicles = 50  # Replace with actual count from your fleet model
    active_shipments = Shipment.objects.filter(
        Q(status__iexact='in-transit') | Q(status__iexact='booked')
    ).count()

    # Assuming each active shipment uses one vehicle
    utilization = min(100, round((active_shipments / total_vehicles) * 100, 1)) if total_vehicles > 0 else 0

    return {
        'rate': utilization,
        'active_vehicles': min(active_shipments, total_vehicles),
        'total_vehicles': total_vehicles
    }


def get_user_permissions(user):
    """Get user-specific permissions and access levels"""
    return {
        'can_create_shipment': user.usertype == 'Internal' if hasattr(user, 'usertype') else True,
        'can_manage_masters': user.usertype == 'Internal' if hasattr(user, 'usertype') else True,
        'can_create_manifest': user.usertype == 'Internal' if hasattr(user, 'usertype') else True,
        'can_upload_pod': user.usertype == 'Internal' if hasattr(user, 'usertype') else True,
        'can_bulk_upload': user.usertype == 'Internal' if hasattr(user, 'usertype') else True,
        'can_view_billing': user.usertype == 'Internal' if hasattr(user, 'usertype') else False,
    }


def get_quick_actions(user):
    """Get user-specific quick actions"""
    actions = [
        {
            'name': 'Track Shipments',
            'url': 'bulk_tracking',
            'icon': 'fas fa-search-location',
            'available': True
        },
        {
            'name': 'View All Shipments',
            'url': 'shipment_list',
            'icon': 'fas fa-list',
            'available': True
        }
    ]

    # Add internal user actions
    if hasattr(user, 'usertype') and user.usertype == 'Internal':
        actions.extend([
            {
                'name': 'Create New Shipment',
                'url': 'shipment_create',
                'icon': 'fas fa-plus',
                'available': True
            },
            {
                'name': 'Create Manifest',
                'url': 'create_manifest',
                'icon': 'fas fa-file-invoice',
                'available': True
            },
            {
                'name': 'Bulk Upload',
                'url': 'shipment_bulk_upload',
                'icon': 'fas fa-upload',
                'available': True
            },
            {
                'name': 'Generate Reports',
                'url': 'shipment_report_download',
                'icon': 'fas fa-chart-bar',
                'available': True
            }
        ])

    return actions


def get_time_based_greeting():
    """Get time-based greeting message"""
    current_hour = datetime.now().hour

    if 5 <= current_hour < 12:
        return "Good Morning"
    elif 12 <= current_hour < 17:
        return "Good Afternoon"
    elif 17 <= current_hour < 21:
        return "Good Evening"
    else:
        return "Good Night"


# Optional: AJAX endpoint for real-time data updates
@login_required
def dashboard_data_api(request, data_type):
    """API endpoint for real-time dashboard data updates"""

    if data_type == 'shipments':
        data = {
            'total': Shipment.objects.count(),
            'today': Shipment.objects.filter(date=timezone.now().date()).count()
        }
    elif data_type == 'status':
        data = {
            'delivered': Shipment.objects.filter(status__iexact='delivered').count(),
            'in_transit': Shipment.objects.filter(status__iexact='in-transit').count(),
            'pending': Shipment.objects.filter(status__iexact='booked').count()
        }
    elif data_type == 'recent':
        recent = Shipment.objects.order_by('-date')[:5]
        data = {
            'shipments': [
                {
                    'consignment_no': ship.consignment_no,
                    'origin': ship.origin,
                    'destination': ship.destination,
                    'status': ship.status,
                    'date': ship.date.strftime('%Y-%m-%d')
                } for ship in recent
            ]
        }
    else:
        data = {'error': 'Invalid data type'}

    return JsonResponse(data)


# ---------------------------
# Shipments
# ---------------------------

from django.http import JsonResponse
from django.db.models import Q
from .models import CustomerMaster


def customer_autocomplete(request):
    """
    AJAX endpoint for customer name autocomplete
    """
    if request.method == 'GET':
        query = request.GET.get('term', '')
        if len(query) < 2:
            return JsonResponse({'results': []})

        customers = CustomerMaster.objects.filter(
            Q(company_name__icontains=query) |
            Q(contact_person__icontains=query) |
            Q(customer_id__icontains=query),
            status='Active'
        ).values(
            'id', 'customer_id', 'company_name', 'contact_person',
            'billing_address', 'city', 'pin_code', 'state', 'country',
            'gstn', 'contact_number', 'email_id'
        )[:10]  # Limit to 10 results

        results = []
        for customer in customers:
            results.append({
                'id': customer['id'],
                'customer_id': customer['customer_id'],
                'label': f"{customer['company_name']} ({customer['contact_person']})",
                'value': customer['company_name'],
                'company_name': customer['company_name'],
                'contact_person': customer['contact_person'],
                'address': customer['billing_address'],
                'city': customer['city'],
                'pin_code': customer['pin_code'],
                'state': customer['state'],
                'country': customer['country'],
                'gstn': customer['gstn'] or '',
                'contact_number': customer['contact_number'],
                'email_id': customer['email_id']
            })

        return JsonResponse({'results': results})

    return JsonResponse({'results': []})


def get_customer_details(request):
    """
    Get detailed customer information by ID
    """
    if request.method == 'GET':
        customer_id = request.GET.get('id')
        try:
            customer = CustomerMaster.objects.get(id=customer_id, status='Active')
            data = {
                'customer_id': customer.customer_id,
                'company_name': customer.company_name,
                'contact_person': customer.contact_person,
                'address': customer.billing_address,
                'city': customer.city,
                'pin_code': customer.pin_code,
                'state': customer.state,
                'country': customer.country,
                'gstn': customer.gstn or '',
                'contact_number': customer.contact_number,
                'email_id': customer.email_id
            }
            return JsonResponse(data)
        except CustomerMaster.DoesNotExist:
            return JsonResponse({'error': 'Customer not found'}, status=404)

    return JsonResponse({'error': 'Invalid request'}, status=400)


import json
from django.contrib import messages
from django.shortcuts import render, redirect
from django.db import transaction
from .models import Shipment, Content
from .forms import ShipmentForm


@transaction.atomic
def shipment_create(request):
    if request.method == 'POST':
        form = ShipmentForm(request.POST)

        # Get dimensions data
        dimensions_data = []
        post_data = request.POST

        # Extract dimensions from POST data
        i = 0
        while f'dimensions[{i}][box_length]' in post_data:
            dimension = {
                'box_length': post_data.get(f'dimensions[{i}][box_length]', 0),
                'box_width': post_data.get(f'dimensions[{i}][box_width]', 0),
                'box_height': post_data.get(f'dimensions[{i}][box_height]', 0),
                'box_type': post_data.get(f'dimensions[{i}][box_type]', ''),
                'count_of_box': post_data.get(f'dimensions[{i}][count_of_box]', 0),
                'box_weight': post_data.get(f'dimensions[{i}][box_weight]', 0),
                'remark': post_data.get(f'dimensions[{i}][remark]', ''),
            }
            dimensions_data.append(dimension)
            i += 1

        if form.is_valid():
            # Validate total box count doesn't exceed articles
            total_boxes = sum(int(dim['count_of_box']) for dim in dimensions_data)
            total_articles = form.cleaned_data.get('no_article', 0)

            if total_boxes > total_articles:
                messages.error(request,
                               f'Total box count ({total_boxes}) cannot exceed number of articles ({total_articles})')
                return render(request, 'shipment_create.html', {'form': form})

            # Save shipment
            shipment = form.save(commit=False)
            if hasattr(request.user, 'customer'):
                shipment.billto_customer = request.user.customer
            shipment.save()

            # Create Content entries
            for i, dimension in enumerate(dimensions_data):
                if any(dimension.values()):  # Only create if has data
                    Content.objects.create(
                        shipment=shipment,
                        box_length=float(dimension['box_length'] or 0),
                        box_width=float(dimension['box_width'] or 0),
                        box_height=float(dimension['box_height'] or 0),
                        box_type=dimension['box_type'] or '',
                        count_of_box=int(dimension['count_of_box'] or 0),
                        box_weight=float(dimension['box_weight'] or 0),
                        remark=dimension['remark'] or '',
                    )

            messages.success(request, f'Shipment {shipment.consignment_no} created successfully!')
            return redirect('shipment_list')

    else:
        form = ShipmentForm()

    return render(request, 'shipment_create.html', {'form': form})


def search_consignment(request):
    return render(request, 'search_consignment.html', {'pagename': 'Search Consignment'})


def update_content(request, consignment_no):
    shipment = get_object_or_404(Shipment, consignment_no=consignment_no)
    queryset = Content.objects.filter(shipment=shipment)

    # Restrict editing if shipment not Booked
    if shipment.status != "Booked":
        messages.error(request, "Shipment is In-Transit. You cannot update the details.")
        return redirect("shipment_detail", pk=shipment.pk)

    ContentFormSet = modelformset_factory(Content, form=ContentForm, extra=0, can_delete=True)

    if request.method == 'POST':
        formset = ContentFormSet(request.POST, queryset=queryset)

        if formset.is_valid():
            instances = formset.save(commit=False)

            # Enforce FTL rule: only 1 box allowed
            if shipment.shipment_type in ["FTL", "FTL-RTO", "FTL-APT", "FTL-NOR"]:
                total_forms = sum(1 for f in formset.cleaned_data if not f.get("DELETE", False))
                if total_forms > 1:
                    messages.error(request, "FTL shipment can only have 1 content/box.")
                    return redirect('update_content', consignment_no=consignment_no)

            # Save instances, set shipment FK if new
            for instance in instances:
                if not instance.pk:
                    instance.shipment = shipment
                instance.save()

            # Delete removed objects
            for obj in formset.deleted_objects:
                obj.delete()

            # Recalculate shipment summary fields
            shipment.update_weights_and_articles()

            messages.success(request, "Boxes updated successfully.")
            return redirect('update_content', consignment_no=consignment_no)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        formset = ContentFormSet(queryset=queryset)

    return render(request, 'update_content.html', {
        'shipment': shipment,
        'formset': formset,
        'pagename': f'Update Box Details for Shipment - {consignment_no}',
    })


@login_required
def shipment_list(request):
    if request.user.usertype == "Internal":
        shipments = Shipment.objects.all().order_by('-date')
    else:
        shipments = Shipment.objects.filter(
            billto_customer=request.user.company_name
        ).order_by('-date')

    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    consignment_no = request.GET.get('consignment_no')

    if start_date:
        shipments = shipments.filter(date__gte=parse_date(start_date))
    if end_date:
        shipments = shipments.filter(date__lte=parse_date(end_date))
    if consignment_no:
        shipments = shipments.filter(consignment_no__icontains=consignment_no)

    return render(request, 'shipment_list.html', {
        'shipments': shipments,
        'pagename': 'Shipment List',
        'start_date': start_date,
        'end_date': end_date,
    })


import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from datetime import datetime


@login_required
@require_http_methods(["POST"])
def bulk_update_shipments(request):
    """
    Handle bulk updates for shipment fields via AJAX
    """
    try:
        data = json.loads(request.body)
        changes = data.get('changes', {})

        if not changes:
            return JsonResponse({'success': False, 'error': 'No changes provided'})

        updated_count = 0
        errors = []

        for shipment_id, fields in changes.items():
            try:
                shipment = Shipment.objects.get(pk=shipment_id)

                # Update each field
                for field_name, value in fields.items():
                    if field_name == 'status':
                        if value in dict(Shipment.STATUS_CHOICES):  # Assuming you have STATUS_CHOICES
                            shipment.status = value
                        else:
                            errors.append(f'Invalid status value for shipment {shipment_id}')
                            continue

                    elif field_name == 'estimated_delivery_date':
                        if value:
                            try:
                                shipment.estimated_delivery_date = datetime.strptime(value, '%Y-%m-%d').date()
                            except ValueError:
                                errors.append(f'Invalid estimated delivery date for shipment {shipment_id}')
                                continue
                        else:
                            shipment.estimated_delivery_date = None

                    elif field_name == 'delivery_date':
                        if value:
                            try:
                                shipment.delivery_date = datetime.strptime(value, '%Y-%m-%d').date()
                            except ValueError:
                                errors.append(f'Invalid delivery date for shipment {shipment_id}')
                                continue
                        else:
                            shipment.delivery_date = None

                shipment.save()
                updated_count += 1

            except Shipment.DoesNotExist:
                errors.append(f'Shipment {shipment_id} not found')
            except Exception as e:
                errors.append(f'Error updating shipment {shipment_id}: {str(e)}')

        if errors:
            return JsonResponse({
                'success': False,
                'error': f'Some updates failed. {"; ".join(errors)}',
                'updated_count': updated_count
            })

        return JsonResponse({
            'success': True,
            'updated_count': updated_count,
            'message': f'Successfully updated {updated_count} shipments'
        })

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Server error: {str(e)}'})


@login_required
def download_shipment_report(request):
    user = request.user
    if user.is_superuser or user.is_staff:
        shipments = Shipment.objects.all().order_by('-date')
    else:
        shipments = Shipment.objects.filter(
            billto_customer=user.customer
        ).order_by('-date') if user.customer else Shipment.objects.none()

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="complete_shipment_report.csv"'

    writer = csv.writer(response)

    # Complete header row with ALL fields
    writer.writerow([
        'Consignment No', 'Date', 'Freight', 'Shipment Type', 'Shipment Mode', 'Payment Mode',
        'Vendor', 'Vehicle Type', 'Vehicle No', 'Origin', 'Origin Pin',
        'Destination', 'Destination Pin', 'Driver Details',
        'Bill To Customer', 'Consignor Name', 'Consignor Address', 'Consignor GST', 'Consignor Contact',
        'Consignee Name', 'Consignee Address', 'Consignee GST', 'Consignee Contact',
        'Invoice Ref No', 'SO Number', 'RO Number', 'BOE Number', 'E-waybill No', 'Additional Ref No',
        'Value', 'Pack Type', 'No. of Articles', 'Item Count', 'Actual Weight', 'Charged Weight',
        'Status', 'Estimated Delivery Date', 'Delivery Date',
        'Appointment Delivery', 'Appointment Date', 'Remarks', 'POD Scan URL'
    ])

    # Complete data rows with ALL fields
    for s in shipments:
        writer.writerow([
            s.consignment_no or '',
            s.date.strftime('%Y-%m-%d') if s.date else '',
            s.freight or 0,
            s.shipment_type or '',
            s.shipment_mode or '',
            s.payment_mode or '',
            str(s.vendor) if s.vendor else '',
            s.vehicle_type or '',
            s.vehicle_no or '',
            s.origin or '',
            s.origin_pin or '',
            s.destination or '',
            s.destination_pin or '',
            s.driver_details or '',
            str(s.billto_customer) if s.billto_customer else '',
            s.consignor_name or '',
            s.consignor_address or '',
            s.consignor_gst or '',
            s.consignor_contact or '',
            s.consignee_name or '',
            s.consignee_address or '',
            s.consignee_gst or '',
            s.consignee_contact or '',
            s.invoice_ref_number or '',
            s.so_number or '',
            s.ro_number or '',
            s.boe_num or '',
            s.ewaybill_number or '',
            s.additional_ref_number or '',
            s.value or 0,
            s.pack_type or '',
            s.no_article or 0,
            s.item_count or 0,
            s.actual_weight or 0,
            s.charged_weight or 0,
            s.status or '',
            s.estimated_delivery_date.strftime('%Y-%m-%d') if s.estimated_delivery_date else '',
            s.delivery_date.strftime('%Y-%m-%d') if s.delivery_date else '',
            'Yes' if s.appointment_delivery else 'No' if s.appointment_delivery is not None else '',
            s.appointment_date.strftime('%Y-%m-%d') if s.appointment_date else '',
            s.remark or '',
            s.pod_scan.url if getattr(s, 'pod_scan', None) else ''
        ])

    return response


def shipment_detail(request, pk):
    shipment = get_object_or_404(Shipment, pk=pk)
    return render(request, 'shipment_detail.html',
                  {'shipment': shipment, 'pagename': f'Shipment Detail of {shipment.consignment_no}'})


from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db import transaction
from decimal import Decimal
from .models import Shipment, Content
from .forms import ShipmentUpdateForm


def shipment_update(request, pk):
    shipment = get_object_or_404(Shipment, pk=pk)

    if request.method == 'POST':
        form = ShipmentUpdateForm(request.POST, request.FILES, instance=shipment)

        if form.is_valid():
            try:
                with transaction.atomic():
                    # Save the main shipment form
                    updated_shipment = form.save()

                    # Handle dimensions data
                    dimensions_data = extract_dimensions_from_request(request.POST)

                    if dimensions_data:
                        # Update content/dimensions
                        update_shipment_contents(updated_shipment, dimensions_data)

                        # Recalculate aggregated weights and dimensions
                        updated_shipment.update_weights_and_articles()

                        messages.success(request, f'Shipment {updated_shipment.consignment_no} updated successfully!')
                        return redirect('shipment_detail', pk=updated_shipment.pk)
                    else:
                        messages.error(request, 'At least one box/package dimension is required.')

            except Exception as e:
                messages.error(request, f'Error updating shipment: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ShipmentUpdateForm(instance=shipment)

    # Prepare context data
    context = {
        'form': form,
        'shipment': shipment,
        'existing_boxes_count': shipment.boxes.count() if shipment.boxes.exists() else 0,
        'existing_total_volume': calculate_total_volume(shipment.boxes.all()) if shipment.boxes.exists() else 0.0,
        'pagename': f'Update Shipment Details of {getattr(shipment, "consignment_no", "N/A")}',
    }

    return render(request, 'shipment_update.html', context)


def extract_dimensions_from_request(post_data):
    """Extract dimensions data from POST request"""
    dimensions = {}

    for key, value in post_data.items():
        if key.startswith('dimensions[') and '][' in key:
            # Parse dimension index and field name
            # Format: dimensions[0][box_length]
            try:
                start_idx = key.find('[') + 1
                end_idx = key.find(']')
                index = int(key[start_idx:end_idx])

                field_start = key.find('][') + 2
                field_end = key.rfind(']')
                field_name = key[field_start:field_end]

                if index not in dimensions:
                    dimensions[index] = {}

                dimensions[index][field_name] = value

            except (ValueError, IndexError):
                continue

    return dimensions


def update_shipment_contents(shipment, dimensions_data):
    """Update shipment content objects based on dimensions data"""

    # Get existing content IDs that should be preserved
    existing_ids = set()
    updated_ids = set()

    for index, dimension_data in dimensions_data.items():
        content_id = dimension_data.get('id')

        # Validate required fields
        required_fields = ['box_type', 'count_of_box', 'box_length', 'box_width', 'box_height', 'box_weight']
        if not all(dimension_data.get(field) for field in required_fields):
            continue

        try:
            # Convert numeric fields
            count_of_box = int(dimension_data.get('count_of_box', 1))
            box_length = Decimal(str(dimension_data.get('box_length', 0)))
            box_width = Decimal(str(dimension_data.get('box_width', 0)))
            box_height = Decimal(str(dimension_data.get('box_height', 0)))
            box_weight = Decimal(str(dimension_data.get('box_weight', 0)))

            # Prepare content data
            content_data = {
                'shipment': shipment,
                'box_type': dimension_data.get('box_type', ''),
                'count_of_box': count_of_box,
                'box_length': box_length,
                'box_width': box_width,
                'box_height': box_height,
                'box_weight': box_weight,
                'remark': dimension_data.get('remark', ''),
            }

            if content_id and content_id.isdigit():
                # Update existing content
                content_id = int(content_id)
                try:
                    content = Content.objects.get(id=content_id, shipment=shipment)
                    for key, value in content_data.items():
                        if key != 'shipment':  # Don't update shipment field
                            setattr(content, key, value)
                    content.save()
                    existing_ids.add(content_id)
                    updated_ids.add(content_id)
                except Content.DoesNotExist:
                    # Create new if not found
                    Content.objects.create(**content_data)
            else:
                # Create new content
                Content.objects.create(**content_data)

        except (ValueError, TypeError) as e:
            print(f"Error processing dimension data: {e}")
            continue

    # Delete content items that were not updated (removed from form)
    existing_contents = shipment.boxes.all()
    for content in existing_contents:
        if content.id not in updated_ids:
            content.delete()


def calculate_total_volume(contents_queryset):
    """Calculate total volume from contents queryset"""
    total = Decimal('0')
    for content in contents_queryset:
        if content.total_volumetric and content.count_of_box:
            total += content.total_volumetric * content.count_of_box
    return float(total)


# Alternative: If you prefer a more robust approach using Django formsets
from django.forms import modelformset_factory


def shipment_update_with_formset(request, pk):
    """Alternative implementation using Django formsets for better form handling"""
    shipment = get_object_or_404(Shipment, pk=pk)

    # Create formset for Content model
    ContentFormSet = modelformset_factory(
        Content,
        fields=('box_type', 'count_of_box', 'box_length', 'box_width', 'box_height', 'box_weight', 'remark'),
        extra=1,
        can_delete=True
    )

    if request.method == 'POST':
        form = ShipmentUpdateForm(request.POST, request.FILES, instance=shipment)
        formset = ContentFormSet(request.POST, queryset=shipment.boxes.all())

        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    # Save main shipment
                    updated_shipment = form.save()

                    # Save content formset
                    contents = formset.save(commit=False)

                    # Set shipment for new contents
                    for content in contents:
                        content.shipment = updated_shipment
                        content.save()

                    # Handle deletions
                    for content in formset.deleted_objects:
                        content.delete()

                    # Recalculate aggregates
                    updated_shipment.update_weights_and_articles()

                    messages.success(request, f'Shipment {updated_shipment.consignment_no} updated successfully!')
                    return redirect('shipment_detail', pk=updated_shipment.pk)

            except Exception as e:
                messages.error(request, f'Error updating shipment: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ShipmentUpdateForm(instance=shipment)
        formset = ContentFormSet(queryset=shipment.boxes.all())

    context = {
        'form': form,
        'formset': formset,
        'shipment': shipment,
        'existing_boxes_count': shipment.boxes.count(),
        'existing_total_volume': calculate_total_volume(shipment.boxes.all()),
    }

    return render(request, 'shipment_update.html', context)


def shipment_bulk_upload(request):
    if request.method == 'POST' and request.FILES.get('file'):
        file = request.FILES['file']
        ext = file.name.split('.')[-1].lower()
        try:
            if ext == 'csv':
                df = pd.read_csv(file)
            elif ext in ['xls', 'xlsx']:
                df = pd.read_excel(file)
            else:
                return HttpResponse("Unsupported file format", status=400)
        except Exception as e:
            return HttpResponse(f"Error reading file: {str(e)}", status=400)

        generated_data = []
        for index, row in df.iterrows():
            try:
                customer_id = str(row['billto_customer']).strip() if pd.notnull(row.get('billto_customer')) else None
                billto_customer = None
                if customer_id:
                    billto_customer = CustomerMaster.objects.filter(customer_id=customer_id).first()
                    if not billto_customer:
                        return HttpResponse(f"Row {index + 1} failed: Customer with ID '{customer_id}' not found",
                                            status=400)
                shipment = Shipment(
                    date=parse_date(str(row['date'])) if pd.notnull(row['date']) else None,
                    freight=float(row['freight']),
                    payment_mode=row['payment_mode'],
                    shipment_type=row['shipment_type'],
                    billto_customer=billto_customer,
                    origin=row['origin'],
                    origin_pin=str(row['origin_pin']),
                    destination=row['destination'],
                    destination_pin=str(row['destination_pin']),
                    vehicle_no=row['vehicle_no'],
                    driver_details=row['driver_details'],
                    consignor_name=row['consignor_name'],
                    consignor_address=row['consignor_address'],
                    consignor_gst=row.get('consignor_gst', ''),
                    consignor_contact=str(row['consignor_contact']),
                    consignee_name=row['consignee_name'],
                    consignee_address=row['consignee_address'],
                    consignee_gst=row.get('consignee_gst', ''),
                    consignee_contact=str(row['consignee_contact']),
                    invoice_ref_number=row['invoice_ref_number'],
                    ewaybill_number=row.get('ewaybill_number', ''),
                    value=float(row['value']),
                    no_article=int(row.get('no_article', 0)),
                    actual_weight=float(row.get('actual_weight', 0)),
                    charged_weight=float(row.get('charged_weight', 0)),
                    pack_type=row.get('pack_type', 'NA'),
                    status=row.get('status', 'Booked'),
                    estimated_delivery_date=parse_date(str(row.get('estimated_delivery_date'))) if pd.notnull(
                        row.get('estimated_delivery_date')) else None,
                    delivery_date=parse_date(str(row.get('delivery_date'))) if pd.notnull(
                        row.get('delivery_date')) else None
                )
                shipment.save()

                generated_data.append({
                    'invoice_ref_number': shipment.invoice_ref_number,
                    'consignment_no': shipment.consignment_no,
                    'date': shipment.date,
                    'origin': shipment.origin,
                    'destination': shipment.destination,
                    'freight': shipment.freight
                })
            except Exception as e:
                return HttpResponse(f"Row {index + 1} failed: {str(e)}", status=500)

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="uploaded_shipments.csv"'
        writer = csv.DictWriter(response,
                                fieldnames=['invoice_ref_number', 'consignment_no', 'date', 'origin', 'destination',
                                            'freight'])
        writer.writeheader()
        writer.writerows(generated_data)
        return response

    return render(request, 'shipment_bulk_upload.html', {'pagename': 'Bulk Upload'})


# ---------------------------
# Label, Notes, POD (Updated with QR Codes)
# ---------------------------

def print_label(request):
    return render(request, 'shipment_print_label.html', {'pagename': 'Print Labels'})


def download_labels(request):
    if request.method == 'POST':
        consignment_input = request.POST.get('consignments')
        consignment_numbers = consignment_input.strip().split()
        shipments = Shipment.objects.filter(consignment_no__in=consignment_numbers)

        buffer = BytesIO()
        width, height = 5 * inch, 4 * inch
        p = canvas.Canvas(buffer, pagesize=(width, height))

        for shipment in shipments:
            for i in range(shipment.no_article):
                y = height - 15 * mm
                p.setFont("Helvetica-Bold", 10)
                p.drawString(10 * mm, y, "FROM:")
                y -= 5 * mm
                p.setFont("Helvetica", 9)
                p.drawString(10 * mm, y, shipment.consignor_name)
                y -= 5 * mm
                p.drawString(10 * mm, y, shipment.consignor_address[:60])
                y -= 5 * mm
                p.drawString(10 * mm, y, f"Ph: {shipment.consignor_contact}")
                y -= 10 * mm
                p.setFont("Helvetica-Bold", 10)
                p.drawString(10 * mm, y, "TO:")
                y -= 5 * mm
                p.setFont("Helvetica", 9)
                p.drawString(10 * mm, y, shipment.consignee_name)
                y -= 5 * mm
                p.drawString(10 * mm, y, shipment.consignee_address[:60])
                y -= 5 * mm
                p.drawString(10 * mm, y, f"Ph: {shipment.consignee_contact}")
                y -= 10 * mm
                p.setFont("Helvetica", 9)
                p.drawString(10 * mm, y, f"Consignment No: {shipment.consignment_no}")
                y -= 5 * mm
                p.drawString(10 * mm, y, f"Package: {i + 1} of {shipment.no_article}")
                y -= 20 * mm

                # Use traditional barcode for labels (more space-efficient)
                barcode = code128.Code128(shipment.consignment_no, barHeight=15 * mm, barWidth=0.5)
                barcode.drawOn(p, 10 * mm, y)
                p.showPage()

        p.save()
        buffer.seek(0)
        return HttpResponse(buffer, content_type='application/pdf',
                            headers={'Content-Disposition': 'attachment; filename="shipment_labels.pdf"'})

    return HttpResponse("Only POST method allowed.")


def consignment_note(request):
    return render(request, 'consignment_notes.html', {'pagename': 'Download Consignment Notes'})


def generate_consignment_notes(request):
    consignment_nos = request.GET.get('consignments')
    if not consignment_nos:
        return HttpResponse("No consignment numbers provided.")

    consignment_nos = consignment_nos.strip().split()
    shipments = Shipment.objects.filter(consignment_no__in=consignment_nos)

    # Generate QR codes for each shipment
    tracking_base_url = request.build_absolute_uri('/').rstrip('/')
    for shipment in shipments:
        shipment.qr_code_data = generate_tracking_qr_code(
            shipment.consignment_no,
            tracking_base_url
        )

    context = {
        'shipments': shipments,
        'copy_labels': ['ORIGINAL COPY', 'DUPLICATE COPY', 'TRIPLICATE COPY']
    }
    template_path = 'consignment_notes_pdf.html'

    if request.GET.get('pdf') == 'yes':
        template = get_template(template_path)
        html = template.render(context)
        result = io.BytesIO()
        pdf = pisa.CreatePDF(io.BytesIO(html.encode("UTF-8")), dest=result)
        if pdf.err:
            return HttpResponse('PDF generation failed', status=500)
        response = HttpResponse(result.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="consignment_notes.pdf"'
        return response
    return render(request, template_path, context)


def generate_consignment_note_pdf(request, consignment_no):
    shipment = get_object_or_404(Shipment, consignment_no=consignment_no)

    # Generate QR code as base64 image
    tracking_base_url = request.build_absolute_uri('/').rstrip('/')
    qr_code_data = generate_tracking_qr_code(shipment.consignment_no, tracking_base_url)

    html = render_to_string('consignment_note_template.html', {
        'shipment': shipment,
        'logo_url': request.build_absolute_uri('/static/logo.png'),
        'qr_code_url': qr_code_data,
    })

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="consignment_note_{consignment_no}.pdf"'

    pisa_status = pisa.CreatePDF(io.BytesIO(html.encode('utf-8')), dest=response)

    if pisa_status.err:
        return HttpResponse("Error generating PDF", status=500)

    return response


# POD Uploads

def pod_upload_search(request):
    if request.method == 'POST':
        consignment_no = request.POST.get('consignment_no')
        try:
            shipment = Shipment.objects.get(consignment_no=consignment_no)
            return redirect('pod_upload', pk=shipment.pk)
        except Shipment.DoesNotExist:
            messages.error(request, 'Consignment not found.')
    return render(request, 'pod_upload_search.html', {'pagename': "POD Upload"})


def pod_upload(request, pk):
    shipment = get_object_or_404(Shipment, pk=pk)

    if request.method == 'POST':
        form = PODUploadForm(request.POST, request.FILES, instance=shipment)

        if form.is_valid():
            action = request.POST.get('action')

            if action == "full":
                shipment.status = "Delivered"
                form.save()
                messages.success(request, "POD uploaded and shipment marked as Delivered.")

            elif action == "partial":
                shipment.status = "Partial Delivered"
                form.save()
                messages.info(request, "Shipment marked as Partially Delivered.")

            shipment.save()
            return redirect('shipment_detail', pk=shipment.pk)

    else:
        form = PODUploadForm(instance=shipment)

    return render(request, 'pod_upload_form.html', {
        'form': form,
        'shipment': shipment,
        'pagename': "POD Upload",
    })


# ---------------------------
# Tracking (Enhanced with QR Codes)
# ---------------------------

def consignment_tracking(request):
    return render(request, 'consignment_tracking.html')


def bulk_tracking(request):
    consignment_nos = request.GET.get('consignments')
    shipments = Shipment.objects.filter(consignment_no__in=consignment_nos.strip().split()) if consignment_nos else []

    # Generate QR codes for tracking
    tracking_base_url = request.build_absolute_uri('/').rstrip('/')
    for shipment in shipments:
        shipment.tracking_qr_code = generate_tracking_qr_code(
            shipment.consignment_no,
            tracking_base_url
        )

    return render(request, 'bulk_tracking.html', {
        'shipments': shipments,
        'pagename': 'Bulk Consignment Tracking'
    })


def public_tracking(request):
    return render(request, 'public_tracking.html')


def public_tracking_status(request):
    consignment_nos = request.GET.get('consignments')
    shipments = Shipment.objects.filter(consignment_no__in=consignment_nos.strip().split()) if consignment_nos else []

    # Generate QR codes for public tracking
    tracking_base_url = request.build_absolute_uri('/').rstrip('/')
    for shipment in shipments:
        shipment.public_qr_code = generate_tracking_qr_code(
            shipment.consignment_no,
            tracking_base_url
        )

    return render(request, 'public_tracking.html', {'shipments': shipments})


# ---------------------------
# Manifest
# ---------------------------

def create_manifest(request):
    if request.method == 'POST':
        form = ManifestForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('manifest_list')
    else:
        form = ManifestForm()
    return render(request, 'manifest_create.html', {'form': form, 'pagename': 'Create Manifest'})


def manifest_detail(request, pk):
    manifest = get_object_or_404(Manifest, pk=pk)
    shipments = manifest.shipments.all()
    total_articles = sum(s.no_article for s in shipments)
    total_freight = sum(s.freight for s in shipments)
    return render(request, 'manifest_detail.html', {
        'manifest': manifest,
        'total_articles': total_articles,
        'total_freight': total_freight
    })


def manifest_pdf(request, pk):
    manifest = Manifest.objects.get(pk=pk)
    template_path = 'manifest/manifest_pdf_template.html'
    context = {'manifest': manifest, 'shipments': manifest.shipments.all()}
    template = get_template(template_path)
    html = template.render(context)
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="manifest_{manifest.manifest_id}.pdf"'
    pisa_status = pisa.CreatePDF(html, dest=response)
    if pisa_status.err:
        return HttpResponse('PDF generation failed.')
    return response


def manifest_list(request):
    manifests = Manifest.objects.all().order_by('-created_at')
    return render(request, 'manifest_list.html', {'manifests': manifests, 'pagename': 'Manifest List'})


def print_manifest_list(request):
    manifests = Manifest.objects.all()
    return render(request, 'print_manifest_list.html', {'manifests': manifests})


# ---------------------------
# Users
# ---------------------------

def user_add(request):
    return render(request, 'users/user_add.html')


def user_manage(request):
    return render(request, 'users/user_manage.html')


# ---------------------------
# Branches / Fleets / Vendors
# ---------------------------

def branch_add(request):
    return render(request, 'main/branch_add.html')


def branch_manage(request):
    return render(request, 'main/branch_manage.html')


def fleet_add(request):
    return render(request, 'main/fleet_add.html')


def fleet_manage(request):
    return render(request, 'main/fleet_manage.html')


def create_vendor(request):
    if request.method == "POST":
        form = VendorMasterForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Vendor created successfully ✅")
            return redirect("vendor-list")  # make sure to define this route or change as needed
    else:
        form = VendorMasterForm()
    return render(request, "vendor_form.html", {"form": form})


# ---------------------------
# Trips
# ---------------------------

def create_trip(request):
    if request.method == "POST":
        form = TripOutToVendorForm(request.POST)
        if form.is_valid():
            trip = form.save(commit=False)
            # Auto-calculate total bill amount if missing
            if not trip.total_bill_amount:
                trip.total_bill_amount = trip.trip_charge + trip.additional_charge
            trip.save()
            messages.success(request, f"Trip {trip.trip_id} created successfully ✅")
            return redirect("trip-list")
        else:
            messages.error(request, "⚠️ Please correct the errors below.")
    else:
        form = TripOutToVendorForm()
    return render(request, "trip_form.html", {"form": form, 'pagename': 'Create Trip'})


def trip_list(request):
    trips = TripOutToVendor.objects.all()
    status = request.GET.get("status")
    trip_id = request.GET.get("trip_id")

    if status:
        trips = trips.filter(status=status)
    if trip_id:
        trips = trips.filter(trip_id__icontains=trip_id)

    return render(request, "trip_list.html", {"trips": trips, 'pagename': 'Trip List'})


def update_trip_status(request, pk):
    trip = get_object_or_404(TripOutToVendor, pk=pk)
    if request.method == "POST":
        new_status = request.POST.get("status")
        if new_status in dict(TripOutToVendor.STATUS_CHOICES):
            trip.status = new_status
            trip.save()
            messages.success(request, f"Trip {trip.trip_id} status updated to {new_status}")
    return redirect("trip-list")


def trip_detail(request, pk):
    trip = get_object_or_404(TripOutToVendor, pk=pk)
    return render(request, "trip_detail.html", {"trip": trip, 'pagename': 'Trip Details'})


def trip_update(request, pk):
    trip = get_object_or_404(TripOutToVendor, pk=pk)
    if request.method == "POST":
        form = TripOutToVendorForm(request.POST, instance=trip)
        if form.is_valid():
            form.save()
            messages.success(request, f"Trip {trip.trip_id} updated successfully ✅")
            return redirect("trip-list")
    else:
        form = TripOutToVendorForm(instance=trip)
    return render(request, "trip_update.html", {"form": form, "trip": trip, 'pagename': 'Trip Update'})
