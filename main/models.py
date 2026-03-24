from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth.hashers import make_password
from django.db.models import Sum, Count
import uuid


class CustomerMaster(models.Model):
    """Customer Master for managing customer information"""

    STATUS_CHOICES = [
        ('Active', 'Active'),
        ('Inactive', 'Inactive'),
    ]

    customer_id = models.CharField(max_length=50, unique=True, editable=False)
    company_name = models.CharField(max_length=255, blank=True, null=True)
    billing_address = models.TextField()
    city = models.CharField(max_length=100)
    pin_code = models.CharField(max_length=10)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=100, default='India')

    # Tax Information
    gstn = models.CharField(max_length=20, blank=True, null=True)
    pan = models.CharField(max_length=20, blank=True, null=True)
    cin = models.CharField(max_length=30, blank=True, null=True)

    # Contact Information
    contact_person = models.CharField(max_length=100)
    contact_number = models.CharField(max_length=20)
    email_id = models.EmailField()

    # Contract Information
    contract_date_from = models.DateField()
    contract_date_to = models.DateField()

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Active')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Customer"
        verbose_name_plural = "Customers"
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.customer_id:
            self.customer_id = self.generate_customer_id()
        super().save(*args, **kwargs)

    def generate_customer_id(self):
        return f"CUST-{uuid.uuid4().hex[:6].upper()}"

    def __str__(self):
        return f"{self.company_name} ({self.customer_id})"


class Branch(models.Model):
    """Branch Master for managing company branches"""

    branch_code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    address = models.TextField()
    city = models.CharField(max_length=50)
    state = models.CharField(max_length=50)
    pincode = models.CharField(max_length=10)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Branch"
        verbose_name_plural = "Branches"
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.city})"


class Fleet(models.Model):
    """Fleet Master for managing vehicles"""

    VEHICLE_TYPE_CHOICES = [
        ('Truck', 'Truck'),
        ('Trailer', 'Trailer'),
        ('Container', 'Container'),
        ('Tempo', 'Tempo'),
        ('Van', 'Van'),
        ('Other', 'Other'),
    ]

    STATUS_CHOICES = [
        ('Active', 'Active'),
        ('Inactive', 'Inactive'),
    ]

    vehicle_number = models.CharField(max_length=20, unique=True)
    vehicle_type = models.CharField(max_length=20, choices=VEHICLE_TYPE_CHOICES)
    capacity_mt = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        help_text="Capacity in Metric Tons"
    )
    make = models.CharField(max_length=50, blank=True, null=True)
    model = models.CharField(max_length=50, blank=True, null=True)
    year_of_manufacture = models.PositiveIntegerField(blank=True, null=True)

    # Owner Information
    owner_name = models.CharField(max_length=100, blank=True, null=True)
    owner_contact = models.CharField(max_length=15, blank=True, null=True)

    branch = models.ForeignKey(
        Branch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='Active'
    )

    # Document Validity
    insurance_validity = models.DateField(blank=True, null=True)
    fitness_validity = models.DateField(blank=True, null=True)
    permit_validity = models.DateField(blank=True, null=True)
    pollution_validity = models.DateField(blank=True, null=True)

    remarks = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Fleet Vehicle"
        verbose_name_plural = "Fleet Vehicles"
        ordering = ['vehicle_number']

    def insurance_expiry(self):
        """Read-only field for admin."""
        return self.insurance_validity

    insurance_expiry.short_description = "Insurance Expiry"

    def fitness_certificate_expiry(self):
        """Read-only field for admin."""
        return self.fitness_validity

    fitness_certificate_expiry.short_description = "Fitness Certificate Expiry"

    def __str__(self):
        return f"{self.vehicle_number} - {self.vehicle_type}"


