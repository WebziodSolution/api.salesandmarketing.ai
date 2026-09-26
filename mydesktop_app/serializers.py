from rest_framework import serializers
from common_app.models import SurveysTemplate
from common_app.utils import display_date_time

class SurveysTemplateDto(serializers.ModelSerializer):
    stId = serializers.IntegerField(source='st_id', default=0)
    memberId = serializers.IntegerField(source='member_id', required=False)
    stName = serializers.CharField(source='st_name', allow_blank=True, allow_null=True, required=False)
    stData = serializers.CharField(source='st_data', allow_blank=True, allow_null=True, required=False)
    stStatus = serializers.IntegerField(source='st_status', default=0)
    stCreateDate = serializers.DateField(source='st_create_date', format='%m/%d/%Y', required=False)
    stUpdateDate = serializers.DateField(source='st_update_date', format='%m/%d/%Y', required=False)
    stHtml = serializers.CharField(source='st_html', allow_blank=True, allow_null=True, required=False)
    stLogicFlow = serializers.CharField(source='st_logic_flow', allow_blank=True, allow_null=True, required=False)
    stCategoryPageList = serializers.CharField(source='st_category_page_list', allow_blank=True, allow_null=True, required=False)
    stTotalQuestions = serializers.IntegerField(source='st_total_questions', default=0)
    stDescription = serializers.CharField(source='st_description', allow_blank=True, allow_null=True, required=False)
    stType = serializers.IntegerField(source='st_type', default=0)
    stSurveyAbout = serializers.CharField(source='st_survey_about', allow_blank=True, allow_null=True, required=False)
    stSurveyGoal = serializers.CharField(source='st_survey_goal', allow_blank=True, allow_null=True, required=False)
    stSurveyGoalDescription = serializers.CharField(source='st_survey_goal_description', allow_blank=True, allow_null=True, required=False)
    stNoOfQuestion = serializers.IntegerField(source='st_no_of_question', default=0, allow_null=True)
    stSurveyType = serializers.CharField(source='st_survey_type', allow_blank=True, allow_null=True, required=False)
    
    # Extra fields for DTO handling
    thumbData = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = SurveysTemplate
        fields = [
            'stId', 'memberId', 'stName', 'stData', 'stStatus', 'stCreateDate', 'stUpdateDate',
            'stHtml', 'stLogicFlow', 'stCategoryPageList', 'stTotalQuestions',
            'stDescription', 'stType', 'stSurveyAbout', 'stSurveyGoal', 'stSurveyGoalDescription',
            'stNoOfQuestion', 'stSurveyType', 'thumbData'
        ]

    def to_internal_value(self, data):
        # Handle empty strings for numeric fields to maintain parity with Java
        if 'stNoOfQuestion' in data and data['stNoOfQuestion'] == "":
            data = data.copy()
            data['stNoOfQuestion'] = 0
        return super().to_internal_value(data)

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        # Custom formatting if needed, though format in field should handle it
        if instance.st_create_date:
            ret['stCreateDate'] = display_date_time(instance.st_create_date)
        if instance.st_update_date:
            ret['stUpdateDate'] = display_date_time(instance.st_update_date)
        
        # Handle stNoOfQuestion as string if needed by Java parity
        ret['stNoOfQuestion'] = str(ret['stNoOfQuestion'])
        return ret

class SurveysTemplateListDto(serializers.ModelSerializer):
    stId = serializers.IntegerField(source='st_id')
    stName = serializers.CharField(source='st_name', allow_null=True, allow_blank=True)

    class Meta:
        model = SurveysTemplate
        fields = ['stId', 'stName']

class SurveysTemplateOnlyDataDto(serializers.ModelSerializer):
    stId = serializers.IntegerField(source='st_id')
    stData = serializers.CharField(source='st_data')

    class Meta:
        model = SurveysTemplate
        fields = ['stId', 'stData']