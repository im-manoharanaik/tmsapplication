import csv
import io
import json
import base64
import logging
from decimal import Decimal
from io import BytesIO
from datetime import datetime, timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q, Count
from django.forms import modelformset_factory
from django.http import JsonResponse, HttpResponse
from django.template.loader import get_template
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

import pandas as pd
import qrcode
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A6
from reportlab.lib.units import inch, mm
from reportlab.graphics.barcode import code128
from xhtml2pdf import pisa
import barcode
from barcode.writer import ImageWriter

from .models import Shipment, Manifest, Content, CustomerMaster, TripOutToVendor
from .forms import (
    ShipmentForm, ShipmentUpdateForm, ManifestForm, CustomUserCreationForm,
    PODUploadForm, ContentForm, ContentFormSet, VendorMasterForm, TripOutToVendorForm
)

logger = logging.getLogger(__name__)


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
        logger.error(f"QR code generation error: {e}")
        return None

def generate_barcode_base64(value: str) -> str | None:
    """
    Generate Code128 barcode PNG for 'value' and return as data URI.
    Returns None if generation fails.
    """
    try:
        code128 = barcode.get_barcode_class('code128')
        bar = code128(str(value), writer=ImageWriter())
        buf = BytesIO()
        # Tuned for print clarity; adjust if needed
        bar.write(
            buf,
            options={
                "module_width": 0.45,   # bar width
                "module_height": 14,    # bar height
                "font_size": 8,         # text under bars
                "text_distance": 1,     # gap between bars and text
                "quiet_zone": 2,        # side padding
            }
        )
        data = buf.getvalue()
        buf.close()
        return "data:image/png;base64," + base64.b64encode(data).decode("utf-8")
    except Exception:
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
        logger.error(f"QR code URL generation error: {e}")
        return HttpResponse(status=404)


def generate_tracking_qr_code(consignment_no, tracking_url_base=None):
    """Generate QR code with full tracking URL for better user experience"""
    try:
        if tracking_url_base:
            tracking_data = f"{tracking_url_base}/track/{consignment_no}"
        else:
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
        logger.error(f"Tracking QR code generation error: {e}")
        return None


# ---------------------------
# Auth & Basic Pages
# ---------------------------

def main(request):
    """Main landing page"""
    return render(request, 'main.html')


def register_user(request):
    """User registration view"""
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
    """User logout view"""
    logout(request)
    return redirect(reverse('login'))


def user_login(request):
    """User login view"""
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)

        if user:
            if hasattr(user, 'user_status') and user.user_status == 'Active':
                login(request, user)
                return redirect('dashboard')
            messages.error(request, 'Your account is inactive. Please contact admin.')
        else:
            messages.error(request, 'Invalid username or password.')

    return render(request, 'main.html')


# ---------------------------
# Dashboard & Statistics
# ---------------------------

@login_required
def dashboard(request):
    """Enhanced dashboard with real-time statistics and data"""
    today = timezone.now().date()
    current_month = today.replace(day=1)
    last_month = (current_month - timedelta(days=1)).replace(day=1)

    # Calculate shipment statistics
    shipment_stats = get_shipment_statistics(current_month, last_month)

    # Get recent shipments for quick access
    recent_shipments = Shipment.objects.order_by('-date', '-id')[:5]

    # Calculate fleet utilization
    fleet_utilization = calculate_fleet_utilization()

    # Get user-specific data
    user_permissions = get_user_permissions(request.user)
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
        date__gte=current_month, status__iexact='delivered'
    ).count()
    current_transit = Shipment.objects.filter(
        date__gte=current_month, status__iexact='in-transit'
    ).count()
    current_pending = Shipment.objects.filter(
        date__gte=current_month, status__iexact='booked'
    ).count()

    # Last month stats for comparison
    last_total = Shipment.objects.filter(
        date__gte=last_month, date__lt=current_month
    ).count()
    last_delivered = Shipment.objects.filter(
        date__gte=last_month, date__lt=current_month, status__iexact='delivered'
    ).count()
    last_transit = Shipment.objects.filter(
        date__gte=last_month, date__lt=current_month, status__iexact='in-transit'
    ).count()
    last_pending = Shipment.objects.filter(
        date__gte=last_month, date__lt=current_month, status__iexact='booked'
    ).count()

    def calculate_change(current, previous):
        """Calculate percentage change"""
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
    total_vehicles = 50  # Replace with actual count from fleet model
    active_shipments = Shipment.objects.filter(
        Q(status__iexact='in-transit') | Q(status__iexact='booked')
    ).count()

    utilization = min(100, round((active_shipments / total_vehicles) * 100, 1)) if total_vehicles > 0 else 0

    return {
        'rate': utilization,
        'active_vehicles': min(active_shipments, total_vehicles),
        'total_vehicles': total_vehicles
    }


def get_user_permissions(user):
    """Get user-specific permissions and access levels"""
    is_internal = hasattr(user, 'usertype') and user.usertype == 'Internal'

    return {
        'can_create_shipment': is_internal,
        'can_manage_masters': is_internal,
        'can_create_manifest': is_internal,
        'can_upload_pod': is_internal,
        'can_bulk_upload': is_internal,
        'can_view_billing': is_internal,
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
# Customer Management
# ---------------------------

def customer_autocomplete(request):
    """AJAX endpoint for customer name autocomplete"""
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
        )[:10]

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
    """Get detailed customer information by ID"""
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


# ---------------------------
# FIXED: Content Data Extraction Functions
# ---------------------------

def extract_content_from_request(post_data):
    """Extract content data from POST request - FIXED VERSION"""
    content_items = []
    i = 0

    print(f"\n=== EXTRACTING CONTENT DATA ===")
    print(f"POST data keys: {list(post_data.keys())}")

    # Look for content[i] data (matching template)
    while f'content[{i}][count_of_box]' in post_data:
        try:
            # Get raw values
            raw_data = {
                'count_of_box': post_data.get(f'content[{i}][count_of_box]', '0'),
                'box_weight': post_data.get(f'content[{i}][box_weight]', '0.00'),
                'box_length': post_data.get(f'content[{i}][box_length]', '0.00'),
                'box_width': post_data.get(f'content[{i}][box_width]', '0.00'),
                'box_height': post_data.get(f'content[{i}][box_height]', '0.00'),
                'id': post_data.get(f'content[{i}][id]', None),  # For updates
            }

            print(f"Raw data for content[{i}]: {raw_data}")

            # Convert and validate
            content_data = {
                'count_of_box': int(raw_data['count_of_box']) if raw_data['count_of_box'] and raw_data[
                    'count_of_box'] != '' else 0,
                'box_weight': float(raw_data['box_weight']) if raw_data['box_weight'] and raw_data[
                    'box_weight'] != '' else 0.0,
                'box_length': float(raw_data['box_length']) if raw_data['box_length'] and raw_data[
                    'box_length'] != '' else 0.0,
                'box_width': float(raw_data['box_width']) if raw_data['box_width'] and raw_data[
                    'box_width'] != '' else 0.0,
                'box_height': float(raw_data['box_height']) if raw_data['box_height'] and raw_data[
                    'box_height'] != '' else 0.0,
                'id': raw_data['id'] if raw_data['id'] and raw_data['id'] != '' else None,
            }

            print(f"Converted data for content[{i}]: {content_data}")

            # Validate - all values must be positive
            if (content_data['count_of_box'] > 0 and
                    content_data['box_weight'] > 0 and
                    content_data['box_length'] > 0 and
                    content_data['box_width'] > 0 and
                    content_data['box_height'] > 0):

                content_items.append(content_data)
                print(f"✅ Valid content item {i}: {content_data}")
            else:
                print(f"❌ Invalid content data at index {i}: {content_data}")

        except (ValueError, TypeError) as e:
            print(f'❌ Error parsing content data at index {i}: {e}')
            continue

        i += 1

    print(f"=== EXTRACTION COMPLETE ===")
    print(f"Total valid content items extracted: {len(content_items)}")
    return content_items


def create_content_from_data(shipment, content_data):
    """Create Content object from content data - FIXED VERSION"""
    try:
        print(f"\n=== CREATING CONTENT ITEM ===")
        print(f"Shipment: {shipment.consignment_no} (ID: {shipment.id})")
        print(f"Content data: {content_data}")

        # Create content item WITHOUT total_volumetric (it's now a property)
        content_item = Content.objects.create(
            shipment=shipment,
            count_of_box=content_data['count_of_box'],
            box_weight=Decimal(str(content_data['box_weight'])),
            box_length=Decimal(str(content_data['box_length'])),
            box_width=Decimal(str(content_data['box_width'])),
            box_height=Decimal(str(content_data['box_height'])),
        )

        print(f"✅ Content item created successfully:")
        print(f"   - ID: {content_item.id}")
        print(f"   - Batch ID: {content_item.batch_id}")
        print(f"   - Count: {content_item.count_of_box}")
        print(f"   - Weight: {content_item.box_weight}")
        print(f"   - Dimensions: {content_item.box_length}×{content_item.box_width}×{content_item.box_height}")
        print(f"   - Volume (property): {content_item.total_volumetric}")

        return True

    except Exception as e:
        print(f"❌ Error creating content item: {e}")
        print(f"   - Exception type: {type(e)}")
        logger.error(f"Error creating content from data: {e}")
        return False


# ---------------------------
# FIXED: Shipment Management
# ---------------------------

