from rest_framework import serializers
from main.models import Shipment, Content


class ContentSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = Content
        fields = [
            "id",
            "count_of_box",
            "box_weight",
            "box_height",
            "box_length",
            "box_width",
        ]


class ShipmentCreateSerializer(serializers.ModelSerializer):
    boxes = ContentSerializer(many=True)

    class Meta:
        model = Shipment
        exclude = ["consignment_no", "no_article", "actual_weight", "charged_weight"]

    def create(self, validated_data):
        boxes_data = validated_data.pop("boxes")

        request = self.context.get("request")

        shipment = Shipment.objects.create(**validated_data)

        # Assign customer from logged-in user (optional)
        if request and hasattr(request.user, "company_name"):
            shipment.billto_customer = request.user.company_name
            shipment.save()

        # Create content items
        for box in boxes_data:
            Content.objects.create(shipment=shipment, **box)

        # Update calculated fields
        shipment.update_calculated_fields()

        return shipment
    

class ContentTrackingSerializer(serializers.ModelSerializer):
    volume = serializers.FloatField(source="volume_per_box", read_only=True)

    class Meta:
        model = Content
        fields = [
            "batch_id",
            "count_of_box",
            "box_weight",
            "box_length",
            "box_width",
            "box_height",
            "volume",
        ]


class ShipmentTrackingSerializer(serializers.ModelSerializer):
    boxes = ContentTrackingSerializer(many=True, read_only=True)

    class Meta:
        model = Shipment
        fields = [
            "consignment_no",
            "status",
            "origin",
            "destination",
            "consignor_name",
            "consignee_name",
            "vehicle_no",
            "driver_details",
            "freight",
            "total_quantity",
            "no_article",
            "actual_weight",
            "created_at",
            "estimated_delivery_date",
            "delivery_date",
            "boxes",
        ]