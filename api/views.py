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