@transaction.atomic
def shipment_create(request):
    """Create new shipment with content items - FIXED VERSION"""
    print(f"\n=== SHIPMENT CREATE REQUEST ===")
    print(f"Method: {request.method}")

    if request.method == 'POST':
        print(f"POST data received")

        form = ShipmentForm(request.POST)

        # Extract content data from POST data
        content_data = extract_content_from_request(request.POST)

        print(f"Final extracted content data: {content_data}")

        if form.is_valid():
            print(f"✅ Form is valid")

            # Validate content data exists
            if not content_data:
                print(f"❌ No content data found!")
                messages.error(request, 'No content items were provided. Please add at least one content item.')
                return render(request, 'shipment_create.html', {'form': form})

            # Save shipment first
            shipment = form.save(commit=False)

            # Set customer if user has one
            if hasattr(request.user, 'customer'):
                shipment.billto_customer = request.user.customer
                print(f"Set customer: {request.user.customer}")

            shipment.save()
            print(f"✅ Shipment created: {shipment.consignment_no} (ID: {shipment.id})")
            print(f"   - Total Quantity (manual): {shipment.total_quantity}")

            # Create Content entries
            created_count = 0
            failed_count = 0

            for i, content in enumerate(content_data):
                print(f"\n--- Processing content item {i + 1} ---")
                if create_content_from_data(shipment, content):
                    created_count += 1
                    print(f"✅ Content item {i + 1} created successfully")
                else:
                    failed_count += 1
                    print(f"❌ Content item {i + 1} failed to create")

            print(f"\n=== CONTENT CREATION SUMMARY ===")
            print(f"Total items processed: {len(content_data)}")
            print(f"Successfully created: {created_count}")
            print(f"Failed to create: {failed_count}")

            if created_count == 0:
                print(f"❌ No content items were created!")
                messages.error(request, 'Failed to create content items. Please check your input data.')
                return render(request, 'shipment_create.html', {'form': form})

            # Update calculated fields after all content is created
            if hasattr(shipment, 'update_calculated_fields'):
                print(f"Updating calculated fields...")
                shipment.update_calculated_fields()

                # Reload shipment to get updated values
                shipment.refresh_from_db()
                print(f"Updated shipment fields:")
                print(f"   - No of articles: {shipment.no_article}")
                print(f"   - Actual weight: {shipment.actual_weight}")
                print(f"   - Total Quantity (manual): {shipment.total_quantity}")

            success_msg = f'Shipment {shipment.consignment_no} created successfully with {created_count} content items!'
            if failed_count > 0:
                success_msg += f' ({failed_count} items failed to create)'

            messages.success(request, success_msg)
            print(f"✅ {success_msg}")

            return redirect('shipment_detail', pk=shipment.pk)

        else:
            print(f"❌ Form is not valid")
            print(f"Form errors: {form.errors}")

            # Also check if content data was extracted
            if not content_data:
                print(f"❌ No content data extracted from form")
                messages.error(request, 'Please add at least one content item with valid dimensions.')

            messages.error(request, 'Please correct the errors below.')

    else:
        print(f"GET request - rendering empty form")
        form = ShipmentForm()

    return render(request, 'shipment_create.html', {'form': form,'pagename':'Create Shipment'})


@transaction.atomic
def shipment_update(request, pk):
    """Update shipment and its content items - FIXED VERSION"""
    shipment = get_object_or_404(Shipment, pk=pk)

    print(f"\n=== SHIPMENT UPDATE REQUEST ===")
    print(f"Shipment: {shipment.consignment_no} (ID: {shipment.id})")
    print(f"Current Total Quantity (manual): {shipment.total_quantity}")
    print(f"Method: {request.method}")

    if request.method == 'POST':
        form = ShipmentUpdateForm(request.POST, request.FILES, instance=shipment)

        if form.is_valid():
            try:
                print(f"✅ Form is valid")

                # Extract content data from POST
                content_data = extract_content_from_request(request.POST)
                print(f"Update - Extracted content data: {content_data}")

                # Save the shipment first (total_quantity will be updated from form automatically)
                updated_shipment = form.save()
                print(f"✅ Shipment updated: {updated_shipment.consignment_no}")
                print(f"   - Updated Total Quantity (manual): {updated_shipment.total_quantity}")

                # Handle content items
                processed_content_ids = []
                created_count = 0
                updated_count = 0

                for item_data in content_data:
                    try:
                        content_id = item_data.get('id')

                        if content_id and str(content_id).isdigit():
                            # Update existing content item
                            try:
                                content_item = Content.objects.get(
                                    id=int(content_id),
                                    shipment=updated_shipment
                                )
                                content_item.count_of_box = item_data['count_of_box']
                                content_item.box_weight = Decimal(str(item_data['box_weight']))
                                content_item.box_length = Decimal(str(item_data['box_length']))
                                content_item.box_width = Decimal(str(item_data['box_width']))
                                content_item.box_height = Decimal(str(item_data['box_height']))
                                content_item.save()

                                processed_content_ids.append(content_item.id)
                                updated_count += 1
                                print(f"✅ Updated existing content item: {content_item.id}")

                            except Content.DoesNotExist:
                                print(f"❌ Content item with ID {content_id} not found, creating new one")
                                # Create new if not found
                                if create_content_from_data(updated_shipment, item_data):
                                    created_count += 1
                                    # Get the last created content item ID
                                    last_content = Content.objects.filter(shipment=updated_shipment).order_by(
                                        '-id').first()
                                    if last_content:
                                        processed_content_ids.append(last_content.id)
                        else:
                            # Create new content item
                            if create_content_from_data(updated_shipment, item_data):
                                created_count += 1
                                # Get the last created content item ID
                                last_content = Content.objects.filter(shipment=updated_shipment).order_by('-id').first()
                                if last_content:
                                    processed_content_ids.append(last_content.id)

                    except Exception as e:
                        print(f"❌ Error processing content item: {e}")
                        continue

                # Delete content items that are no longer in the form
                existing_content_items = Content.objects.filter(shipment=updated_shipment)
                items_to_delete = existing_content_items.exclude(id__in=processed_content_ids)
                deleted_count = items_to_delete.count()
                items_to_delete.delete()

                print(f"\n=== UPDATE SUMMARY ===")
                print(f"Content items created: {created_count}")
                print(f"Content items updated: {updated_count}")
                print(f"Content items deleted: {deleted_count}")

                # Update calculated fields
                if hasattr(updated_shipment, 'update_calculated_fields'):
                    print(f"Updating calculated fields...")
                    updated_shipment.update_calculated_fields()

                    # Reload to get final values
                    updated_shipment.refresh_from_db()
                    print(f"Final shipment values:")
                    print(f"   - No of articles: {updated_shipment.no_article}")
                    print(f"   - Actual weight: {updated_shipment.actual_weight}")
                    print(f"   - Total Quantity (manual): {updated_shipment.total_quantity}")

                success_msg = f'Shipment {updated_shipment.consignment_no} updated successfully! '
                if created_count > 0:
                    success_msg += f'{created_count} new content items created, '
                if updated_count > 0:
                    success_msg += f'{updated_count} content items updated, '
                if deleted_count > 0:
                    success_msg += f'{deleted_count} content items removed.'

                messages.success(request, success_msg)
                return redirect('shipment_detail', pk=updated_shipment.pk)

            except Exception as e:
                messages.error(request, f'Error updating shipment: {str(e)}')
                print(f"❌ Error in shipment update: {e}")

        else:
            print(f"❌ Form is not valid")
            print(f"Form errors: {form.errors}")

    else:
        form = ShipmentUpdateForm(instance=shipment)

    # Get content items for display
    content_items = Content.objects.filter(shipment=shipment).order_by('batch_id', 'id')

    # Debug: Print content items to console
    print(f"\nShipment ID: {shipment.id}")
    print(f"Content items count: {content_items.count()}")
    print(f"Total Quantity (manual): {shipment.total_quantity}")
    for content in content_items:
        print(f"Content ID: {content.id}, Batch: {content.batch_id}, Count: {content.count_of_box}")

    context = {
        'form': form,
        'shipment': shipment,
        'content_items': content_items,
        'debug': True,  # Enable debug info in template
        'pagename': f'Update Shipment - {shipment.consignment_no}'
    }

    return render(request, 'shipment_update.html', context)



from django.core.paginator import Paginator
from django.db.models import Q

def shipment_list(request):
    # Base queryset
    shipments = Shipment.objects.all().order_by('-date')

    # Date filters
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    if start_date:
        shipments = shipments.filter(date__gte=start_date)
    if end_date:
        shipments = shipments.filter(date__lte=end_date)

    # Text filters (case-insensitive partial match)
    consignment_no = request.GET.get('consignment_no', '').strip()
    if consignment_no:
        shipments = shipments.filter(consignment_no__icontains=consignment_no)

    consignor = request.GET.get('consignor', '').strip()
    if consignor:
        shipments = shipments.filter(consignor_name__icontains=consignor)

    origin = request.GET.get('origin', '').strip()
    if origin:
        shipments = shipments.filter(origin__icontains=origin)

    consignee = request.GET.get('consignee', '').strip()
    if consignee:
        shipments = shipments.filter(consignee_name__icontains=consignee)

    destination = request.GET.get('destination', '').strip()
    if destination:
        shipments = shipments.filter(destination__icontains=destination)

    vehicle_no = request.GET.get('vehicle_no', '').strip()
    if vehicle_no:
        shipments = shipments.filter(vehicle_no__icontains=vehicle_no)

    status = request.GET.get('status', '').strip()
    if status:
        shipments = shipments.filter(status=status)

    # Pagination (25 per page)
    paginator = Paginator(shipments, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'shipments': page_obj.object_list,  # for backward compatibility
        'start_date': start_date,
        'end_date': end_date,
    }
    return render(request, 'shipment_list.html', context)

def shipment_detail(request, pk):
    """Show shipment detail"""
    shipment = get_object_or_404(Shipment, pk=pk)
    return render(request, 'shipment_detail.html', {
        'shipment': shipment,
        'pagename': f'Shipment Detail of {shipment.consignment_no}'
    })


def search_consignment(request):
    """Search consignment page"""
    return render(request, 'search_consignment.html', {'pagename': 'Search Consignment'})


# ---------------------------
# Legacy Functions (Kept for compatibility)
# ---------------------------

def extract_dimensions_from_request(post_data):
    """Legacy function - redirects to extract_content_from_request for compatibility"""
    return extract_content_from_request(post_data)


def create_content_from_dimension(shipment, dimension):
    """Legacy function - redirects to create_content_from_data for compatibility"""
    return create_content_from_data(shipment, dimension)

# ---------------------------
# Bulk Operations & Reports
# ---------------------------

