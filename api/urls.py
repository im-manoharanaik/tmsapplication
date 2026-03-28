from django.urls import path, include
from .views import ShipmentCreateAPI, LoginAPI, ShipmentTrackingAPI

urlpatterns = [
    path('login/', LoginAPI.as_view(), name='api-login'),
    path("shipment/create/", ShipmentCreateAPI.as_view(), name="shipment-create"),
    path("shipment/track/<str:consignment_no>/", ShipmentTrackingAPI.as_view(), name="shipment-track"),
]