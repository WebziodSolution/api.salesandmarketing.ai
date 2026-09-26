from django.db.models import Sum, Q
from rest_framework.decorators import api_view, permission_classes
from rest_framework import status
from django.utils import timezone
from common_app.custom_permissions import WhitelistPermission
from common_app.utils import (
    api_response, get_final_tenant_id, get_client_id_by_tenant_id
)
from common_app.models import (
    Userlist, CampaignsEmail, CampaignsSms, SpSmsPolling, Surveys, Invoices, CampaignsSendEmail, CampaignSmsReply, SpReply, SurveysStatistics, Calendar, SpQuestions, CampaignTransaction, CampaignLinks, CampaignsSmsSend, CampaignSendSms, Groups
)
from assessment_app.models import Assessments, AssessmentsStatistics

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getModuleList(request):
    """
    Retrieve statistics for various modules with nested structure.
    Path: /v1/dashboard/getModuleList
    """
    final_tenant_id = get_final_tenant_id(request=request)

    try:
        res_body = {}

        # 1. Client Contacts
        client_contacts = {}

        valid_groups = Groups.objects.values_list('grpId', flat=True)
        
        active_contact_query = Userlist.objects.filter(
            memberId=get_client_id_by_tenant_id(final_tenant_id),
            groupId__gt=0,
            groupId__in=valid_groups
        ).filter(
            Q(optId__isnull=True) | Q(optId=0)
        ).filter(
            (
                Q(status='Subscribed') &
                Q(badEmail__in=['N', 'B', 'D']) &
                ~Q(typeEmail__in=['email', 'pending'])
            ) | (
                ~Q(phoneNumber='') &
                Q(badPhoneNumber='N') &
                Q(smsStatus='Subscribed') &
                ~Q(typeSms='sms')
            )
        )
        client_contacts["active"] = active_contact_query.count()

        final_total_contact = Userlist.objects.filter(
            memberId=get_client_id_by_tenant_id(final_tenant_id),
            groupId__gt=0,
            groupId__in=valid_groups
        ).count()
        client_contacts["total"] = final_total_contact

        opt_out = {
            "email": Userlist.objects.filter(
                memberId=get_client_id_by_tenant_id(final_tenant_id),
                status='Unsubscribed'
            ).exclude(badEmail='Y').exclude(typeEmail__in=['email', 'pending']).count(),
            "sms": Userlist.objects.filter(
                memberId=get_client_id_by_tenant_id(final_tenant_id),
                smsStatus='Unsubscribed'
            ).exclude(typeSms='sms').count()
        }
        client_contacts["optOut"] = opt_out

        bad = {
            "email": Userlist.objects.filter(memberId=get_client_id_by_tenant_id(final_tenant_id), badEmail='Y').count(),
            "sms": Userlist.objects.filter(memberId=get_client_id_by_tenant_id(final_tenant_id), badPhoneNumber='Y').count()
        }
        client_contacts["bad"] = bad

        contact_status = ""
        try:
            last_invoice = Invoices.objects.filter(invTenantId=final_tenant_id).order_by('-invId').first()
            if last_invoice and last_invoice.invCurrentContacts is not None:
                if last_invoice.invCurrentContacts == final_total_contact:
                    contact_status = ""
                elif last_invoice.invCurrentContacts > final_total_contact:
                    contact_status = "down"
                else:
                    contact_status = "up"
            else:
                contact_status = "up"
        except Exception:
            pass
        client_contacts["contactStatus"] = contact_status
        res_body["clientContacts"] = client_contacts

        # 2. Email Campaigns
        email_campaigns = dict()
        email_campaigns["total"] = CampaignsEmail.objects.filter(ceClientId=get_client_id_by_tenant_id(final_tenant_id), campStatus__gt=1).count()
        avg_open_rate = "0.00%"
        try:
            camp_ids = list(CampaignsEmail.objects.filter(ceClientId=get_client_id_by_tenant_id(final_tenant_id)).values_list('campId', flat=True))
            if camp_ids:
                tot_delivered = CampaignsSendEmail.objects.filter(memberId=get_client_id_by_tenant_id(final_tenant_id), campId__in=camp_ids, isSend='Y').count()
                tot_bounce = CampaignsSendEmail.objects.filter(memberId=get_client_id_by_tenant_id(final_tenant_id), campId__in=camp_ids, isBounced='Y').count()
                total_opened = CampaignsSendEmail.objects.filter(memberId=get_client_id_by_tenant_id(final_tenant_id), campId__in=camp_ids, isRead='Y').count()

                tot_rec = tot_delivered - tot_bounce
                if total_opened != 0 and tot_rec != 0:
                    rate = (total_opened * 100.0) / tot_rec
                    avg_open_rate = f"{rate:.2f}%"
        except Exception:
            pass
        email_campaigns["averageTotalOpenRate"] = avg_open_rate
        res_body["emailCampaigns"] = email_campaigns

        # 3. SMS Campaigns
        sms_camps_ids = CampaignsSms.objects.filter(memberId=get_client_id_by_tenant_id(final_tenant_id)).exclude(smsOpenClose='close').values_list('smsId', flat=True)
        sms_campaigns = {
            "total": CampaignsSms.objects.filter(memberId=get_client_id_by_tenant_id(final_tenant_id), smsStatus__gt=1).count(),
            "totalReplies": CampaignSmsReply.objects.filter(crSmsId__in=sms_camps_ids).count()
        }
        res_body["smsCampaigns"] = sms_campaigns

        # 4. SMS Polling
        polling_ids = SpSmsPolling.objects.filter(iUserId=get_client_id_by_tenant_id(final_tenant_id)).values_list('iId', flat=True)
        total_polling_responses = 0
        for pid in polling_ids:
            total_polling_responses += SpReply.objects.filter(
                smsPollingId=pid,
                userReply__isnull=False
            ).values('toNo').distinct().count()
            
        sms_polling = {
            "total": SpSmsPolling.objects.filter(iUserId=get_client_id_by_tenant_id(final_tenant_id), iSPStatus__gt=1).count(),
            "totalResponses": total_polling_responses
        }
        res_body["smsPolling"] = sms_polling

        # 5. Surveys
        survey_ids = Surveys.objects.filter(memberId=get_client_id_by_tenant_id(final_tenant_id)).values_list('sryId', flat=True)
        surveys = {
            "total": Surveys.objects.filter(memberId=get_client_id_by_tenant_id(final_tenant_id), sryStatus__gt=0).count(),
            "totalResponses": SurveysStatistics.objects.filter(ssSryId__in=survey_ids).count()
        }
        res_body["surveys"] = surveys

        # 6. Assessment
        ass_ids = Assessments.objects.filter(assClientId=get_client_id_by_tenant_id(final_tenant_id)).values_list('assId', flat=True)
        assessment = {
            "total": Assessments.objects.filter(assClientId=get_client_id_by_tenant_id(final_tenant_id), assStatus__gt=0).count(),
            "totalResponses": AssessmentsStatistics.objects.filter(as_ass_id__in=ass_ids).count()
        }
        res_body["assessment"] = assessment

        return api_response(status.HTTP_200_OK, "Fetch Module List Successfully.", res_body)
    except Exception as e:
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))


