from django.urls import path, include
from .views import ShipmentCreateAPI, LoginAPI

urlpatterns = [
     path('login/', LoginAPI.as_view(), name='api-login'),
    path("shipment/create/", ShipmentCreateAPI.as_view(), name="shipment-create"),
]