@login_required
@require_http_methods(["POST"])
def bulk_update_shipments(request):
    """Handle bulk updates for shipment fields via AJAX"""
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
                        # Validate status if STATUS_CHOICES exists
                        shipment.status = value

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
    """Download complete shipment report as CSV with date filtering"""
    user = request.user

    # Get date filters from request
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    consignment_no = request.GET.get('consignment_no')

    # Base queryset based on user permissions
    if user.is_superuser or user.is_staff:
        shipments = Shipment.objects.all()
    else:
        shipments = Shipment.objects.filter(
            billto_customer=getattr(user, 'customer', None)
        ) if hasattr(user, 'customer') and user.customer else Shipment.objects.none()

    # Apply date filters
    if start_date:
        try:
            start_date_parsed = datetime.strptime(start_date, '%Y-%m-%d').date()
            shipments = shipments.filter(date__gte=start_date_parsed)
        except ValueError:
            pass  # Invalid date format, ignore

    if end_date:
        try:
            end_date_parsed = datetime.strptime(end_date, '%Y-%m-%d').date()
            shipments = shipments.filter(date__lte=end_date_parsed)
        except ValueError:
            pass  # Invalid date format, ignore

    # Apply consignment number filter
    if consignment_no:
        shipments = shipments.filter(consignment_no__icontains=consignment_no)

    # Order by date
    shipments = shipments.order_by('-date')

    # Generate filename with date range
    filename_parts = ['shipment_report']
    if start_date:
        filename_parts.append(f'from_{start_date}')
    if end_date:
        filename_parts.append(f'to_{end_date}')
    if consignment_no:
        filename_parts.append(f'consignment_{consignment_no}')
    filename = '_'.join(filename_parts) + '.csv'

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)

    # Complete header row with additional fields
    writer.writerow([
        'Consignment No', 'Date', 'Freight', 'Shipment Type', 'Shipment Mode', 'Payment Mode',
        'Vendor', 'Vehicle Type', 'Vehicle No', 'Origin', 'Origin Pin',
        'Destination', 'Destination Pin', 'Driver Details',
        'Bill To Customer', 'Consignor Name', 'Consignor Address', 'Consignor GST', 'Consignor Contact',
        'Consignee Name', 'Consignee Address', 'Consignee GST', 'Consignee Contact',
        'Invoice Ref No', 'SO Number', 'RO Number', 'BOE Number', 'E-waybill No', 'Additional Ref No',
        'Value', 'Pack Type', 'Total Quantity (Manual)', 'No. of Articles (Auto)', 'Actual Weight (Auto)',
        'Charged Weight (Auto)',
        'Total Volume (Auto)', 'Status', 'Pickup Date', 'Estimated Delivery Date', 'Delivery Date',
        'Appointment Delivery', 'Appointment Date', 'Remarks', 'POD Scan URL', 'Created At', 'Updated At'
    ])

    # Complete data rows
    for s in shipments:
        writer.writerow([
            getattr(s, 'consignment_no', '') or '',
            s.date.strftime('%Y-%m-%d') if s.date else '',
            getattr(s, 'freight', 0) or 0,
            getattr(s, 'shipment_type', '') or '',
            getattr(s, 'shipment_mode', '') or '',
            getattr(s, 'payment_mode', '') or '',
            str(getattr(s, 'vendor', '')) or '',
            getattr(s, 'vehicle_type', '') or '',
            getattr(s, 'vehicle_no', '') or '',
            getattr(s, 'origin', '') or '',
            getattr(s, 'origin_pin', '') or '',
            getattr(s, 'destination', '') or '',
            getattr(s, 'destination_pin', '') or '',
            getattr(s, 'driver_details', '') or '',
            str(getattr(s, 'billto_customer', '')) or '',
            getattr(s, 'consignor_name', '') or '',
            getattr(s, 'consignor_address', '') or '',
            getattr(s, 'consignor_gst', '') or '',
            getattr(s, 'consignor_contact', '') or '',
            getattr(s, 'consignee_name', '') or '',
            getattr(s, 'consignee_address', '') or '',
            getattr(s, 'consignee_gst', '') or '',
            getattr(s, 'consignee_contact', '') or '',
            getattr(s, 'invoice_ref_number', '') or '',
            getattr(s, 'so_number', '') or '',
            getattr(s, 'ro_number', '') or '',
            getattr(s, 'boe_num', '') or '',
            getattr(s, 'ewaybill_number', '') or '',
            getattr(s, 'additional_ref_number', '') or '',
            getattr(s, 'value', 0) or 0,
            getattr(s, 'pack_type', '') or '',
            getattr(s, 'total_quantity', 0) or 0,  # Manual entry field
            getattr(s, 'no_article', 0) or 0,  # Auto-calculated
            getattr(s, 'actual_weight', 0) or 0,  # Auto-calculated
            getattr(s, 'charged_weight', 0) or 0,  # Auto-calculated
            s.total_volume if hasattr(s, 'total_volume') else 0,  # Auto-calculated property
            getattr(s, 'status', '') or '',
            s.pickedup_date.strftime('%Y-%m-%d') if getattr(s, 'pickedup_date', None) else '',
            s.estimated_delivery_date.strftime('%Y-%m-%d') if getattr(s, 'estimated_delivery_date', None) else '',
            s.delivery_date.strftime('%Y-%m-%d') if getattr(s, 'delivery_date', None) else '',
            'Yes' if getattr(s, 'appointment_delivery', None) else 'No' if getattr(s, 'appointment_delivery',
                                                                                   None) is not None else '',
            s.appointment_date.strftime('%Y-%m-%d') if getattr(s, 'appointment_date', None) else '',
            getattr(s, 'remark', '') or '',
            s.pod_scan.url if getattr(s, 'pod_scan', None) else '',
            s.created_at.strftime('%Y-%m-%d %H:%M:%S') if getattr(s, 'created_at', None) else '',
            s.updated_at.strftime('%Y-%m-%d %H:%M:%S') if getattr(s, 'updated_at', None) else ''
        ])

    return response


def shipment_bulk_upload(request):
    """Bulk upload shipments from CSV/Excel"""
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
                # Process customer lookup
                customer_id = str(row['billto_customer']).strip() if pd.notnull(row.get('billto_customer')) else None
                billto_customer = None
                if customer_id:
                    billto_customer = CustomerMaster.objects.filter(customer_id=customer_id).first()
                    if not billto_customer:
                        return HttpResponse(
                            f"Row {index + 1} failed: Customer with ID '{customer_id}' not found",
                            status=400
                        )

                # Create shipment
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

        # Return CSV with generated data
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="uploaded_shipments.csv"'
        writer = csv.DictWriter(response, fieldnames=[
            'invoice_ref_number', 'consignment_no', 'date', 'origin', 'destination', 'freight'
        ])
        writer.writeheader()
        writer.writerows(generated_data)
        return response

    return render(request, 'shipment_bulk_upload.html', {'pagename': 'Bulk Upload'})


# ---------------------------
# Content Management
# ---------------------------

def update_content(request, consignment_no):
    """Update content/boxes for a shipment"""
    shipment = get_object_or_404(Shipment, consignment_no=consignment_no)

    if hasattr(shipment, 'boxes'):
        queryset = shipment.boxes.all()
    else:
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

            # Save instances
            for instance in instances:
                if not instance.pk:
                    instance.shipment = shipment
                instance.save()

            # Delete removed objects
            for obj in formset.deleted_objects:
                obj.delete()

            # Recalculate shipment summary fields
            if hasattr(shipment, 'update_weights_and_articles'):
                shipment.update_weights_and_articles()
            elif hasattr(shipment, 'update_calculated_fields'):
                shipment.update_calculated_fields()

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


# Keep all remaining functions exactly as they were in your original file...
# (POD functions, tracking functions, manifest functions, etc.)

# ---------------------------
# Label, Notes, POD (Updated with QR Codes)
# ---------------------------

def print_label(request):
    """Print labels page"""
    return render(request, 'shipment_print_label.html', {'pagename': 'Print Labels'})


def download_labels(request):
    """Generate and download shipping labels"""
    if request.method == 'POST':
        consignment_input = request.POST.get('consignments')
        consignment_numbers = consignment_input.strip().split()
        shipments = Shipment.objects.filter(consignment_no__in=consignment_numbers)

        buffer = BytesIO()
        width, height = 5 * inch, 4 * inch
        p = canvas.Canvas(buffer, pagesize=(width, height))

        for shipment in shipments:
            for i in range(getattr(shipment, 'no_article', 1)):
                y = height - 15 * mm
                p.setFont("Helvetica-Bold", 10)
                p.drawString(10 * mm, y, "FROM:")
                y -= 5 * mm
                p.setFont("Helvetica", 9)
                p.drawString(10 * mm, y, getattr(shipment, 'consignor_name', ''))
                y -= 5 * mm
                p.drawString(10 * mm, y, getattr(shipment, 'consignor_address', '')[:60])
                y -= 5 * mm
                p.drawString(10 * mm, y, f"Ph: {getattr(shipment, 'consignor_contact', '')}")
                y -= 10 * mm
                p.setFont("Helvetica-Bold", 10)
                p.drawString(10 * mm, y, "TO:")
                y -= 5 * mm
                p.setFont("Helvetica", 9)
                p.drawString(10 * mm, y, getattr(shipment, 'consignee_name', ''))
                y -= 5 * mm
                p.drawString(10 * mm, y, getattr(shipment, 'consignee_address', '')[:60])
                y -= 5 * mm
                p.drawString(10 * mm, y, f"Ph: {getattr(shipment, 'consignee_contact', '')}")
                y -= 10 * mm
                p.setFont("Helvetica", 9)
                p.drawString(10 * mm, y, f"Consignment No: {shipment.consignment_no}")
                y -= 5 * mm
                p.drawString(10 * mm, y, f"Package: {i + 1} of {getattr(shipment, 'no_article', 1)}")
                y -= 20 * mm

                # Add barcode
                try:
                    barcode = code128.Code128(shipment.consignment_no, barHeight=15 * mm, barWidth=0.5)
                    barcode.drawOn(p, 10 * mm, y)
                except Exception as e:
                    logger.error(f"Error generating barcode: {e}")

                p.showPage()

        p.save()
        buffer.seek(0)
        return HttpResponse(buffer, content_type='application/pdf',
                            headers={'Content-Disposition': 'attachment; filename="shipment_labels.pdf"'})

    return HttpResponse("Only POST method allowed.")


def consignment_note(request):
    """Consignment notes page"""
    return render(request, 'consignment_notes.html', {'pagename': 'Download Consignment Notes'})


def generate_consignment_notes(request):
    """Generate consignment notes with QR codes"""
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
        'copy_labels': ['CONSIGNOR COPY', 'CONSIGNEE COPY', 'POD COPY']
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


# ---------------------------
# POD Uploads
# ---------------------------

def pod_upload_search(request):
    """POD upload search page"""
    if request.method == 'POST':
        consignment_no = request.POST.get('consignment_no')
        try:
            shipment = Shipment.objects.get(consignment_no=consignment_no)
            return redirect('pod_upload', pk=shipment.pk)
        except Shipment.DoesNotExist:
            messages.error(request, 'Consignment not found.')
    return render(request, 'pod_upload_search.html', {'pagename': "POD Upload"})


