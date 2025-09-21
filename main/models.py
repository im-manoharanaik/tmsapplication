from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.exceptions import ValidationError
import uuid
from django.utils import timezone
from django.contrib.auth.hashers import make_password
from django.db.models import Sum

class CustomerMaster(models.Model):
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

    gstn = models.CharField(max_length=20, blank=True, null=True)
    pan = models.CharField(max_length=20, blank=True, null=True)
    cin = models.CharField(max_length=30, blank=True, null=True)

    contact_person = models.CharField(max_length=100)
    contact_number = models.CharField(max_length=20)
    email_id = models.EmailField()

    contract_date_from = models.DateField()
    contract_date_to = models.DateField()

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Active')

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.customer_id:
            self.customer_id = self.generate_customer_id()
        super().save(*args, **kwargs)

    def generate_customer_id(self):
        return f"CUST-{uuid.uuid4().hex[:6].upper()}"

    def __str__(self):
        return f"{self.company_name} ({self.customer_id})"


class Branch(models.Model):
    branch_code = models.CharField(max_length=20, unique=True)  # e.g., BLR001
    name = models.CharField(max_length=100)  # Branch Name
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

    def __str__(self):
        return f"{self.name} ({self.city})"


class Fleet(models.Model):
    VEHICLE_TYPE_CHOICES = [
        ('Truck', 'Truck'),
        ('Trailer', 'Trailer'),
        ('Container', 'Container'),
        ('Tempo', 'Tempo'),
        ('Van', 'Van'),
        ('Other', 'Other'),
    ]

    vehicle_number = models.CharField(max_length=20, unique=True)  # Registration Number
    vehicle_type = models.CharField(max_length=20, choices=VEHICLE_TYPE_CHOICES)
    capacity_mt = models.DecimalField(max_digits=6, decimal_places=2, help_text="Capacity in Metric Tons")
    make = models.CharField(max_length=50, blank=True, null=True)  # Manufacturer
    model = models.CharField(max_length=50, blank=True, null=True)  # Model name
    year_of_manufacture = models.PositiveIntegerField(blank=True, null=True)
    owner_name = models.CharField(max_length=100, blank=True, null=True)
    owner_contact = models.CharField(max_length=15, blank=True, null=True)
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(
        max_length=10,
        choices=[('Active', 'Active'), ('Inactive', 'Inactive')],
        default='Active'
    )

    insurance_validity = models.DateField(blank=True, null=True)
    fitness_validity = models.DateField(blank=True, null=True)
    permit_validity = models.DateField(blank=True, null=True)
    pollution_validity = models.DateField(blank=True, null=True)

    remarks = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

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
    usertype = models.CharField(max_length=10, choices=USERTYPE_CHOICES, default='Internal')

    company_name = models.ForeignKey('main.CustomerMaster', on_delete=models.CASCADE, null=True, blank=True)
    branch = models.ForeignKey('main.Branch', on_delete=models.SET_NULL, null=True, blank=True)

    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    user_status = models.CharField(max_length=8, choices=STATUS_CHOICES, default='Active')

    def save(self, *args, **kwargs):
        # If the user is being created and no password is set, assign a default password
        if not self.pk and not self.password:
            self.password = make_password('admin@2025')  # Set default password securely
        super().save(*args, **kwargs)

    def __str__(self):
        return self.username


