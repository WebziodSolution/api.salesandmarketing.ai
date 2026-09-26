from django.urls import path
from esignature_app.views import envelope_views, recipient_views

urlpatterns = [
    path('envelope/create', envelope_views.createEnvelope, name='envelope_create'),
    path('envelope/list', envelope_views.getEnvelopes, name='envelope_list'),
    path('envelope/<int:id>', envelope_views.getEnvelopeById, name='envelope_detail'),
    path('envelope/delete', envelope_views.deleteEnvelopes, name='envelope_delete'),
    
    path('recipient/validate/<str:token>', recipient_views.validateRecipientToken, name='recipient_validate'),
    path('recipient/validate-access-code/<str:token>', recipient_views.validateAccessCode, name='recipient_validate_access_code'),
    path('recipient/status/<str:token>', recipient_views.updateStatus, name='recipient_update_status'),
    path('recipient/sign/<str:token>', recipient_views.submitSignedDocument, name='recipient_sign'),
    path('recipient/signature/adopt/<str:token>', recipient_views.adoptSignature, name='recipient_adopt_signature'),
]