class CustomUser(AbstractUser):
    """Custom User Model extending AbstractUser"""

    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
        ('O', 'Other'),
    ]

    ROLE_CHOICES = [
        ('Admin', 'Admin'),
        ('Supervisor', 'Supervisor'),
        ('Co-ordinator', 'Co-ordinator'),
        ('Executive', 'Executive'),
        ('Branch Manager', 'Branch Manager'),
        ('Customer', 'Customer'),
    ]

    STATUS_CHOICES = [
        ('Active', 'Active'),
        ('Inactive', 'Inactive'),
    ]

    USERTYPE_CHOICES = [
        ('Internal', 'Internal'),
        ('External', 'External'),
    ]

    gender = models.CharField(max_length=1, choices=GENDER_CHOICES)
    phone_number = models.CharField(max_length=15)
    usertype = models.CharField(
        max_length=10,
        choices=USERTYPE_CHOICES,
        default='Internal'
    )

    company_name = models.ForeignKey(
        'CustomerMaster',
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    branch = models.ForeignKey(
        'Branch',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    user_status = models.CharField(
        max_length=8,
        choices=STATUS_CHOICES,
        default='Active'
    )

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"

    def save(self, *args, **kwargs):
        # Set default password for new users
        if not self.pk and not self.password:
            self.password = make_password('admin@2025')
        super().save(*args, **kwargs)

    def __str__(self):
        return self.username


class VendorMaster(models.Model):
    """Vendor Master for managing vendor information"""

    STATUS_CHOICES = [
        ('Active', 'Active'),
        ('Inactive', 'Inactive'),
    ]

    vendor_code = models.CharField(max_length=20, unique=True, editable=False)
    vendor_name = models.CharField(max_length=255)
    billing_address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=100, default="India")

    # Tax Information
    gstn = models.CharField(max_length=20, blank=True, null=True)
    pan = models.CharField(max_length=20, blank=True, null=True)

    short_intro = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    active_till = models.DateField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="Active")

    class Meta:
        verbose_name = "Vendor"
        verbose_name_plural = "Vendors"
        ordering = ['vendor_name']

    def save(self, *args, **kwargs):
        if not self.vendor_code:
            self.vendor_code = self._generate_vendor_code()
        super().save(*args, **kwargs)

    def _generate_vendor_code(self):
        """Generate unique vendor code"""
        last_vendor = VendorMaster.objects.order_by('-id').first()
        if last_vendor and last_vendor.vendor_code[-3:].isdigit():
            last_number = int(last_vendor.vendor_code[-3:])
            new_number = last_number + 1
        else:
            new_number = 1
        return f"VND-{new_number:03d}"

    def __str__(self):
        return f"{self.vendor_name} ({self.vendor_code})"


