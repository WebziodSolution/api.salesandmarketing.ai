from django.urls import path
from api_app.views.payment_gateway_views import (
    createPaymentProfile,
    getPaymentProfile,
    deletePaymentProfile,
    updatePaymentProfile,
    chargePaymentProfile,
    updateBillingDetails
)

from api_app.views.salesforce_views import (
    connectToSalesforce,
    callBackFromOAuth
)
from api_app.views.zoom_views import (
    zoomLogin,
    zoomOauth,
    zoomLogout,
    getZoomAuthentication,
    addZoomMeeting
)
from api_app.views.google_calendar_views import (
    googleCalendarSignIn,
    oauth as google_oauth,
    getEvent,
    deleteEvent,
    getEventList,
    saveEvent,
    revoke,
    getUserTimezone,
    getEmail
)
from api_app.views.outlook_calendar_views import (
    outlookCalendarSignIn,
    oauth as outlook_oauth,
    getEventList as getOutlookEventList,
    deleteEvent as deleteOutlookEvent,
    saveEvent as saveOutlookEvent,
    revoke as outlookRevoke,
    getEmail as getOutlookEmail
)
from api_app.views.quickbook_views import (
    ConnectToQuickbooksView,
    OAuth2RedirectView
)
from api_app.views import google_authenticator_views

urlpatterns = [
    path('paymentGateway/createPaymentProfile', createPaymentProfile),
    path('paymentGateway/getPaymentProfile', getPaymentProfile),
    path('paymentGateway/deletePaymentProfile', deletePaymentProfile),
    path('paymentGateway/updatePaymentProfile', updatePaymentProfile),
    path('paymentGateway/chargePaymentProfile', chargePaymentProfile),
    path('paymentGateway/updateBillingDetails', updateBillingDetails),
    path('salesforce/connectToSalesforce', connectToSalesforce),
    path('salesforce/oauth2redirect', callBackFromOAuth),
    path('zoom/zoomLogin', zoomLogin),
    path('zoom/zoomOauth', zoomOauth),
    path('zoom/zoomLogout', zoomLogout),
    path('zoom/getZoomAuthentication', getZoomAuthentication),
    path('zoom/addZoomMeeting', addZoomMeeting),
    path('googleCalendar/googleCalendarSignIn', googleCalendarSignIn),
    path('googleCalendar/oauth', google_oauth),
    path('googleCalendar/getEvent/<str:eventId>', getEvent),
    path('googleCalendar/deleteEvent/<str:eventId>', deleteEvent),
    path('googleCalendar/getEventList', getEventList),
    path('googleCalendar/saveEvent', saveEvent),
    path('googleCalendar/revoke', revoke),
    path('googleCalendar/getUserTimezone', getUserTimezone),
    path('googleCalendar/getEmail', getEmail),
    path('outlookCalendar/outlookCalendarSignIn', outlookCalendarSignIn),
    path('outlookCalendar/oauth', outlook_oauth),
    path('outlookCalendar/getEventList', getOutlookEventList),
    path('outlookCalendar/deleteEvent/<str:eventId>', deleteOutlookEvent),
    path('outlookCalendar/saveEvent', saveOutlookEvent),
    path('outlookCalendar/revoke', outlookRevoke),
    path('outlookCalendar/getEmail', getOutlookEmail),
    path('quickbook/connectToQuickbooks', ConnectToQuickbooksView.as_view()),
    path('quickbook/oauth2redirect', OAuth2RedirectView.as_view()),
    path('authenticator/generate', google_authenticator_views.generate),
    path('authenticator/verify', google_authenticator_views.verify),
]