def pod_upload(request, pk):
    """POD upload form"""
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
    """Consignment tracking page"""
    return render(request, 'consignment_tracking.html')


def bulk_tracking(request):
    """Internal bulk tracking view for authenticated users"""
    consignment_nos = request.GET.get('consignments', '').strip()
    shipments = []

    if consignment_nos:
        # Clean and split consignment numbers
        consignment_list = [
            cn.strip() for cn in
            consignment_nos.replace(',', ' ').replace('\n', ' ').split()
            if cn.strip()
        ]

        # Filter shipments based on user permissions
        if request.user.is_authenticated:
            if hasattr(request.user, 'usertype') and request.user.usertype == "Internal":
                shipments = Shipment.objects.filter(consignment_no__in=consignment_list)
            else:
                # External users can only see their own shipments
                shipments = Shipment.objects.filter(
                    consignment_no__in=consignment_list,
                    billto_customer=getattr(request.user, 'company_name', None)
                )
        else:
            # For unauthenticated users, redirect to public tracking
            return redirect('public_tracking')

    # Generate QR codes for tracking
    tracking_base_url = request.build_absolute_uri('/').rstrip('/')
    for shipment in shipments:
        shipment.tracking_qr_code = generate_tracking_qr_code(
            shipment.consignment_no,
            tracking_base_url
        )

    return render(request, 'bulk_tracking.html', {
        'shipments': shipments,
        'pagename': 'Bulk Consignment Tracking',
        'search_query': consignment_nos,
    })


def public_tracking(request):
    """Public tracking page - entry point for customers"""
    return render(request, 'public_tracking.html', {
        'pagename': 'Track Your Shipment'
    })


def public_tracking_status(request):
    """Public tracking results - shows shipment status to anyone"""
    consignment_nos = request.GET.get('consignments', '').strip()
    shipments = []

    if consignment_nos:
        # Clean and split consignment numbers
        consignment_list = [
            cn.strip() for cn in
            consignment_nos.replace(',', ' ').replace('\n', ' ').split()
            if cn.strip()
        ]

        # Public access - show basic tracking info only
        shipments = Shipment.objects.filter(
            consignment_no__in=consignment_list
        ).select_related()

        # Generate QR codes for public sharing
        tracking_base_url = request.build_absolute_uri('/').rstrip('/')
        for shipment in shipments:
            shipment.public_qr_code = generate_tracking_qr_code(
                shipment.consignment_no,
                tracking_base_url
            )

    return render(request, 'public_tracking.html', {
        'shipments': shipments,
        'search_query': consignment_nos,
        'pagename': 'Shipment Tracking Results'
    })


def single_shipment_tracking(request, consignment_no):
    """Direct tracking URL for individual shipments"""
    try:
        shipment = get_object_or_404(Shipment, consignment_no=consignment_no)

        # Generate QR code
        tracking_base_url = request.build_absolute_uri('/').rstrip('/')
        shipment.public_qr_code = generate_tracking_qr_code(
            shipment.consignment_no,
            tracking_base_url
        )

        return render(request, 'single_tracking.html', {
            'shipment': shipment,
            'pagename': f'Tracking - {consignment_no}'
        })
    except:
        return render(request, 'public_tracking.html', {
            'error': f'Shipment {consignment_no} not found',
            'pagename': 'Shipment Not Found'
        })


def tracking_api(request, consignment_no):
    """API endpoint for tracking data - Returns JSON response"""
    try:
        shipment = get_object_or_404(Shipment, consignment_no=consignment_no)

        data = {
            'consignment_no': shipment.consignment_no,
            'status': getattr(shipment, 'status', ''),
            'date': shipment.date.strftime('%d %b %Y') if shipment.date else None,
            'origin': getattr(shipment, 'origin', ''),
            'destination': getattr(shipment, 'destination', ''),
            'estimated_delivery': shipment.estimated_delivery_date.strftime(
                '%d %b %Y') if getattr(shipment, 'estimated_delivery_date', None) else None,
            'delivery_date': shipment.delivery_date.strftime('%d %b %Y') if getattr(shipment, 'delivery_date',
                                                                                    None) else None,
            'vehicle_no': getattr(shipment, 'vehicle_no', ''),
            'driver_details': getattr(shipment, 'driver_details', ''),
        }

        return JsonResponse({
            'success': True,
            'data': data
        })
    except:
        return JsonResponse({
            'success': False,
            'error': 'Shipment not found'
        }, status=404)


# ---------------------------
# Manifest Management
# ---------------------------