from django.db import models
from django.utils import timezone
class Shipment(models.Model):
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
        ('PTL', 'PTL'),  # ✅ changed from LTL → PTL
        ('FTL', 'FTL'),
        ('PTL-RTO', 'PTL-RTO'),
        ('FTL-RTO', 'FTL-RTO'),
        ('PTL-APT', 'PTL-APT'),
        ('PTL-NOR', 'PTL-NOR'),
        ('FTL-APT', 'FTL-APT'),
        ('FTL-NOR', 'FTL-NOR'),
    ]

    SHIPMENT_MODES = [
        ('By_Road', 'By Road'),
        ('By_Air', 'By Air'),
        ('By_Train', 'By Train'),
    ]

    VEHICLE_TYPE = [
        ('LCV','LCV'),
        ('TATA-ACE', 'TATA-ACE'),
        ('Truck-9ft', 'Truck-9ft'),
        ('Truck-14ft', 'Truck-14ft'),
        ('Truck-17ft', 'Truck-17ft'),
        ('Truck-19ft', 'Truck-19ft'),
        ('Truck-20ft', 'Truck-20ft'),
        ('Truck-22ft', 'Truck-22ft'),
        ('Truck-24ft', 'Truck-24ft'),
        ('Truck-28ft', 'Truck-28ft'),
        ('Truck-32ft', 'Truck-32ft'),
    ]
    consignment_no = models.CharField(max_length=50, unique=True, editable=False)
    date = models.DateField(default=timezone.now)
    freight = models.DecimalField(max_digits=10, decimal_places=2)
    shipment_type = models.CharField(max_length=15, choices=SHIPMENT_TYPES)
    shipment_mode = models.CharField(max_length=15, choices=SHIPMENT_MODES, default='By_Road')
    payment_mode = models.CharField(max_length=10, choices=PAYMENT_MODES)

    origin = models.CharField(max_length=100)
    origin_pin = models.CharField(max_length=6)
    destination = models.CharField(max_length=100)
    destination_pin = models.CharField(max_length=6)

    vehicle_no = models.CharField(max_length=50)
    driver_details = models.CharField(max_length=100)

    vehicle_type = models.CharField(max_length=30, choices=VEHICLE_TYPE,default='LCV')
    vendor = models.ForeignKey("VendorMaster", on_delete=models.CASCADE, related_name="shipments", null=True, blank=True)
    billto_customer = models.ForeignKey(
        "CustomerMaster",
        on_delete=models.CASCADE,
        to_field="customer_id",
        db_column="billto_customer",
        related_name="shipments",
        null=True,
        blank=True,
    )

    # Consignor (Shipper)
    consignor_name = models.CharField(max_length=100)
    consignor_address = models.TextField()
    consignor_gst = models.CharField(max_length=20, blank=True, null=True)
    consignor_contact = models.CharField(max_length=20)

    # Consignee (Receiver)
    consignee_name = models.CharField(max_length=100)
    consignee_address = models.TextField()
    consignee_gst = models.CharField(max_length=20, blank=True, null=True)
    consignee_contact = models.CharField(max_length=20)

    # References
    invoice_ref_number = models.CharField(max_length=500)
    so_number = models.CharField(max_length=500, blank=True, null=True)   # ✅ Sales Order
    ro_number = models.CharField(max_length=500, blank=True, null=True)   # ✅ Release Order
    boe_num = models.CharField(max_length=500, blank=True, null=True)     # ✅ Bill of Entry
    ewaybill_number = models.CharField(max_length=500, blank=True, null=True)
    additional_ref_number = models.CharField(max_length=500, blank=True, null=True)

    # Cargo details
    value = models.DecimalField(max_digits=12, decimal_places=2)
    item_count = models.IntegerField(default=0)
    no_article = models.IntegerField(default=0)
    actual_weight = models.DecimalField(max_digits=12, decimal_places=2, default=0.0)
    charged_weight = models.DecimalField(max_digits=12, decimal_places=2, default=0.0)
    pack_type = models.CharField(max_length=50)

    #dimension
    length_ft = models.IntegerField(default=0)
    width_ft = models.IntegerField(default=0)
    height = models.IntegerField(default=0)
    total_dfc = models.IntegerField(default=0)

    # Status & tracking
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='Booked')
    pickedup_date = models.DateField(default=timezone.now, null=True)
    estimated_delivery_date = models.DateField(null=True, blank=True)
    delivery_date = models.DateField(blank=True, null=True)

    # Proof of Delivery
    pod_scan = models.FileField(upload_to='pod_scans/', blank=True, null=True)
    pod_link = models.URLField(blank=True, null=True)

    # Appointment delivery
    appointment_delivery = models.BooleanField(default=False)
    appointment_date = models.DateField(blank=True, null=True)

    # Extra info
    remark = models.TextField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.pk and not self.consignment_no:
            current_year = timezone.now().year
            year_prefix = str(current_year)[2:4]

            last_shipment = Shipment.objects.filter(
                consignment_no__startswith=f"SVE-{year_prefix}"
            ).order_by('-id').first()

            if last_shipment and last_shipment.consignment_no[-3:].isdigit():
                last_number = int(last_shipment.consignment_no[-3:])
                new_number = last_number + 1
            else:
                new_number = 1

            self.consignment_no = f"SVE-{year_prefix}{new_number:03d}"
            self.total_dfc = self.width_ft *self.length_ft

        super().save(*args, **kwargs)

    def __str__(self):
        return self.consignment_no

    def update_weights_and_articles(self):
        """
        Recalculate shipment weight and article count based on Content.
        """
        contents = self.boxes.all()  # 'boxes' is related_name in Content
        total_weight = contents.aggregate(Sum("box_weight"))["box_weight__sum"] or 0
        article_count = contents.count()

        # update shipment fields
        self.actual_weight = total_weight
        self.item_count = article_count
        self.no_article = article_count
        self.save(update_fields=["actual_weight", "item_count", "no_article"])

from django.db import models

