from django.urls import path
from .views import eas_build_it_for_me_views

urlpatterns = [
    path('getListOrder', eas_build_it_for_me_views.getListOrder, name='getListOrder'),
    path('getRequestForApprovalTags', eas_build_it_for_me_views.getRequestForApprovalTags, name='getRequestForApprovalTags'),
    path('getListRequestForApproval', eas_build_it_for_me_views.getListRequestForApproval, name='getListRequestForApproval'),
    path('getOrderDetails/<int:bfmId>', eas_build_it_for_me_views.getOrderDetails, name='getOrderDetails'),
    path('approveRequest', eas_build_it_for_me_views.approveRequest, name='approveRequest'),
    path('rejectRequest', eas_build_it_for_me_views.rejectRequest, name='rejectRequest'),
    path('deleteOrder/<int:bfmId>', eas_build_it_for_me_views.deleteOrder, name='deleteOrder'),
    path('uploadFile', eas_build_it_for_me_views.uploadFile, name='uploadFile'),
    path('removeFile/<int:bfmId>/<str:fileName>', eas_build_it_for_me_views.removeFile, name='removeFile'),
    path('saveOrder', eas_build_it_for_me_views.saveOrder, name='saveOrder'),
    path('placeOrder/<int:bfmId>', eas_build_it_for_me_views.placeOrder, name='placeOrder'),
    path('getListPackage', eas_build_it_for_me_views.getListPackage, name='getListPackage'),
]