def create_manifest(request):
    """Create new manifest"""
    if request.method == 'POST':
        form = ManifestForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                # Save manifest without committing (needed for ManyToMany)
                manifest = form.save(commit=False)

                # Set calculated values from form's clean method
                manifest.total_freight = form.cleaned_data['total_freight_calculated']
                manifest.balance_freight = form.cleaned_data['balance_freight_calculated']
                manifest.total_articles = form.cleaned_data.get('total_articles_calculated', 0)

                # Save the manifest instance first
                manifest.save()

                # Now save the ManyToMany relationships
                form.save_m2m()

                # Recalculate totals after shipments are saved
                manifest.calculate_totals()
                manifest.save()

                messages.success(request, f'Manifest {manifest.manifest_id} created successfully!')
                return redirect('manifest_list')

            except Exception as e:
                messages.error(request, f'Error creating manifest: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ManifestForm()

    return render(request, 'manifest_create.html', {
        'form': form,
        'pagename': 'Create Manifest'
    })


def manifest_detail(request, pk):
    """Show manifest detail"""
    manifest = get_object_or_404(Manifest, pk=pk)
    shipments = manifest.shipments.all()
    total_articles = sum(getattr(s, 'no_article', 0) for s in shipments)


    return render(request, 'manifest_detail.html', {
        'manifest': manifest,
        'total_articles': total_articles,
    })


def manifest_pdf(request, pk):
    """Generate manifest PDF"""
    manifest = get_object_or_404(Manifest, pk=pk)
    template_path = 'manifest_pdf_template.html'
    context = {'manifest': manifest, 'shipments': manifest.shipments.all()}

    template = get_template(template_path)
    html = template.render(context)
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="manifest_{getattr(manifest, "manifest_id", pk)}.pdf"'

    pisa_status = pisa.CreatePDF(html, dest=response)
    if pisa_status.err:
        return HttpResponse('PDF generation failed.')
    return response


from django.db.models import Q
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.core.exceptions import FieldError
from datetime import datetime

from django.db.models import Q
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from datetime import datetime


@login_required
def manifest_list(request):
    """Display list of manifests with filtering"""
    manifests = Manifest.objects.all().order_by('-created_at')

    # Apply filters
    search = request.GET.get('search')
    vehicle = request.GET.get('vehicle')
    vendor = request.GET.get('vendor')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    print(f"\n=== FILTER DEBUG ===")
    print(f"Search: {search}")
    print(f"Vehicle: {vehicle}")
    print(f"Vendor: {vendor}")
    print(f"Date From: {date_from}")
    print(f"Date To: {date_to}")

    if search:
        manifests = manifests.filter(manifest_id__icontains=search)
        print(f"✅ Applied search filter: manifest_id contains '{search}'")

    if vehicle:
        manifests = manifests.filter(vehicle_no__icontains=vehicle)
        print(f"✅ Applied vehicle filter: vehicle_no contains '{vehicle}'")

    if vendor:
        # Check your Manifest model structure for vendor field
        # Try multiple possible field lookups for vendor:

        try:
            # Option 1: If vendor_name is a ForeignKey to Vendor model
            manifests = manifests.filter(vendor_name__name__icontains=vendor)
            print(f"✅ Applied vendor filter (FK name): vendor_name__name contains '{vendor}'")
        except:
            try:
                # Option 2: If vendor_name is a ForeignKey with different field name
                manifests = manifests.filter(vendor_name__vendor_name__icontains=vendor)
                print(f"✅ Applied vendor filter (FK vendor_name): vendor_name__vendor_name contains '{vendor}'")
            except:
                try:
                    # Option 3: If vendor_name is a CharField
                    manifests = manifests.filter(vendor_name__icontains=vendor)
                    print(f"✅ Applied vendor filter (CharField): vendor_name contains '{vendor}'")
                except Exception as e:
                    print(f"❌ Vendor filter failed: {str(e)}")
                    # Print available fields for debugging
                    print(f"Available Manifest fields: {[f.name for f in Manifest._meta.fields]}")

    if date_from:
        try:
            from_date = datetime.strptime(date_from, '%Y-%m-%d').date()
            manifests = manifests.filter(created_at__date__gte=from_date)
            print(f"✅ Applied date_from filter: created_at >= {from_date}")
        except ValueError as e:
            print(f"❌ Date from filter error: {e}")

    if date_to:
        try:
            to_date = datetime.strptime(date_to, '%Y-%m-%d').date()
            manifests = manifests.filter(created_at__date__lte=to_date)
            print(f"✅ Applied date_to filter: created_at <= {to_date}")
        except ValueError as e:
            print(f"❌ Date to filter error: {e}")

    print(f"Final query count: {manifests.count()}")
    print(f"=== END FILTER DEBUG ===\n")

    context = {
        'manifests': manifests,
        'pagename': 'Manifest List'
    }
    return render(request, 'manifest_list.html', context)

from django.contrib.auth.decorators import login_required

try:
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill

    EXCEL_AVAILABLE = True
except ImportError:
    EXCEL_AVAILABLE = False


@login_required
def manifest_report_download(request):
    manifests = Manifest.objects.select_related('vendor_name').all()

    # Apply same filters as manifest_list view
    search = request.GET.get('search')
    vehicle = request.GET.get('vehicle')
    vendor = request.GET.get('vendor')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    report_format = request.GET.get('format', 'csv')

    if search:
        manifests = manifests.filter(manifest_id__icontains=search)

    if vehicle:
        manifests = manifests.filter(vehicle_no__icontains=vehicle)

    if vendor:
        manifests = manifests.filter(vendor_name__vendor_code__icontains=vendor)

    if date_from:
        try:
            start_date_parsed = datetime.strptime(date_from, '%Y-%m-%d').date()
            manifests = manifests.filter(created_at__date__gte=start_date_parsed)
        except ValueError:
            pass

    if date_to:
        try:
            end_date_parsed = datetime.strptime(date_to, '%Y-%m-%d').date()
            manifests = manifests.filter(created_at__date__lte=end_date_parsed)
        except ValueError:
            pass

    manifests = manifests.order_by('-created_at')

    if report_format == 'excel' and EXCEL_AVAILABLE:
        return generate_excel_report(manifests, request)
    else:
        return generate_csv_report(manifests, request)


from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
def generate_excel_report(manifests, request):
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'manifest_report_{timestamp}.xlsx'

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = 'Manifest Report'

    # Header styling
    header_font = Font(bold=True, color='FFFFFF')
    header_fill = PatternFill(start_color='2C3E50', end_color='2C3E50', fill_type='solid')
    header_alignment = Alignment(horizontal='center', vertical='center')

    # Enhanced Headers with new fields
    headers = [
        'Manifest ID', 'Created Date', 'Consignment Numbers', 'Total Articles',
        'Base Freight (₹)', 'Additional Freight (₹)', 'Total Freight (₹)',
        'Advance Amount (₹)', 'Balance Freight (₹)', 'Origin Branch',
        'Destination Branch', 'Vehicle Number', 'Vendor Code', 'Vendor Name',
        'Driver Name', 'Driver Contact'
    ]

    # Apply header styling
    for col, header in enumerate(headers, 1):
        cell = worksheet.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment

    # Data rows with enhanced information
    for row, manifest in enumerate(manifests, 2):
        # Get consignment numbers from related shipments
        try:
            if hasattr(manifest, 'shipments') and manifest.shipments.exists():
                consignment_numbers = ", ".join([
                    shipment.consignment_no
                    for shipment in manifest.shipments.all()
                    if shipment.consignment_no
                ])
            else:
                consignment_numbers = "No Shipments"
        except Exception as e:
            consignment_numbers = "Error fetching shipments"
            print(f"Error getting consignments for manifest {manifest.id}: {e}")

        # Get vendor name (handle different vendor field structures)
        try:
            if manifest.vendor_name:
                if hasattr(manifest.vendor_name, 'name'):
                    vendor_name = manifest.vendor_name.name
                elif hasattr(manifest.vendor_name, 'vendor_name'):
                    vendor_name = manifest.vendor_name.vendor_name
                else:
                    vendor_name = str(manifest.vendor_name)
            else:
                vendor_name = "Not Assigned"
        except Exception as e:
            vendor_name = "Error fetching vendor"
            print(f"Error getting vendor for manifest {manifest.id}: {e}")

        # Get vendor code
        try:
            if manifest.vendor_name and hasattr(manifest.vendor_name, 'vendor_code'):
                vendor_code = manifest.vendor_name.vendor_code
            else:
                vendor_code = "N/A"
        except Exception:
            vendor_code = "N/A"

        # Get additional freight (handle if field doesn't exist)
        try:
            additional_freight = float(manifest.additional_freight or 0)
        except (AttributeError, TypeError):
            additional_freight = 0.0

        # Get base freight (handle if field doesn't exist)
        try:
            if hasattr(manifest, 'base_freight'):
                base_freight = float(manifest.base_freight or 0)
            else:
                # Calculate base freight as total - additional if base_freight doesn't exist
                total_freight = float(manifest.total_freight or 0)
                base_freight = total_freight - additional_freight
        except (AttributeError, TypeError):
            base_freight = 0.0

        # Calculate balance freight
        try:
            total_freight = float(manifest.total_freight or 0)
            advance_amount = float(manifest.advance_amount or 0)
            balance_freight = total_freight - advance_amount
        except (AttributeError, TypeError):
            balance_freight = 0.0

        # Prepare data row
        data = [
            manifest.manifest_id or 'N/A',
            manifest.created_at.strftime('%d-%m-%Y %H:%M'),
            consignment_numbers,
            manifest.total_articles or 0,
            base_freight,
            additional_freight,
            float(manifest.total_freight or 0),
            float(manifest.advance_amount or 0),
            balance_freight,
            manifest.origin_branch or 'Not Set',
            manifest.destination_branch or 'Not Set',
            manifest.vehicle_no or 'Not Assigned',
            vendor_code,
            vendor_name,
            manifest.driver_name or 'Not Assigned',
            manifest.driver_contact or 'Not Provided'
        ]

        # Write data to cells
        for col, value in enumerate(data, 1):
            cell = worksheet.cell(row=row, column=col, value=value)

            # Apply special formatting for certain columns
            if col in [5, 6, 7, 8, 9]:  # Freight amount columns
                cell.number_format = '₹#,##0.00'
            elif col == 2:  # Date column
                cell.alignment = Alignment(horizontal='center')
            elif col == 3:  # Consignment numbers column
                cell.alignment = Alignment(wrap_text=True, vertical='top')

    # Enhanced column width adjustment
    column_widths = {
        'A': 15,  # Manifest ID
        'B': 18,  # Created Date
        'C': 40,  # Consignment Numbers (wider for multiple numbers)
        'D': 12,  # Total Articles
        'E': 15,  # Base Freight
        'F': 18,  # Additional Freight
        'G': 15,  # Total Freight
        'H': 16,  # Advance Amount
        'I': 16,  # Balance Freight
        'J': 18,  # Origin Branch
        'K': 20,  # Destination Branch
        'L': 15,  # Vehicle Number
        'M': 12,  # Vendor Code
        'N': 20,  # Vendor Name
        'O': 18,  # Driver Name
        'P': 15,  # Driver Contact
    }

    # Apply column widths
    for column_letter, width in column_widths.items():
        worksheet.column_dimensions[column_letter].width = width

    # Add some styling improvements
    for row in worksheet.iter_rows(min_row=2, max_row=worksheet.max_row):
        for cell in row:
            # Add border to all data cells
            thin_border = Border(
                left=Side(style='thin'),
                right=Side(style='thin'),
                top=Side(style='thin'),
                bottom=Side(style='thin')
            )
            cell.border = thin_border

            # Alternate row coloring
            if cell.row % 2 == 0:
                cell.fill = PatternFill(start_color='F8F9FA', end_color='F8F9FA', fill_type='solid')

    # Add summary row at the end
    if manifests:
        summary_row = worksheet.max_row + 2

        # Summary headers
        worksheet.cell(row=summary_row, column=1, value='SUMMARY').font = Font(bold=True)
        worksheet.cell(row=summary_row + 1, column=1, value='Total Manifests:')
        worksheet.cell(row=summary_row + 1, column=2, value=len(manifests))

        worksheet.cell(row=summary_row + 2, column=1, value='Total Articles:')
        total_articles = sum([manifest.total_articles or 0 for manifest in manifests])
        worksheet.cell(row=summary_row + 2, column=2, value=total_articles)

        worksheet.cell(row=summary_row + 3, column=1, value='Total Freight Amount:')
        total_freight_sum = sum([float(manifest.total_freight or 0) for manifest in manifests])
        worksheet.cell(row=summary_row + 3, column=2, value=total_freight_sum).number_format = '₹#,##0.00'

        worksheet.cell(row=summary_row + 4, column=1, value='Total Advance Amount:')
        total_advance_sum = sum([float(manifest.advance_amount or 0) for manifest in manifests])
        worksheet.cell(row=summary_row + 4, column=2, value=total_advance_sum).number_format = '₹#,##0.00'

    workbook.save(response)
    return response


from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.core.exceptions import ValidationError
import logging
from .models import Manifest, Shipment
from .forms import ManifestForm

logger = logging.getLogger(__name__)


@login_required
@transaction.atomic
def manifest_update(request, pk):
    """
    Update an existing manifest with comprehensive change tracking and validation
    """
    manifest = get_object_or_404(Manifest, pk=pk)

    print(f"\n=== MANIFEST UPDATE REQUEST ===")
    print(f"Manifest: {manifest.manifest_id} (ID: {manifest.pk})")
    print(f"Method: {request.method}")

    if request.method == 'POST':
        print(f"POST data received for manifest update")

        # Create form with existing manifest instance
        form = ManifestForm(request.POST, request.FILES, instance=manifest)

        if form.is_valid():
            print(f"✅ Form is valid")

            try:
                # Store old values for comparison and change tracking
                old_values = {
                    'vendor_name': str(manifest.vendor_name) if manifest.vendor_name else None,
                    'vehicle_no': manifest.vehicle_no,
                    'driver_name': manifest.driver_name,
                    'driver_contact': manifest.driver_contact,
                    'origin_branch': manifest.origin_branch,
                    'destination_branch': manifest.destination_branch,
                    'base_freight': float(getattr(manifest, 'base_freight', 0) or 0),
                    'additional_freight': float(manifest.additional_freight or 0),
                    'total_freight': float(manifest.total_freight or 0),
                    'advance_amount': float(manifest.advance_amount or 0),
                    'total_articles': manifest.total_articles or 0,
                    'document': manifest.document.name if manifest.document else None,
                    'shipments_count': manifest.shipments.count() if hasattr(manifest, 'shipments') else 0
                }

                print(f"Old values captured: {old_values}")

                # Save the updated manifest
                updated_manifest = form.save(commit=False)

                # Handle base_freight calculation if it exists
                base_freight = form.cleaned_data.get('base_freight', 0) or 0
                additional_freight = form.cleaned_data.get('additional_freight', 0) or 0
                calculated_total = base_freight + additional_freight

                # Update calculated fields
                if hasattr(updated_manifest, 'base_freight'):
                    updated_manifest.base_freight = base_freight
                updated_manifest.total_freight = calculated_total

                # Save the manifest
                updated_manifest.save()

                # Save many-to-many relationships (shipments)
                form.save_m2m()

                print(f"✅ Manifest updated successfully")

                # Get new values for comparison
                new_values = {
                    'vendor_name': str(updated_manifest.vendor_name) if updated_manifest.vendor_name else None,
                    'vehicle_no': updated_manifest.vehicle_no,
                    'driver_name': updated_manifest.driver_name,
                    'driver_contact': updated_manifest.driver_contact,
                    'origin_branch': updated_manifest.origin_branch,
                    'destination_branch': updated_manifest.destination_branch,
                    'base_freight': float(getattr(updated_manifest, 'base_freight', 0) or 0),
                    'additional_freight': float(updated_manifest.additional_freight or 0),
                    'total_freight': float(updated_manifest.total_freight or 0),
                    'advance_amount': float(updated_manifest.advance_amount or 0),
                    'total_articles': updated_manifest.total_articles or 0,
                    'document': updated_manifest.document.name if updated_manifest.document else None,
                    'shipments_count': updated_manifest.shipments.count() if hasattr(updated_manifest,
                                                                                     'shipments') else 0
                }

                print(f"New values: {new_values}")

                # Create detailed change summary
                changes = []
                for key, old_val in old_values.items():
                    new_val = new_values[key]
                    if old_val != new_val:
                        if key == 'vendor_name':
                            changes.append(f'Vendor: {old_val or "Not Set"} → {new_val or "Not Set"}')
                        elif key == 'vehicle_no':
                            changes.append(f'Vehicle: {old_val or "Not Set"} → {new_val or "Not Set"}')
                        elif key == 'driver_name':
                            changes.append(f'Driver: {old_val or "Not Set"} → {new_val or "Not Set"}')
                        elif key == 'driver_contact':
                            changes.append(f'Driver Contact: {old_val or "Not Set"} → {new_val or "Not Set"}')
                        elif key == 'origin_branch':
                            changes.append(f'Origin: {old_val or "Not Set"} → {new_val or "Not Set"}')
                        elif key == 'destination_branch':
                            changes.append(f'Destination: {old_val or "Not Set"} → {new_val or "Not Set"}')
                        elif key == 'shipments_count':
                            changes.append(f'Shipments: {old_val} → {new_val}')
                        elif key == 'total_articles':
                            changes.append(f'Articles: {old_val} → {new_val}')
                        elif key in ['base_freight', 'additional_freight', 'total_freight', 'advance_amount']:
                            field_name = key.replace('_', ' ').title()
                            changes.append(f'{field_name}: ₹{old_val:.2f} → ₹{new_val:.2f}')
                        elif key == 'document':
                            if old_val and new_val:
                                changes.append('Document: Updated')
                            elif new_val:
                                changes.append('Document: Added')
                            elif old_val:
                                changes.append('Document: Removed')

                print(f"Changes detected: {changes}")

                # Log the update with detailed information
                change_summary = "; ".join(changes) if changes else "No significant changes detected"
                logger.info(
                    f'Manifest {updated_manifest.manifest_id} updated by user {request.user.username} '
                    f'at {datetime.now()}. Changes: {change_summary}'
                )

                # Create comprehensive success message
                if changes:
                    success_msg = f'Manifest {updated_manifest.manifest_id} updated successfully!'

                    # Show up to 3 most important changes in the message
                    important_changes = [c for c in changes if any(keyword in c.lower()
                                                                   for keyword in
                                                                   ['vendor', 'vehicle', 'freight', 'shipments',
                                                                    'articles'])]
                    display_changes = important_changes[:3] if important_changes else changes[:3]

                    if display_changes:
                        success_msg += f' Key changes: {"; ".join(display_changes)}'
                        if len(changes) > len(display_changes):
                            success_msg += f' and {len(changes) - len(display_changes)} more.'
                else:
                    success_msg = f'Manifest {updated_manifest.manifest_id} form submitted successfully. No changes were detected.'

                messages.success(request, success_msg)

                print(f"✅ Success message: {success_msg}")

                # Redirect to manifest detail page
                return redirect('manifest_detail', pk=updated_manifest.pk)

            except ValidationError as e:
                error_message = f'Validation error: {str(e)}'
                messages.error(request, error_message)
                logger.warning(f'Manifest update validation error for {manifest.manifest_id}: {error_message}')
                print(f"❌ Validation error: {error_message}")

            except Exception as e:
                error_message = f'An unexpected error occurred: {str(e)}'
                messages.error(request, 'An unexpected error occurred while updating the manifest. Please try again.')
                logger.error(f'Manifest update error for {manifest.manifest_id}: {str(e)}')
                print(f"❌ Unexpected error: {str(e)}")

        else:
            print(f"❌ Form is not valid")
            print(f"Form errors: {form.errors}")

            messages.error(request, 'Please correct the errors below.')
            logger.warning(f'Manifest update form validation failed for {manifest.manifest_id}: {form.errors}')

    else:
        print(f"GET request - creating form with existing manifest data")
        # Create form with existing manifest data for GET request
        form = ManifestForm(instance=manifest)

        # Debug: Print current manifest data
        print(f"Current manifest data:")
        print(f"  - Vendor: {manifest.vendor_name}")
        print(f"  - Vehicle: {manifest.vehicle_no}")
        print(f"  - Driver: {manifest.driver_name}")
        print(f"  - Total Freight: {manifest.total_freight}")
        print(f"  - Articles: {manifest.total_articles}")
        if hasattr(manifest, 'shipments'):
            print(f"  - Shipments: {manifest.shipments.count()}")

    # Prepare context for template
    context = {
        'form': form,
        'manifest': manifest,
        'pagename': f'Update Manifest - {manifest.manifest_id}',
        'is_update': True,  # Flag to help template distinguish between create/update
    }

    return render(request, 'manifest_update.html', context)


def print_manifest_list(request):
    """Print manifest list"""
    manifests = Manifest.objects.all()
    return render(request, 'print_manifest_list.html', {'manifests': manifests})


from django.http import HttpResponse
from django.db.models import Q
from datetime import datetime
import csv

# Check if Excel libraries are available
try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment

    EXCEL_AVAILABLE = True
except ImportError:
    EXCEL_AVAILABLE = False


def trip_report_download(request):
    """
    Download trip report in CSV or Excel format with filtering support
    """
    # Get format parameter (default to Excel if available, otherwise CSV)
    format_type = request.GET.get('format', 'excel' if EXCEL_AVAILABLE else 'csv').lower()

    # Start with all trips
    trips = TripOutToVendor.objects.select_related('vendor').all()

    # Apply filters based on request parameters
    filters = Q()
    active_filters = {}

    # Status filter
    if request.GET.get('status'):
        status = request.GET.get('status')
        filters &= Q(status=status)
        active_filters['Status'] = status

    # Vendor name filter - CORRECTED to match template
    if request.GET.get('vendor'):
        vendor = request.GET.get('vendor')
        # Try different vendor field patterns
        try:
            filters &= Q(vendor__vendor_name__icontains=vendor)
            active_filters['Vendor'] = vendor
        except:
            try:
                filters &= Q(vendor__name__icontains=vendor)
                active_filters['Vendor'] = vendor
            except:
                try:
                    filters &= Q(vendor__icontains=vendor)
                    active_filters['Vendor'] = vendor
                except:
                    pass

    # Trip ID filter
    if request.GET.get('trip_id'):
        trip_id = request.GET.get('trip_id')
        filters &= Q(trip_id__icontains=trip_id)
        active_filters['Trip ID'] = trip_id

    # From location filter
    if request.GET.get('from_location'):
        from_location = request.GET.get('from_location')
        filters &= Q(from_location__icontains=from_location)
        active_filters['From Location'] = from_location

    # Destination filter
    if request.GET.get('destination'):
        destination = request.GET.get('destination')
        filters &= Q(destination__icontains=destination)
        active_filters['Destination'] = destination

    # Apply filters
    trips = trips.filter(filters).order_by('-created_at')

    # Generate filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    base_filename = f'trip_report_{timestamp}'

    if format_type == 'excel' and EXCEL_AVAILABLE:
        return generate_trip_excel_report(trips, active_filters, base_filename)
    else:
        return generate_trip_csv_report(trips, active_filters, base_filename)


def generate_trip_excel_report(trips, active_filters=None, base_filename='trip_report'):
    """Generate comprehensive Excel report for trips with all model fields"""
    timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
    filename = f'{base_filename}_{timestamp}.xlsx'

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = 'Trip Report'

    # Header styling
    header_font = Font(bold=True, color='FFFFFF', size=11)
    header_fill = PatternFill(start_color='2C3E50', end_color='2C3E50', fill_type='solid')
    header_alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

    # Complete headers mapping all model fields
    headers = [
        'Trip ID',
        'Vendor Name',
        'Vendor Code',
        'Vehicle Type',
        'Vehicle Capacity (MT)',
        'From Location',
        'Destination',
        'Distance (KM)',
        'Trip Charge (₹)',
        'Additional Charge (₹)',
        'Total Bill Amount (₹)',
        'Status',
        'Created Date',
        'Created Time'
    ]

    # Apply header styling and set row height
    worksheet.row_dimensions[1].height = 30
    for col, header in enumerate(headers, 1):
        cell = worksheet.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment

    # Data rows with comprehensive field mapping
    for row, trip in enumerate(trips, 2):
        # Get vendor information safely
        try:
            if trip.vendor:
                vendor_name = getattr(trip.vendor, 'vendor_name', str(trip.vendor))
                vendor_code = getattr(trip.vendor, 'vendor_code', 'N/A')
            else:
                vendor_name = "Not Assigned"
                vendor_code = "N/A"
        except Exception:
            vendor_name = "N/A"
            vendor_code = "N/A"

        # Prepare comprehensive data row
        data = [
            trip.trip_id or 'N/A',
            vendor_name,
            vendor_code,
            trip.vehicle_type or 'Not Specified',
            float(trip.vehicle_capacity or 0),
            trip.from_location or 'Not Set',
            trip.destination or 'Not Set',
            float(trip.kilometer or 0),
            float(trip.trip_charge or 0),
            float(trip.additional_charge or 0),
            float(trip.total_bill_amount or 0),
            trip.status or 'In-Progress',
            trip.created_at.strftime('%d-%m-%Y') if trip.created_at else 'N/A',
            trip.created_at.strftime('%H:%M:%S') if trip.created_at else 'N/A'
        ]

        # Write data to cells with formatting
        for col, value in enumerate(data, 1):
            cell = worksheet.cell(row=row, column=col, value=value)

            # Apply specific formatting based on data type
            if col in [5, 8, 9, 10, 11]:  # Numeric columns
                if col in [9, 10, 11]:  # Currency columns
                    cell.number_format = '₹#,##0.00'
                else:  # Other numeric columns
                    cell.number_format = '#,##0.00'
                cell.alignment = Alignment(horizontal='right')
            elif col in [13, 14]:  # Date and time columns
                cell.alignment = Alignment(horizontal='center')
            else:  # Text columns
                cell.alignment = Alignment(horizontal='left', vertical='center')

        # Set row height for better readability
        worksheet.row_dimensions[row].height = 20

    # Auto-adjust column widths with improved logic
    column_widths = {
        1: 15,  # Trip ID
        2: 25,  # Vendor Name
        3: 15,  # Vendor Code
        4: 20,  # Vehicle Type
        5: 18,  # Vehicle Capacity
        6: 25,  # From Location
        7: 25,  # Destination
        8: 15,  # Distance
        9: 18,  # Trip Charge
        10: 18,  # Additional Charge
        11: 18,  # Total Bill Amount
        12: 15,  # Status
        13: 15,  # Created Date
        14: 12,  # Created Time
    }

    for col, width in column_widths.items():
        column_letter = openpyxl.utils.get_column_letter(col)
        worksheet.column_dimensions[column_letter].width = width

    # Add filters applied section
    if active_filters:
        summary_start_row = worksheet.max_row + 3

        # Filter summary header
        filter_header_cell = worksheet.cell(row=summary_start_row, column=1, value='APPLIED FILTERS')
        filter_header_cell.font = Font(bold=True, size=12, color='FFFFFF')
        filter_header_cell.fill = PatternFill(start_color='34495E', end_color='34495E', fill_type='solid')
        filter_header_cell.alignment = Alignment(horizontal='center', vertical='center')

        # Merge cells for filter header
        worksheet.merge_cells(f'A{summary_start_row}:C{summary_start_row}')

        # Add individual filters
        for i, (filter_name, filter_value) in enumerate(active_filters.items(), 1):
            filter_row = summary_start_row + i
            worksheet.cell(row=filter_row, column=1, value=f'{filter_name.replace("_", " ").title()}:').font = Font(
                bold=True)
            worksheet.cell(row=filter_row, column=2, value=str(filter_value))

    # Add comprehensive summary statistics
    if trips:
        stats_start_row = worksheet.max_row + 3

        # Summary statistics header
        stats_header_cell = worksheet.cell(row=stats_start_row, column=1, value='SUMMARY STATISTICS')
        stats_header_cell.font = Font(bold=True, size=14, color='FFFFFF')
        stats_header_cell.fill = PatternFill(start_color='27AE60', end_color='27AE60', fill_type='solid')
        stats_header_cell.alignment = Alignment(horizontal='center', vertical='center')

        # Merge cells for summary header
        worksheet.merge_cells(f'A{stats_start_row}:D{stats_start_row}')

        current_row = stats_start_row + 2

        # Basic statistics
        basic_stats = [
            ('Total Trips:', len(trips)),
            ('Total Distance (KM):', sum([float(trip.kilometer or 0) for trip in trips])),
            ('Total Trip Charges (₹):', sum([float(trip.trip_charge or 0) for trip in trips])),
            ('Total Additional Charges (₹):', sum([float(trip.additional_charge or 0) for trip in trips])),
            ('Total Bill Amount (₹):', sum([float(trip.total_bill_amount or 0) for trip in trips])),
        ]

        for stat_name, stat_value in basic_stats:
            worksheet.cell(row=current_row, column=1, value=stat_name).font = Font(bold=True)
            cell = worksheet.cell(row=current_row, column=2, value=stat_value)
            cell.font = Font(bold=True)

            # Format currency cells
            if '₹' in stat_name:
                cell.number_format = '₹#,##0.00'
            elif 'KM' in stat_name:
                cell.number_format = '#,##0.00'

            current_row += 1

        current_row += 1

        # Status breakdown
        status_header_cell = worksheet.cell(row=current_row, column=1, value='STATUS BREAKDOWN')
        status_header_cell.font = Font(bold=True, color='FFFFFF')
        status_header_cell.fill = PatternFill(start_color='3498DB', end_color='3498DB', fill_type='solid')
        status_header_cell.alignment = Alignment(horizontal='center', vertical='center')

        # Merge cells for status header
        worksheet.merge_cells(f'A{current_row}:C{current_row}')
        current_row += 1

        status_counts = Counter([trip.status for trip in trips])
        for status, count in status_counts.items():
            worksheet.cell(row=current_row, column=1, value=f'{status}:').font = Font(bold=True)
            worksheet.cell(row=current_row, column=2, value=count)

            # Calculate percentage
            percentage = (count / len(trips)) * 100
            worksheet.cell(row=current_row, column=3, value=f'({percentage:.1f}%)')
            current_row += 1

        current_row += 1

        # Vehicle type breakdown
        vehicle_header_cell = worksheet.cell(row=current_row, column=1, value='VEHICLE TYPE BREAKDOWN')
        vehicle_header_cell.font = Font(bold=True, color='FFFFFF')
        vehicle_header_cell.fill = PatternFill(start_color='9B59B6', end_color='9B59B6', fill_type='solid')
        vehicle_header_cell.alignment = Alignment(horizontal='center', vertical='center')

        # Merge cells for vehicle header
        worksheet.merge_cells(f'A{current_row}:C{current_row}')
        current_row += 1

        vehicle_counts = Counter([trip.vehicle_type or 'Not Specified' for trip in trips])
        for vehicle_type, count in vehicle_counts.items():
            worksheet.cell(row=current_row, column=1, value=f'{vehicle_type}:').font = Font(bold=True)
            worksheet.cell(row=current_row, column=2, value=count)

            # Calculate percentage
            percentage = (count / len(trips)) * 100
            worksheet.cell(row=current_row, column=3, value=f'({percentage:.1f}%)')
            current_row += 1

        current_row += 1

        # Top vendors by trip count
        vendor_header_cell = worksheet.cell(row=current_row, column=1, value='TOP VENDORS BY TRIP COUNT')
        vendor_header_cell.font = Font(bold=True, color='FFFFFF')
        vendor_header_cell.fill = PatternFill(start_color='E67E22', end_color='E67E22', fill_type='solid')
        vendor_header_cell.alignment = Alignment(horizontal='center', vertical='center')

        # Merge cells for vendor header
        worksheet.merge_cells(f'A{current_row}:C{current_row}')
        current_row += 1

        vendor_names = []
        for trip in trips:
            try:
                if trip.vendor:
                    vendor_names.append(getattr(trip.vendor, 'vendor_name', str(trip.vendor)))
                else:
                    vendor_names.append('Not Assigned')
            except Exception:
                vendor_names.append('N/A')

        vendor_counts = Counter(vendor_names)
        top_vendors = vendor_counts.most_common(10)  # Top 10 vendors

        for vendor_name, count in top_vendors:
            worksheet.cell(row=current_row, column=1, value=f'{vendor_name}:').font = Font(bold=True)
            worksheet.cell(row=current_row, column=2, value=count)

            # Calculate percentage
            percentage = (count / len(trips)) * 100
            worksheet.cell(row=current_row, column=3, value=f'({percentage:.1f}%)')
            current_row += 1

    # Add generation timestamp
    timestamp_row = worksheet.max_row + 2
    worksheet.cell(row=timestamp_row, column=1, value='Report Generated:').font = Font(bold=True)
    worksheet.cell(row=timestamp_row, column=2, value=timezone.now().strftime('%d-%m-%Y %H:%M:%S'))

    # Freeze top row for better navigation
    worksheet.freeze_panes = 'A2'

    # Add autofilter to header row
    worksheet.auto_filter.ref = f'A1:{openpyxl.utils.get_column_letter(len(headers))}1'

    workbook.save(response)
    return response


def generate_trip_csv_report(trips, active_filters=None, base_filename='trip_report'):
    """Generate CSV report for trips"""
    filename = f'{base_filename}.csv'

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)

    # Write CSV headers
    writer.writerow([
        'Trip ID', 'Created Date', 'Vendor Name', 'Vehicle Type', 'Vehicle Capacity (MT)',
        'From Location', 'Destination', 'Distance (KM)', 'Total Bill Amount (₹)',
        'Status', 'Driver Name', 'Driver Contact', 'Remarks'
    ])

    # Write CSV data
    for trip in trips:
        # Get vendor name safely
        try:
            if trip.vendor:
                if hasattr(trip.vendor, 'vendor_name'):
                    vendor_name = trip.vendor.vendor_name
                elif hasattr(trip.vendor, 'name'):
                    vendor_name = trip.vendor.name
                else:
                    vendor_name = str(trip.vendor)
            else:
                vendor_name = "Not Assigned"
        except Exception:
            vendor_name = "N/A"

        writer.writerow([
            trip.trip_id or 'N/A',
            trip.created_at.strftime('%d-%m-%Y %H:%M'),
            vendor_name,
            trip.vehicle_type or 'Not Specified',
            trip.vehicle_capacity or 0,
            trip.from_location or 'Not Set',
            trip.destination or 'Not Set',
            trip.kilometer or 0,
            f'{float(trip.total_bill_amount or 0):.2f}',
            trip.status or 'In-Progress',
            getattr(trip, 'driver_name', 'Not Assigned') or 'Not Assigned',
            getattr(trip, 'driver_contact', 'Not Provided') or 'Not Provided',
            getattr(trip, 'remarks', '') or ''
        ])

    # Add filter summary as comments if filters are active
    if active_filters:
        writer.writerow([])  # Empty row
        writer.writerow(['FILTERS APPLIED:'])
        for filter_name, filter_value in active_filters.items():
            writer.writerow([f'{filter_name}: {filter_value}'])

        # Add summary statistics
        writer.writerow([])  # Empty row
        writer.writerow(['SUMMARY STATISTICS:'])
        writer.writerow([f'Total Trips: {len(trips)}'])
        total_bill_sum = sum([float(trip.total_bill_amount or 0) for trip in trips])
        writer.writerow([f'Total Bill Amount: ₹{total_bill_sum:.2f}'])

    return response


