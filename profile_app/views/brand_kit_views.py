import logging
import json
import os
import shutil
from datetime import datetime
from rest_framework.decorators import api_view
from rest_framework.renderers import JSONRenderer
from rest_framework.request import Request
from common_app.utils import api_response, get_final_tenant_id, get_client_id_by_tenant_id
from common_app.models import BrandKits
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)
ERROR_MSG = "Something went wrong."

class CustomDateJSONRenderer(JSONRenderer):
    def render(self, data, accepted_media_type=None, renderer_context=None):
        def _format_date(obj):
            if isinstance(obj, dict):
                return {k: _format_date(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [_format_date(i) for i in obj]
            elif isinstance(obj, datetime):
                return obj.strftime('%m-%d-%Y %H:%M:%S')
            # For timezone aware datetimes, could optionally convert
            # if hasattr(obj, 'isoformat') and 'time' in str(type(obj)):
            #     # naive check to handle datetime strings potentially?
            return obj

        formatted_data = _format_date(data)
        return super().render(formatted_data, accepted_media_type, renderer_context)

@api_view(['POST'])
def saveBrandData(request: Request):
    request.accepted_renderer = CustomDateJSONRenderer()
    res_body = dict()
    final_member_id = get_final_tenant_id(request=request)
    try:
        data = request.data
        brand_id = data.get('brandId', 0)

        brand_fonts = data.get('brandFonts')
        brand_fonts_str = json.dumps(brand_fonts) if brand_fonts is not None else None

        if brand_id == 0 or brand_id is None:
            brand_kit = BrandKits(
                brand_client_id=get_client_id_by_tenant_id(final_member_id),
                brand_name=data.get('brandName'),
                brand_website=data.get('brandWebsite'),
                brand_logo=data.get('brandLogo'),
                brand_colors=data.get('brandColors'),
                brand_fonts=brand_fonts_str,
                brand_created_date=timezone.now(),
                brand_updated_date=timezone.now()
            )
            brand_kit.save()
            data['brandId'] = brand_kit.brand_id # mirror returning the modified dto
        else:
            brand_kit = BrandKits.objects.filter(brand_id=brand_id).first()
            if brand_kit:
                brand_kit.brand_client_id = get_client_id_by_tenant_id(final_member_id)
                if data.get('brandName') is not None: brand_kit.brand_name = data.get('brandName')
                if data.get('brandWebsite') is not None: brand_kit.brand_website = data.get('brandWebsite')
                if data.get('brandLogo') is not None: brand_kit.brand_logo = data.get('brandLogo')
                if data.get('brandColors') is not None: brand_kit.brand_colors = data.get('brandColors')
                if data.get('brandFonts') is not None: brand_kit.brand_fonts = brand_fonts_str
                brand_kit.brand_updated_date = timezone.now()
                brand_kit.save()

        res_body['brandKit'] = data
        return api_response(200, "Brand Kit Saved Successfully", res_body)

    except Exception as e:
        logger.error(f"[ memberId : {final_member_id} ] SaveBrandKit Error : {e}")
        return api_response(500, ERROR_MSG, res_body)

@api_view(['DELETE'])
def deleteBrandData(request, brandId):
    request.accepted_renderer = CustomDateJSONRenderer()
    res_body = dict()
    final_member_id = get_final_tenant_id(request=request)
    try:
        brand_kit = BrandKits.objects.filter(brand_id=brandId).first()
        if brand_kit:
            brand_website = brand_kit.brand_website or ""

            # Replicating Java path manipulation: 
            # brandKits.getBrandWebsite().replaceAll("http://","").replaceAll("https://","").replaceAll("ftp://","").replaceAll("www.","").replaceAll("/","");
            folder_name = brand_website.replace("http://", "").replace("https://", "").replace("ftp://", "").replace("www.", "").replace("/", "")

            eas_drive_path = getattr(settings, 'EAS_DRIVE_PATH', '')
            root_path = os.path.join(eas_drive_path, str(final_member_id), "images")
            src_folder = os.path.join(root_path, folder_name)

            if os.path.exists(src_folder) and os.path.isdir(src_folder):
                shutil.rmtree(src_folder)

            brand_kit.delete()

        return api_response(200, "Brand Kit Deleted Successfully", res_body)
    except Exception as e:
        logger.error(f"[ memberId : {final_member_id} ] SaveBrandKit Error : {e}")  # Java logged 'SaveBrandKit Error' on delete
        return api_response(500, ERROR_MSG, res_body)

@api_view(['GET'])
def getBrandData(request):
    request.accepted_renderer = CustomDateJSONRenderer()
    res_body = dict()
    final_member_id = get_final_tenant_id(request=request)
    try:
        brand_kits_list = BrandKits.objects.filter(brand_client_id=get_client_id_by_tenant_id(final_member_id))
        
        brand_kits_dto_list = []
        for e in brand_kits_list:
            dto = dict()
            dto['brandId'] = e.brand_id
            dto['brandName'] = e.brand_name
            dto['brandWebsite'] = e.brand_website
            dto['brandLogo'] = e.brand_logo
            dto['brandColors'] = e.brand_colors
            
            brand_fonts_json = {}
            if e.brand_fonts:
                try:
                    brand_fonts_json = json.loads(e.brand_fonts)
                except json.JSONDecodeError:
                    pass
                    
            dto['brandFonts'] = brand_fonts_json
            brand_kits_dto_list.append(dto)
            
        res_body['brandKitsList'] = brand_kits_dto_list
        return api_response(200, "Brand Kit Fetched Successfully", res_body)
    except Exception as e:
        logger.error(f"[ memberId : {final_member_id} ] SaveBrandKit Error : {e}")  # Java logged 'SaveBrandKit Error' on list
        return api_response(500, ERROR_MSG, res_body)