class Shipment(models.Model):
    """Main shipment model for managing logistics consignments"""

    PAYMENT_MODES = [
        ('TO-PAY', 'TO-PAY'),
        ('TBB', 'TBB'),
        ('PAID', 'PAID'),
        ('FOC', 'FOC'),
    ]

    STATUS_CHOICES = [
        # Initial/Booking Statuses
        ('Booked', 'Booked'),
        ('Confirmed', 'Confirmed'),

        # Pickup/Collection Statuses
        ('Ready for Pickup', 'Ready for Pickup'),
        ('Pickup Scheduled', 'Pickup Scheduled'),
        ('Picked Up', 'Picked Up'),
        ('Arrived', 'Arrived'),
        ('Accepted at Hub', 'Accepted at Hub'),

        # Transit Statuses
        ('In Transit', 'In Transit'),
        ('Reached Origin Hub', 'Reached Origin Hub'),
        ('Departed Origin Hub', 'Departed Origin Hub'),
        ('In Transit to Destination', 'In Transit to Destination'),
        ('Reached Destination Hub', 'Reached Destination Hub'),

        # Delivery Statuses
        ('Out For Delivery', 'Out For Delivery'),
        ('Delivery Attempted', 'Delivery Attempted'),
        ('Delivered', 'Delivered'),
        ('Partial Delivered', 'Partial Delivered'),

        # Exception/Problem Statuses
        ('Failed Delivery', 'Failed Delivery'),
        ('Customer Not Available', 'Customer Not Available'),
        ('Address Issue', 'Address Issue'),
        ('Refused by Customer', 'Refused by Customer'),
        ('Damaged', 'Damaged'),
        ('Lost', 'Lost'),

        # Hold/Delay Statuses
        ('On Hold', 'On Hold'),
        ('Delayed', 'Delayed'),
        ('Under Investigation', 'Under Investigation'),

        # Return/Cancellation Statuses
        ('RTO', 'RTO'),
        ('RTO In Transit', 'RTO In Transit'),
        ('RTO Delivered', 'RTO Delivered'),
        ('Cancelled', 'Cancelled'),
        ('Returned to Sender', 'Returned to Sender'),
    ]

    SHIPMENT_TYPES = [
        ('PTL', 'PTL'),  # Part Truck Load
        ('FTL', 'FTL'),  # Full Truck Load
        ('PTL-RTO', 'PTL-RTO'),
        ('FTL-RTO', 'FTL-RTO'),
        ('PTL-APT', 'PTL-APT'),  # Appointment
        ('PTL-NOR', 'PTL-NOR'),  # Normal
        ('FTL-APT', 'FTL-APT'),
        ('FTL-NOR', 'FTL-NOR'),
    ]

    SHIPMENT_MODES = [
        ('By_Road', 'By Road'),
        ('By_Air', 'By Air'),
        ('By_Train', 'By Train'),
    ]

    # Basic shipment information
    consignment_no = models.CharField(
        max_length=50,
        unique=True,
        editable=False,
        help_text="Auto-generated consignment number"
    )
    date = models.DateField(default=timezone.now)
    freight = models.DecimalField(max_digits=10, decimal_places=2)
    shipment_type = models.CharField(max_length=15, choices=SHIPMENT_TYPES)
    shipment_mode = models.CharField(
        max_length=15,
        choices=SHIPMENT_MODES,
        default='By_Road'
    )
    payment_mode = models.CharField(max_length=10, choices=PAYMENT_MODES)

    # Location details
    origin = models.CharField(max_length=100)
    origin_pin = models.CharField(max_length=6)
    destination = models.CharField(max_length=100)
    destination_pin = models.CharField(max_length=6)

    # Vehicle and vendor information
    vehicle_no = models.CharField(max_length=50)
    driver_details = models.CharField(max_length=100)
    vehicle_type = models.CharField(max_length=30, default='LCV')
    vendor = models.ForeignKey(
        VendorMaster,
        on_delete=models.CASCADE,
        related_name="shipments",
        null=True,
        blank=True
    )
    billto_customer = models.ForeignKey(
        CustomerMaster,
        on_delete=models.CASCADE,
        to_field="customer_id",
        db_column="billto_customer",
        related_name="shipments",
        null=True,
        blank=True,
    )

    # Consignor (Shipper) details
    consignor_name = models.CharField(max_length=100)
    consignor_address = models.TextField()
    consignor_gst = models.CharField(max_length=20, blank=True, null=True)
    consignor_contact = models.CharField(max_length=20)

    # Consignee (Receiver) details
    consignee_name = models.CharField(max_length=100)
    consignee_address = models.TextField()
    consignee_gst = models.CharField(max_length=20, blank=True, null=True)
    consignee_contact = models.CharField(max_length=20)

    # Reference numbers
    invoice_ref_number = models.CharField(max_length=500)
    so_number = models.CharField(max_length=500, blank=True, null=True)  # Sales Order
    ro_number = models.CharField(max_length=500, blank=True, null=True)  # Release Order
    boe_num = models.CharField(max_length=500, blank=True, null=True)  # Bill of Entry
    ewaybill_number = models.CharField(max_length=500, blank=True, null=True)
    additional_ref_number = models.CharField(max_length=500, blank=True, null=True)

    # Cargo details
    value = models.DecimalField(max_digits=12, decimal_places=2)

    # MANUAL ENTRY FIELD - NOT AUTO-CALCULATED
    total_quantity = models.IntegerField(
        default=0,
        help_text="Manual entry only - total quantity (NOT auto-calculated)",
        verbose_name="Total Quantity"
    )

    # Auto-calculated fields
    no_article = models.IntegerField(
        default=0,
        help_text="Auto-calculated - sum of all box counts from content items"
    )
    actual_weight = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.0,
        help_text="Auto-calculated - sum of all weights from content items"
    )
    charged_weight = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.0,
        help_text="Auto-calculated - same as actual weight"
    )
    pack_type = models.CharField(max_length=50)

    # Dimension details
    length_ft = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    width_ft = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    height = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_dfc = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    # Status and tracking
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='Booked')
    pickedup_date = models.DateField(default=timezone.now, null=True, blank=True)
    estimated_delivery_date = models.DateField(null=True, blank=True)
    delivery_date = models.DateField(blank=True, null=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Proof of Delivery
    pod_scan = models.FileField(upload_to='pod_scans/', blank=True, null=True)
    pod_link = models.URLField(blank=True, null=True)

    # Appointment delivery
    appointment_delivery = models.BooleanField(default=False)
    appointment_date = models.DateField(blank=True, null=True)

    # Additional information
    remark = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Shipment"
        verbose_name_plural = "Shipments"
        ordering = ['-date', '-id']

    def save(self, *args, **kwargs):
        """
        Custom save method that:
        1. Generates consignment number for new shipments
        2. Calculates total_dfc if not provided
        3. PRESERVES manual total_quantity (does not auto-calculate)
        """
        # Generate consignment number for new shipments
        if not self.pk and not self.consignment_no:
            self.consignment_no = self._generate_consignment_number()

        # Calculate total_dfc if not provided
        if not self.total_dfc:
            self.total_dfc = self.width_ft * self.length_ft * self.height

        # NOTE: total_quantity is preserved as manual entry - NOT auto-calculated here

        super().save(*args, **kwargs)

    def _generate_consignment_number(self):
        """
        Generate unique consignment number with format: YYYY0000001
        - YYYY: 4-digit current year
        - 0000001: 7-digit sequential number starting from 0000001
        - Resets to 0000001 when new year starts
        - Continues sequentially within the same year up to 9999999
        """
        from django.db.models import Max
        import re

        current_year = timezone.now().year
        year_prefix = str(current_year)

        # Find the highest consignment number for the current year
        # Pattern: YYYY followed by exactly 7 digits
        year_pattern = f"{year_prefix}"

        # Get all shipments for current year and extract the numeric part
        existing_shipments = Shipment.objects.filter(
            consignment_no__startswith=year_prefix,
            consignment_no__regex=r'^' + year_prefix + r'\d{7}$'  # Exactly 7 digits after year
        ).values_list('consignment_no', flat=True)

        if existing_shipments:
            # Extract numeric parts and find the maximum
            numeric_parts = []
            for consignment_no in existing_shipments:
                numeric_part = consignment_no[4:]  # Remove year prefix (4 digits)
                if numeric_part.isdigit() and len(numeric_part) == 7:
                    numeric_parts.append(int(numeric_part))

            if numeric_parts:
                last_number = max(numeric_parts)
                new_number = last_number + 1

                # Handle rollover case (though unlikely to reach 9999999)
                if new_number > 9999999:
                    # This is a very edge case - you might want to handle this differently
                    # For now, we'll start from 1 again (or you could throw an exception)
                    new_number = 1
            else:
                new_number = 1
        else:
            # No shipments found for current year, start with 1
            new_number = 1

        # Generate the consignment number with proper formatting
        consignment_number = f"{year_prefix}{new_number:07d}"

        # Double-check uniqueness (safety measure)
        while Shipment.objects.filter(consignment_no=consignment_number).exists():
            new_number += 1
            if new_number > 9999999:
                new_number = 1  # Reset or handle as per business logic
            consignment_number = f"{year_prefix}{new_number:07d}"

        return consignment_number
        
        
    def update_calculated_fields(self):
        """
        Recalculate ONLY auto-calculated fields based on Content items:
        - no_article: sum of count_of_box from all Content items
        - actual_weight: sum of box_weight from all Content items
        - charged_weight: same as actual_weight

        IMPORTANT: total_quantity is NOT updated here - it remains manual entry only
        """
        contents = self.boxes.all()

        if contents.exists():
            # Calculate totals using aggregation
            aggregated_data = contents.aggregate(
                total_weight=Sum('box_weight'),
                total_boxes=Sum('count_of_box'),
            )

            # Update ONLY auto-calculated fields
            self.actual_weight = aggregated_data['total_weight'] or 0
            self.charged_weight = self.actual_weight  # Same as actual weight
            self.no_article = aggregated_data['total_boxes'] or 0

        else:
            # No content items, reset auto-calculated fields to zero
            self.actual_weight = 0
            self.charged_weight = 0
            self.no_article = 0

        # Save with specific fields to avoid recursion
        # EXPLICITLY EXCLUDE total_quantity from auto-update
        self.save(update_fields=['actual_weight', 'charged_weight', 'no_article'])

        print(
            f"Updated shipment {self.id}: articles={self.no_article}, weight={self.actual_weight}, total_quantity={self.total_quantity} (manual)")

    def update_calculated_fields_preserve_manual(self, preserve_total_quantity=None):
        """
        Enhanced version that explicitly preserves manual total_quantity
        Use this method when you want to ensure total_quantity is never touched
        """
        # Store the current total_quantity before any operations
        if preserve_total_quantity is not None:
            manual_total_quantity = preserve_total_quantity
        else:
            manual_total_quantity = self.total_quantity

        # Update calculated fields
        self.update_calculated_fields()

        # Restore manual total_quantity if it was changed
        if self.total_quantity != manual_total_quantity:
            self.total_quantity = manual_total_quantity
            self.save(update_fields=['total_quantity'])
            print(f"Restored manual total_quantity to: {self.total_quantity}")

    @property
    def total_volume(self):
        """Calculate total volume from all content items"""
        contents = self.boxes.all()
        if contents.exists():
            total = 0
            for content in contents:
                item_volume = content.volume_per_box or 0
                total += item_volume * content.count_of_box
            return round(total, 2)
        return 0.00

    @property
    def is_total_quantity_manual(self):
        """Property to check if total_quantity is set as manual entry"""
        return True  # Always True - this field is always manual

    def get_content_items_count(self):
        """Helper method to get actual number of content items (for reference only)"""
        return self.boxes.count()

    def __str__(self):
        return f"{self.consignment_no} - {self.origin} to {self.destination}"


class Content(models.Model):
    """Content/Package details within a shipment"""

    shipment = models.ForeignKey(
        Shipment,
        on_delete=models.CASCADE,
        related_name='boxes',
        help_text="Parent shipment for this content item"
    )
    batch_id = models.CharField(
        max_length=60,
        unique=True,
        editable=False,
        help_text="Auto-generated batch ID"
    )
    count_of_box = models.PositiveIntegerField(default=1)
    box_weight = models.DecimalField(max_digits=10, decimal_places=2)
    box_height = models.DecimalField(max_digits=8, decimal_places=2)
    box_length = models.DecimalField(max_digits=8, decimal_places=2)
    box_width = models.DecimalField(max_digits=8, decimal_places=2)

    # Timestamps
    # created_at = models.DateTimeField(auto_now_add=True)
    # updated_at = models.DateTimeField(auto_now=True)

    created_at = models.DateTimeField(default=timezone.now)  # Changed from auto_now_add=True
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Content Item"
        verbose_name_plural = "Content Items"
        ordering = ['batch_id']

    @property
    def volume_per_box(self):
        """Calculate volume per individual box in CFT"""
        if all([self.box_length, self.box_width, self.box_height]):
            # Convert from cm³ to CFT (1 CFT = 28316.8 cm³)
            # Convert all to Decimal to avoid mixing types
            from decimal import Decimal

            volume_cm3 = self.box_length * self.box_width * self.box_height
            cft_conversion = Decimal('28316.8')  # Convert to Decimal
            volume_cft = volume_cm3 / cft_conversion
            return float(volume_cft.quantize(Decimal('0.01')))  # Return as float with 2 decimal places
        return 0.0

    @property
    def total_volumetric(self):
        """Calculate total volumetric weight (cm³) for all boxes"""
        if all([self.box_length, self.box_width, self.box_height]):
            volume_per_box = self.box_length * self.box_width * self.box_height
            total_volume = volume_per_box * self.count_of_box
            return float(total_volume)  # Convert to float for consistency
        return 0.0

    def save(self, *args, **kwargs):
        # Generate batch_id if not exists
        if not self.batch_id and self.shipment:
            self.batch_id = self._generate_batch_id()

        super().save(*args, **kwargs)

        # Update parent shipment totals after save
        if hasattr(self.shipment, 'update_calculated_fields'):
            self.shipment.update_calculated_fields()

    def _generate_batch_id(self):
        """Generate unique batch ID for this content item"""
        existing_count = Content.objects.filter(shipment=self.shipment).count()
        line_number = existing_count + 1
        return f"{self.shipment.consignment_no}-{line_number:02d}"

    def delete(self, *args, **kwargs):
        shipment = self.shipment
        super().delete(*args, **kwargs)
        # Update parent shipment totals after delete
        if hasattr(shipment, 'update_calculated_fields'):
            shipment.update_calculated_fields()

    def __str__(self):
        return f"{self.batch_id} - {self.count_of_box} boxes"


class Manifest(models.Model):
    """Manifest for grouping shipments"""

    manifest_id = models.CharField(
        max_length=100,
        unique=True,
        editable=False,
        help_text="Auto-generated manifest ID"
    )
    shipments = models.ManyToManyField(
        Shipment,
        related_name='manifests',
        help_text="Shipments included in this manifest"
    )

    # Summary fields
    total_articles = models.IntegerField(default=0)
    total_freight = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Financial details
    base_freight = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    advance_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    additional_freight = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    balance_freight = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Vendor and route information
    vendor_name = models.ForeignKey(
        VendorMaster,
        on_delete=models.CASCADE,
        to_field="vendor_code",
        db_column="vendor_name",
        related_name="manifests",
        null=True,
        blank=True,
    )

    origin_branch = models.CharField(max_length=100, null=True, blank=True)
    destination_branch = models.CharField(max_length=100, null=True, blank=True)
    vehicle_no = models.CharField(max_length=50, null=True, blank=True)
    driver_name = models.CharField(max_length=100, blank=True)
    driver_contact = models.CharField(max_length=20, blank=True)

    document = models.FileField(
        upload_to='manifest_documents/',
        blank=True,
        null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    # created_at = models.DateTimeField(default=timezone.now)  # Changed from auto_now_add=True

    class Meta:
        verbose_name = "Manifest"
        verbose_name_plural = "Manifests"
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.manifest_id:
            self.manifest_id = self._generate_manifest_id()
        super().save(*args, **kwargs)

    def _generate_manifest_id(self):
        """Generate unique manifest ID with format: MF-YYNNN"""
        year_prefix = str(timezone.now().year)[2:]
        last_manifest = Manifest.objects.filter(
            manifest_id__startswith=f"MF-{year_prefix}"
        ).order_by('-id').first()

        if last_manifest and last_manifest.manifest_id[-3:].isdigit():
            last_number = int(last_manifest.manifest_id[-3:])
            new_number = last_number + 1
        else:
            new_number = 1

        return f"MF-{year_prefix}{new_number:03d}"

    def calculate_totals(self):
        """Calculate total freight and balance"""
        self.total_freight = self.base_freight + self.additional_freight
        self.balance_freight = self.total_freight - self.advance_amount

        # Calculate total articles from selected shipments
        if self.pk:  # Only if manifest exists
            self.total_articles = sum(
                shipment.no_article for shipment in self.shipments.all()
            )

    def __str__(self):
        return f"{self.manifest_id} - {self.vendor_name}"


class TripOutToVendor(models.Model):
    """Trip management for vendor assignments"""

    STATUS_CHOICES = [
        ('In-Progress', 'In-Progress'),
        ('Cancelled', 'Cancelled'),
        ('Closed', 'Closed'),
        ('Hold', 'Hold'),
        ('Payment Received', 'Payment Received'),
    ]

    trip_id = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
        help_text="Auto-generated trip ID"
    )
    vendor = models.ForeignKey(
        VendorMaster,
        on_delete=models.CASCADE,
        related_name="trips"
    )

    # Vehicle and route information
    vehicle_type = models.CharField(max_length=50)
    vehicle_capacity = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        help_text="Capacity in MT"
    )
    from_location = models.CharField(max_length=255)
    destination = models.CharField(max_length=255)
    kilometer = models.DecimalField(max_digits=10, decimal_places=2)

    # Financial details
    trip_charge = models.DecimalField(max_digits=12, decimal_places=2)
    additional_charge = models.DecimalField(max_digits=12, decimal_places=2, default=0.0)
    total_bill_amount = models.DecimalField(max_digits=12, decimal_places=2)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="In-Progress"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Trip to Vendor"
        verbose_name_plural = "Trips to Vendors"
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.trip_id:
            self.trip_id = self._generate_trip_id()

        # Auto-calculate total bill amount
        if not self.total_bill_amount:
            self.total_bill_amount = self.trip_charge + self.additional_charge

        super().save(*args, **kwargs)

    def _generate_trip_id(self):
        """Generate unique trip ID with format: TRP-YYNNN"""
        last_trip = TripOutToVendor.objects.order_by('-id').first()
        if last_trip and last_trip.trip_id[-3:].isdigit():
            last_number = int(last_trip.trip_id[-3:])
            new_number = last_number + 1
        else:
            new_number = 1
        year_prefix = str(timezone.now().year)[2:]
        return f"TRP-{year_prefix}{new_number:03d}"

    def __str__(self):
        return f"{self.trip_id} - {self.vendor.vendor_name}"
