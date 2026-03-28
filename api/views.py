from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from drf_yasg.utils import swagger_auto_schema
from .serializers import ShipmentCreateSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from rest_framework import serializers

class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()


class LoginAPI(APIView):
    permission_classes = []

    @swagger_auto_schema(request_body=LoginSerializer)
    def post(self, request):
        username = request.data.get("username")
        password = request.data.get("password")

        if not username or not password:
            return Response({
                "status": False,
                "message": "Username and password required"
            }, status=400)

        user = authenticate(request, username=username, password=password)

        if user:
            refresh = RefreshToken.for_user(user)

            return Response({
                "status": True,
                "message": "Login successful",
                "data": {
                    "access": str(refresh.access_token),
                    "refresh": str(refresh),
                    "username": user.username,
                    "role": user.role
                }
            })

        return Response({
            "status": False,
            "message": "Invalid credentials"
        }, status=401)
    
    
class ShipmentCreateAPI(APIView):

    @swagger_auto_schema(
        request_body=ShipmentCreateSerializer,
        operation_description="Create a new shipment with content boxes"
    )
    @transaction.atomic
    def post(self, request):
        serializer = ShipmentCreateSerializer(
            data=request.data,
            context={"request": request}
        )

        if serializer.is_valid():
            shipment = serializer.save()

            return Response({
                "status": True,
                "message": "Shipment created successfully",
                "data": {
                    "id": shipment.id,
                    "consignment_no": shipment.consignment_no
                }
            }, status=status.HTTP_201_CREATED)

        return Response({
            "status": False,
            "errors": serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    

from rest_framework.permissions import AllowAny
from django.shortcuts import get_object_or_404
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status

from .serializers import ShipmentTrackingSerializer


class ShipmentTrackingAPI(APIView):
    permission_classes = [AllowAny]  # Public tracking

    @swagger_auto_schema(
        operation_description="Track shipment using consignment number"
    )
    def get(self, request, consignment_no):
        shipment = get_object_or_404(
            Shipment,
            consignment_no=consignment_no
        )

        serializer = ShipmentTrackingSerializer(shipment)

        return Response({
            "status": True,
            "message": "Shipment details fetched",
            "data": serializer.data
        }, status=status.HTTP_200_OK)