@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getModuleDetails(request, flag, limit):
    """
    Retrieve detailed listings for modules.
    Path: /v1/dashboard/getModuleDetails/<flag>/<limit>
    """
    final_tenant_id = get_final_tenant_id(request=request)

    try:
        limit = int(limit)
        res_data = {}
        
        if flag == "contact":
            contacts = Userlist.objects.filter(memberId=get_client_id_by_tenant_id(final_tenant_id)).order_by('-emailId')[:limit]
            res_data = {
                "contactList": [{
                    "emailId": c.emailId,
                    "firstName": c.firstName,
                    "lastName": c.lastName,
                    "email": c.email if c.email else "",
                    "phoneNumber": c.phoneNumber,
                    "dateAdded": c.dateRegistered.strftime("%m-%d-%Y %H:%M:%S") if c.dateRegistered else ""
                } for c in contacts]
            }

        elif flag == "email":
            email_camps = CampaignsEmail.objects.filter(ceClientId=get_client_id_by_tenant_id(final_tenant_id), campStatus__gt=1).order_by('-campId')[:limit]
            res_data = { "emailCampaigns": [] }
            for camp in email_camps:
                # Java findByIdByOrder: order by id desc
                send_email = CampaignsSendEmail.objects.filter(campId=camp.campId).order_by('-id').first()
                camp_send_id = send_email.campSendId if send_email else 0
                
                # Filters must strictly match Java queries
                base_filter = Q(campId=camp.campId, campSendId=camp_send_id)
                
                tot_sent = CampaignsSendEmail.objects.filter(base_filter).count()
                tot_read = CampaignsSendEmail.objects.filter(base_filter, isRead='Y').count()
                tot_bounce = CampaignsSendEmail.objects.filter(base_filter, isBounced='Y').count()
                tot_delivered = CampaignsSendEmail.objects.filter(base_filter, isSend='Y').count()
                tot_unsub = CampaignsSendEmail.objects.filter(base_filter, isUnsubscribed='Y').count()
                
                # Java totClicks: campaign-wide (no campSendId filter)
                tot_clicks = CampaignLinks.objects.filter(campId=camp.campId).aggregate(Sum('linkCount'))['linkCount__sum'] or 0
                
                # Recipient count from Java logic
                tot_rec = tot_delivered - tot_bounce
                
                # Java percentage calculation with parseFloat(String.format("%.2f", ...))
                # If tot_rec is 0, it results in NaN in Java (quoted string in user snippet)
                if tot_rec > 0:
                    open_rate = round((tot_read * 100.0 / tot_rec), 2)
                    click_rate = round((tot_clicks * 100.0 / tot_rec), 2)
                else:
                    open_rate = 0
                    click_rate = 0
                
                res_data['emailCampaigns'].append({
                    "campId": camp.campId,
                    "campName": camp.campName,
                    "campSendId": camp_send_id if camp_send_id > 0 else None,
                    "totalSent": tot_sent,
                    "totalOpened": tot_read,
                    "totalOpenedPercentage": open_rate,
                    "totalClicks": tot_clicks,
                    "totalClicksPercentage": click_rate,
                    "totalBounce": tot_bounce,
                    "totalUnsubscription": tot_unsub,
                    "sendOnDate": camp.sendDate.strftime("%m/%d/%Y %H:%M:%S") if camp.sendDate else ""
                })

        elif flag == "sms":
            sms_camps = CampaignsSms.objects.filter(memberId=get_client_id_by_tenant_id(final_tenant_id), smsStatus__gt=1).order_by('-smsId')[:limit]
            res_data = { "smsCampaigns": [] }
            for s in sms_camps:
                sms_send = CampaignsSmsSend.objects.filter(smsId=s.smsId).first()
                cssd_id = sms_send.id if sms_send else 0
                
                tot_sent = CampaignSendSms.objects.filter(cssdId=cssd_id, isSend='Y').count()
                tot_delivered = CampaignSendSms.objects.filter(cssdId=cssd_id, isSend='Y', smsStatus='delivered').count()
                tot_not_sent = CampaignSendSms.objects.filter(cssdId=cssd_id, isSend='Y').filter(
                    Q(smsStatus='failed') | Q(smsStatus='') | Q(smsStatus__isnull=True)
                ).count()
                tot_undelivered = tot_sent - tot_delivered - tot_not_sent if tot_sent > 0 else 0
                
                res_data['smsCampaigns'].append({
                    "smsId": s.smsId,
                    "smsName": s.smsName,
                    "totalSent": tot_sent,
                    "totalDelivered": tot_delivered,
                    "totalNotSent": tot_not_sent,
                    "totalUndelivered": tot_undelivered,
                    "sendOnDate": s.sendDate.strftime("%m-%d-%Y %H:%M:%S") if s.sendDate else ""
                })

        elif flag == "polling":
            polling = SpSmsPolling.objects.filter(iUserId=get_client_id_by_tenant_id(final_tenant_id), iSPStatus__gt=1).order_by('-iId')[:limit]
            res_data = {
                "smsPolling": [{
                    "iid": p.iId,
                    "vheading": p.vHeading,
                    "createdDate": p.dPublishDate.strftime("%m-%d-%Y") if p.dPublishDate else "",
                    "dPublishDate": p.dPublishDate.strftime("%m-%d-%Y") if p.dPublishDate else "",
                    "totalQuestion": SpQuestions.objects.filter(iSmspollingId=p.iId).count(),
                    "totalResponses": SpReply.objects.filter(smsPollingId=p.iId, userReply__isnull=False).values('toNo').distinct().count()
                } for p in polling]
            }

        elif flag == "survey":
            survey_list = Surveys.objects.filter(memberId=get_client_id_by_tenant_id(final_tenant_id), sryStatus__gt=0).order_by('-sryId')[:limit]
            res_data = {
                "surveyList": [{
                    "sryId": s.sryId,
                    "sryName": s.sryName,
                    "sryCreatedDate": s.sryCreatedDate.strftime("%m-%d-%Y") if s.sryCreatedDate else "",
                    "totalQuestion": s.sryStTotalQuestions,
                    "totalResponses": CampaignTransaction.objects.filter(tran_campaign_id=s.sryId, tran_type='survey').order_by('-tran_id').values_list('tran_total_member', flat=True).first() or 0
                } for s in survey_list]
            }

        elif flag == "assessment":
            ass_list = Assessments.objects.filter(assClientId=get_client_id_by_tenant_id(final_tenant_id), assStatus__gt=0).order_by('-assId')[:limit]
            res_data = {
                "assessmentList": [{
                    "assId": a.assId,
                    "assName": a.assName,
                    "assCreatedDate": a.assCreatedDate.strftime("%m-%d-%Y") if a.assCreatedDate else "",
                    "totalQuestion": a.assAtTotalQuestions,
                    "totalResponses": CampaignTransaction.objects.filter(tran_campaign_id=a.assId, tran_type='assessment').order_by('-tran_id').values_list('tran_total_member', flat=True).first() or 0
                } for a in ass_list]
            }

        return api_response(status.HTTP_200_OK, "Fetch Module Details Successfully.", res_data)
    except Exception as e:
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))


@api_view(['GET'])
@permission_classes([WhitelistPermission])
def myCalendarAppointmentList(request, count):
    """
    Retrieve upcoming calendar appointments.
    Path: /v1/dashboard/myCalendarAppointmentList/<count>
    """
    final_tenant_id = get_final_tenant_id(request=request)

    try:
        limit = int(count)
        now = timezone.now()
        appointments = Calendar.objects.filter(calMemberId=get_client_id_by_tenant_id(final_tenant_id), calStartDateTime__gt=now).order_by('calStartDateTime')[:limit]
        
        appointment_list = []
        for appt in appointments:
            diff = appt.calStartDateTime - now
            hours, remainder = divmod(diff.total_seconds(), 3600)
            minutes, _ = divmod(remainder, 60)
            remaining_time = f"{int(hours):02d}:{int(minutes):02d}"
            
            appointment_list.append({
                "title": appt.calTitle,
                "remainingTime": remaining_time
            })
        
        res_data = {'appointmentList': appointment_list}
        return api_response(status.HTTP_200_OK, "Calendar Appointment List Successfully.", res_data)
    except Exception as e:
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))