def generate_csv_report(trips, active_filters, base_filename):
    """Generate CSV report"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{base_filename}.csv"'

    writer = csv.writer(response)

    # Write header with report info
    writer.writerow(['Trip Report'])
    writer.writerow(['Generated:', datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
    writer.writerow(['Total Records:', trips.count()])

    # Write active filters
    if active_filters:
        writer.writerow(['Active Filters:'])
        for filter_name, filter_value in active_filters.items():
            writer.writerow([f'  {filter_name}:', filter_value])

    writer.writerow([])  # Empty row

    # Write column headers
    headers = [
        'Trip ID',
        'Vendor Name',
        'Vehicle Type',
        'Vehicle Capacity (MT)',
        'From Location',
        'Destination',
        'Distance (KM)',
        'Trip Charge (₹)',
        'Additional Charge (₹)',
        'Total Bill Amount (₹)',
        'Status',
        'Created Date',
        'Created Time'
    ]
    writer.writerow(headers)

    # Write trip data
    for trip in trips:
        row = [
            trip.trip_id or '',
            trip.vendor.vendor_name if trip.vendor else 'Not Assigned',
            trip.vehicle_type or 'Not Specified',
            trip.vehicle_capacity or '',
            trip.from_location or '',
            trip.destination or '',
            trip.kilometer or '',
            f'{float(trip.trip_charge or 0):.2f}',
            f'{float(trip.additional_charge or 0):.2f}',
            f'{float(trip.total_bill_amount or 0):.2f}',
            trip.status or '',
            trip.created_at.strftime('%Y-%m-%d'),
            trip.created_at.strftime('%H:%M:%S')
        ]
        writer.writerow(row)

    return response



# ---------------------------
# User Management
# ---------------------------

def user_add(request):
    """Add user page"""
    return render(request, 'users/user_add.html')


def user_manage(request):
    """Manage users page"""
    return render(request, 'users/user_manage.html')


# ---------------------------
# Master Data Management
# ---------------------------

def branch_add(request):
    """Add branch page"""
    return render(request, 'main/branch_add.html')


def branch_manage(request):
    """Manage branches page"""
    return render(request, 'main/branch_manage.html')


def fleet_add(request):
    """Add fleet page"""
    return render(request, 'main/fleet_add.html')


def fleet_manage(request):
    """Manage fleet page"""
    return render(request, 'main/fleet_manage.html')


def create_vendor(request):
    """Create vendor"""
    if request.method == "POST":
        form = VendorMasterForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Vendor created successfully ✅")
            return redirect("vendor-list")
    else:
        form = VendorMasterForm()
    return render(request, "vendor_form.html", {"form": form})


# ---------------------------
# Trip Management
# ---------------------------

def create_trip(request):
    """Create trip"""
    if request.method == "POST":
        form = TripOutToVendorForm(request.POST)
        if form.is_valid():
            trip = form.save(commit=False)
            # Auto-calculate total bill amount if missing
            if not getattr(trip, 'total_bill_amount', None):
                trip.total_bill_amount = getattr(trip, 'trip_charge', 0) + getattr(trip, 'additional_charge', 0)
            trip.save()
            messages.success(request, f"Trip {getattr(trip, 'trip_id', 'N/A')} created successfully ✅")
            return redirect("trip-list")
        else:
            messages.error(request, "⚠️ Please correct the errors below.")
    else:
        form = TripOutToVendorForm()
    return render(request, "trip_form.html", {"form": form, 'pagename': 'Create Trip'})


def trip_list(request):
    """List trips with filtering"""
    trips = TripOutToVendor.objects.all().order_by('-created_at')

    # Get filter parameters
    status = request.GET.get("status")
    trip_id = request.GET.get("trip_id")
    vendor = request.GET.get("vendor")  # Added vendor filter
    date_from = request.GET.get("date_from")  # Optional date filters
    date_to = request.GET.get("date_to")

    print(f"\n=== TRIP FILTER DEBUG ===")
    print(f"Status: {status}")
    print(f"Trip ID: {trip_id}")
    print(f"Vendor: {vendor}")
    print(f"Date From: {date_from}")
    print(f"Date To: {date_to}")

    # Apply filters
    if status:
        trips = trips.filter(status=status)
        print(f"✅ Applied status filter: status = '{status}'")

    if trip_id:
        trips = trips.filter(trip_id__icontains=trip_id)
        print(f"✅ Applied trip_id filter: trip_id contains '{trip_id}'")

    if vendor:
        # Handle different vendor field structures
        try:
            # Option 1: If vendor is a ForeignKey to Vendor model with 'name' field
            trips = trips.filter(vendor__name__icontains=vendor)
            print(f"✅ Applied vendor filter (FK name): vendor__name contains '{vendor}'")
        except:
            try:
                # Option 2: If vendor is a ForeignKey with 'vendor_name' field
                trips = trips.filter(vendor__vendor_name__icontains=vendor)
                print(f"✅ Applied vendor filter (FK vendor_name): vendor__vendor_name contains '{vendor}'")
            except:
                try:
                    # Option 3: If vendor is a CharField
                    trips = trips.filter(vendor__icontains=vendor)
                    print(f"✅ Applied vendor filter (CharField): vendor contains '{vendor}'")
                except:
                    try:
                        # Option 4: If field is named 'vendor_name'
                        trips = trips.filter(vendor_name__icontains=vendor)
                        print(f"✅ Applied vendor filter (vendor_name): vendor_name contains '{vendor}'")
                    except Exception as e:
                        print(f"❌ Vendor filter failed: {str(e)}")
                        # Debug: Print available fields
                        print(f"Available TripOutToVendor fields: {[f.name for f in TripOutToVendor._meta.fields]}")

    if date_from:
        try:
            from datetime import datetime
            from_date = datetime.strptime(date_from, '%Y-%m-%d').date()
            trips = trips.filter(created_at__date__gte=from_date)
            print(f"✅ Applied date_from filter: created_at >= {from_date}")
        except ValueError as e:
            print(f"❌ Date from filter error: {e}")

    if date_to:
        try:
            from datetime import datetime
            to_date = datetime.strptime(date_to, '%Y-%m-%d').date()
            trips = trips.filter(created_at__date__lte=to_date)
            print(f"✅ Applied date_to filter: created_at <= {to_date}")
        except ValueError as e:
            print(f"❌ Date to filter error: {e}")

    print(f"Final query count: {trips.count()}")
    print(f"=== END TRIP FILTER DEBUG ===\n")

    context = {
        'trips': trips,
        'pagename': 'Trip List'
    }
    return render(request, "trip_list.html", context)


def update_trip_status(request, pk):
    """Update trip status"""
    trip = get_object_or_404(TripOutToVendor, pk=pk)
    if request.method == "POST":
        new_status = request.POST.get("status")
        if hasattr(TripOutToVendor, 'STATUS_CHOICES') and new_status in dict(TripOutToVendor.STATUS_CHOICES):
            trip.status = new_status
            trip.save()
            messages.success(request, f"Trip {getattr(trip, 'trip_id', 'N/A')} status updated to {new_status}")
    return redirect("trip-list")


def trip_detail(request, pk):
    """Show trip detail"""
    trip = get_object_or_404(TripOutToVendor, pk=pk)
    return render(request, "trip_detail.html", {"trip": trip, 'pagename': 'Trip Details'})


def trip_update(request, pk):
    """Update trip"""
    trip = get_object_or_404(TripOutToVendor, pk=pk)
    if request.method == "POST":
        form = TripOutToVendorForm(request.POST, instance=trip)
        if form.is_valid():
            form.save()
            messages.success(request, f"Trip {getattr(trip, 'trip_id', 'N/A')} updated successfully ✅")
            return redirect("trip-list")
    else:
        form = TripOutToVendorForm(instance=trip)
    return render(request, "trip_update.html", {"form": form, "trip": trip, 'pagename': 'Trip Update'})


from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_protect
from django.http import JsonResponse
from django.db import transaction
from django.utils import timezone
from datetime import datetime
import logging
from .models import TripOutToVendor

logger = logging.getLogger(__name__)


@login_required
@csrf_protect
@require_http_methods(["POST"])
def trip_status_update(request, pk):
    """
    Update TripOutToVendor status with validation and logging
    """
    try:
        trip = get_object_or_404(TripOutToVendor, pk=pk)
    except:
        messages.error(request, 'Trip not found.')
        return redirect('trip-list')

    # Get the new status from POST data
    new_status = request.POST.get('status', '').strip()

    # Get valid statuses from model choices
    valid_statuses = [choice[0] for choice in TripOutToVendor.STATUS_CHOICES]

    # Validate status
    if not new_status:
        messages.error(request, 'Status is required.')
        return redirect('trip-list')

    if new_status not in valid_statuses:
        messages.error(request, f'Invalid status: {new_status}')
        return redirect('trip-list')

    # Store old status for comparison and logging
    old_status = trip.status

    # Check if status is actually changing
    if old_status == new_status:
        messages.info(request, f'Trip {trip.trip_id} status is already "{new_status}".')
        return redirect('trip-list')

    # Optional: Define business rules for status transitions
    VALID_TRANSITIONS = {
        'In-Progress': ['Closed', 'Cancelled', 'Hold'],
        'Hold': ['In-Progress', 'Cancelled', 'Closed'],
        'Cancelled': ['In-Progress'],  # Allow reactivation
        'Closed': ['In-Progress']  # Allow reopening if needed
    }

    # Check status transition rules (optional - remove if not needed)
    if old_status in VALID_TRANSITIONS:
        if new_status not in VALID_TRANSITIONS[old_status]:
            messages.warning(
                request,
                f'Status transition from "{old_status}" to "{new_status}" may require approval.'
            )
            # Note: Showing warning but allowing change - modify as per business rules

    try:
        with transaction.atomic():
            # Update the trip status
            trip.status = new_status
            trip.save(update_fields=['status'])

            # Log the status change
            logger.info(
                f'Trip {trip.trip_id} (ID: {trip.pk}) status updated from "{old_status}" to "{new_status}" '
                f'by user {request.user.username if request.user.is_authenticated else "Anonymous"} '
                f'at {timezone.now()}'
            )

            # Create success message
            success_message = (
                f'Trip {trip.trip_id} status successfully updated to "{new_status}". '
                f'Vendor: {trip.vendor.vendor_name}'
            )
            messages.success(request, success_message)

            # For AJAX requests
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': success_message,
                    'trip_id': trip.trip_id,
                    'trip_pk': trip.pk,
                    'old_status': old_status,
                    'new_status': new_status,
                    'vendor_name': trip.vendor.vendor_name,
                    'updated_at': timezone.now().isoformat()
                })

            # Regular form submission redirect
            return redirect('trip-list')

    except Exception as e:
        error_message = f'Failed to update trip status: {str(e)}'
        logger.error(
            f'Trip status update error for trip {trip.trip_id} (ID: {trip.pk}): {error_message}'
        )
        messages.error(request, 'An unexpected error occurred while updating the trip status.')

        # For AJAX requests
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': 'Failed to update trip status',
                'trip_id': trip.trip_id,
                'details': str(e) if request.user.is_staff else None
            }, status=500)

        return redirect('trip-list')

