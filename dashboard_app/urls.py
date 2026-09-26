from django.urls import path
from .views import dashboard_views

urlpatterns = [
    path('getModuleList', dashboard_views.getModuleList, name='getModuleList'),
    path('getModuleDetails/<str:flag>/<int:limit>', dashboard_views.getModuleDetails, name='getModuleDetails'),
    path('myCalendarAppointmentList/<int:count>', dashboard_views.myCalendarAppointmentList, name='myCalendarAppointmentList'),
]
