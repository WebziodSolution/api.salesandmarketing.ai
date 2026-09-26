from rest_framework import serializers
from common_app.models import (SvQuestionCategory)

class SvQuestionCategorySerializer(serializers.ModelSerializer):
    catName = serializers.CharField(source='cat_name')
    memberId = serializers.IntegerField(source='member_id', required=False, allow_null=True)

    class Meta:
        model = SvQuestionCategory
        fields = ['id', 'catName', 'memberId']

class SvQuestionCategoryResponseSerializer(serializers.ModelSerializer):
    catName = serializers.CharField(source='cat_name')

    class Meta:
        model = SvQuestionCategory
        fields = ['id', 'catName']

class DeleteSurveyCategorySerializer(serializers.Serializer):
    id = serializers.ListField(child=serializers.IntegerField())