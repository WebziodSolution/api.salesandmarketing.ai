from rest_framework.decorators import api_view, permission_classes
from common_app.custom_permissions import WhitelistPermission
from rest_framework import status
from django.conf import settings
from common_app.models import ClientWebsitesAnalytics
from common_app.utils import get_final_tenant_id, display_date_time, api_response, get_client_id_by_tenant_id
from common_app.decrypt_string import DecryptString
from pymongo import MongoClient
import logging
import datetime

logger = logging.getLogger(__name__)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getAllAnalyticsWebsites(request):
    final_tenant_id = get_final_tenant_id(request=request)
    try:
        websites = ClientWebsitesAnalytics.objects.filter(cwa_client_id=get_client_id_by_tenant_id(final_tenant_id))
        website_list = []
        for w in websites:
            website_list.append({
                "cwaId": w.cwa_id,
                "clientId": w.cwa_client_id,
                "websiteUrl": w.cwa_website_url,
                "analyticsWebId": w.cwa_analytics_web_id,
                "cwaGenerationDate": display_date_time(w.cwa_generation_date)
            })

        return api_response(status.HTTP_200_OK, "Fetched successfully", {"websiteList": website_list})
    except Exception as e:
        logger.error(f"[ tenantId : {final_tenant_id} ] getAllAnalyticsWebsites Error : {str(e)}")
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Error encountered while fetching websites", {})

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def saveAnalyticsWebsite(request):
    final_tenant_id = get_final_tenant_id(request=request)
    try:
        website_url = request.data.get('websiteUrl')

        # Uniqueness checks
        existing = ClientWebsitesAnalytics.objects.filter(cwa_website_url=website_url).first()
        www_existing = ClientWebsitesAnalytics.objects.filter(cwa_website_url=f"www.{website_url}").first()

        if existing or www_existing:
            return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "This URL is already in use by other account.", {"error": "This URL is already in use by other account."})

        if website_url.startswith("www."):
            without_www = website_url[4:]
            existing_without = ClientWebsitesAnalytics.objects.filter(cwa_website_url=without_www).first()
            if existing_without:
                return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "This URL is already in use by other account.", {"error": "This URL is already in use by other account."})

        # Generate analyticsWebId
        web_id = DecryptString.set_enc_dec_user(f"{website_url}_{final_tenant_id}", "", "Y")

        cwa = ClientWebsitesAnalytics.objects.create(
            cwa_client_id=get_client_id_by_tenant_id(final_tenant_id),
            cwa_website_url=website_url,
            cwa_analytics_web_id=web_id,
            cwa_generation_date=datetime.datetime.now()
        )

        return api_response(status.HTTP_200_OK, "Saved successfully", {
            "websiteAnalyticsData": {
                "cwaId": cwa.cwa_id,
                "clientId": cwa.cwa_client_id,
                "websiteUrl": cwa.cwa_website_url,
                "analyticsWebId": cwa.cwa_analytics_web_id,
                "cwaGenerationDate": display_date_time(cwa.cwa_generation_date)
            }
        })

    except Exception as e:
        logger.error(f"[ tenantId : {final_tenant_id} ] SaveAnalyticsWebsite Error : {str(e)}")
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Error encountered while saving website", {})

@api_view(['DELETE'])
@permission_classes([WhitelistPermission])
def deleteAnalyticsWebsite(request):
    final_tenant_id = get_final_tenant_id(request=request)
    try:
        website_id = request.GET.get('id')
        website = ClientWebsitesAnalytics.objects.filter(cwa_id=website_id).first()
        
        if website:
            analytics_web_id = website.cwa_analytics_web_id
            
            # Delete from MongoDB
            mongo_settings = getattr(settings, 'MONGODB_SETTINGS', {})
            if mongo_settings:
                try:
                    client = MongoClient(mongo_settings['uri'])
                    db = client[mongo_settings['database']]
                    db.analytics_events.delete_many({'website_id': analytics_web_id})
                    client.close()
                except Exception as mongo_err:
                    logger.error(f"MongoDB delete error: {str(mongo_err)}")
            
            # Delete from SQL
            website.delete()
            
        return api_response(status.HTTP_200_OK, "Your Website Deleted successfully", {})
    except Exception as e:
        logger.error(f"[ tenantId : {final_tenant_id} ] DeleteAnalyticsWebsite Error : {str(e)}")
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Error encountered while deleting website", {})