class Content(models.Model):
    shipment = models.ForeignKey(
        'Shipment',
        on_delete=models.CASCADE,
        related_name='boxes'
    )
    batch_id = models.CharField(max_length=60, unique=True, editable=False)
    count_of_box = models.IntegerField(default=0)
    box_weight = models.DecimalField(max_digits=10, decimal_places=2)
    box_height = models.DecimalField(max_digits=8, decimal_places=2)
    box_length = models.DecimalField(max_digits=8, decimal_places=2)
    box_width = models.DecimalField(max_digits=8, decimal_places=2)
    box_type = models.CharField(max_length=50)
    remark = models.TextField(blank=True, null=True)
    total_volumetric = models.DecimalField(
        max_digits=12, decimal_places=2, editable=False, null=True, blank=True
    )

    def save(self, *args, **kwargs):
        # Calculate volumetric: (L x W x H)
        self.total_volumetric = self.box_length * self.box_width * self.box_height

        # Generate batch_id
        if not self.batch_id and self.shipment:
            existing_count = Content.objects.filter(shipment=self.shipment).count()
            line_number = existing_count + 1
            self.batch_id = f"{self.shipment.consignment_no}-{line_number}"

        super().save(*args, **kwargs)

        # After saving, update shipment weights/articles
        if hasattr(self.shipment, 'update_weights_and_articles'):
            self.shipment.update_weights_and_articles()

    def delete(self, *args, **kwargs):
        shipment = self.shipment
        super().delete(*args, **kwargs)
        if hasattr(shipment, 'update_weights_and_articles'):
            shipment.update_weights_and_articles()


from django.db import models
from django.utils import timezone


class Manifest(models.Model):
    manifest_id = models.CharField(max_length=100, unique=True, editable=False)
    shipments = models.ManyToManyField('Shipment', related_name='manifests')

    total_articles = models.IntegerField(default=0)
    total_freight = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Newly added fields
    advance_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    additional_freight = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    balance_freight = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    vendor_name = models.ForeignKey(
        "VendorMaster",
        on_delete=models.CASCADE,
        to_field="vendor_code",     # ✅ assuming VendorMaster has vendor_id
        db_column="vendor_name",  # ✅ column in DB
        related_name="manifests",
        null=True,
        blank=True,
    )

    origin_branch = models.CharField(max_length=100, null=True)
    destination_branch = models.CharField(max_length=100, null=True)
    vehicle_no = models.CharField(max_length=50, null=True)
    driver_name = models.CharField(max_length=100, blank=True)
    driver_contact = models.CharField(max_length=20, blank=True)
    document = models.FileField(upload_to='manifest_documents/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.manifest_id:
            year_prefix = str(timezone.now().year)[2:]
            last_manifest = Manifest.objects.filter(
                manifest_id__startswith=f"MF-{year_prefix}"
            ).order_by('-id').first()

            if last_manifest and last_manifest.manifest_id[-3:].isdigit():
                last_number = int(last_manifest.manifest_id[-3:])
                new_number = last_number + 1
            else:
                new_number = 1

            self.manifest_id = f"MF-{year_prefix}{new_number:03d}"

        super().save(*args, **kwargs)

    def __str__(self):
        return self.manifest_id


class VendorMaster(models.Model):
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

    gstn = models.CharField(max_length=20, blank=True, null=True)
    pan = models.CharField(max_length=20, blank=True, null=True)

    short_intro = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    active_till = models.DateField(blank=True, null=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="Active")

    def save(self, *args, **kwargs):
        if not self.vendor_code:
            last_vendor = VendorMaster.objects.order_by('-id').first()
            if last_vendor and last_vendor.vendor_code[-3:].isdigit():
                last_number = int(last_vendor.vendor_code[-3:])
                new_number = last_number + 1
            else:
                new_number = 1
            self.vendor_code = f"VND-{new_number:03d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.vendor_name} ({self.vendor_code})"

class TripOutToVendor(models.Model):
    STATUS_CHOICES = [
        ('In-Progress', 'In-Progress'),
        ('Cancelled', 'Cancelled'),
        ('Closed', 'Closed'),
        ('Hold', 'Hold'),
    ]

    trip_id = models.CharField(max_length=20, unique=True, editable=False)
    vendor = models.ForeignKey(VendorMaster, on_delete=models.CASCADE, related_name="trips")

    vehicle_type = models.CharField(max_length=50)
    vehicle_capacity = models.DecimalField(max_digits=6, decimal_places=2, help_text="Capacity in MT")
    from_location = models.CharField(max_length=255)
    destination = models.CharField(max_length=255)
    kilometer = models.DecimalField(max_digits=10, decimal_places=2)
    trip_charge = models.DecimalField(max_digits=12, decimal_places=2)
    additional_charge = models.DecimalField(max_digits=12, decimal_places=2, default=0.0)
    total_bill_amount = models.DecimalField(max_digits=12, decimal_places=2)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="In-Progress")

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.trip_id:
            last_trip = TripOutToVendor.objects.order_by('-id').first()
            if last_trip and last_trip.trip_id[-3:].isdigit():
                last_number = int(last_trip.trip_id[-3:])
                new_number = last_number + 1
            else:
                new_number = 1
            year_prefix = str(timezone.now().year)[2:]  # e.g. 25 for 2025
            self.trip_id = f"TRP-{year_prefix}{new_number:03d}"

        # Auto-calculate total bill if not given
        if not self.total_bill_amount:
            self.total_bill_amount = self.trip_charge + self.additional_charge

        super().save(*args, **kwargs)

    def __str__(self):
        return self.trip_id


