from rest_framework import serializers
from common_app.models import Language, SecurityQuestion, Country, CountryToState

class LanguageDto(serializers.ModelSerializer):
    lgId = serializers.IntegerField(source='lg_id')
    lgDisOrder = serializers.IntegerField(source='lg_dis_order', allow_null=True)
    lgLongName = serializers.CharField(source='lg_long_name', allow_null=True)
    lgName = serializers.CharField(source='lg_name', allow_null=True)

    class Meta:
        model = Language
        fields = ['lgId', 'lgDisOrder', 'lgLongName', 'lgName']

class SecurityQuestionDto(serializers.ModelSerializer):
    secId = serializers.IntegerField(source='sec_id')
    secQuestion = serializers.CharField(source='sec_question')

    class Meta:
        model = SecurityQuestion
        fields = ['secId', 'secQuestion']

class CountryDto(serializers.ModelSerializer):
    id = serializers.IntegerField(source='country_id')
    cntCode = serializers.CharField(source='cnt_code', allow_null=True)
    cntName = serializers.CharField(source='cnt_name')
    iso2 = serializers.CharField(allow_null=True)
    longName = serializers.CharField(source='long_name')
    oid = serializers.IntegerField(allow_null=True)

    class Meta:
        model = Country
        fields = ['id', 'cntCode', 'cntName', 'iso2', 'longName', 'oid']

class CountryToStateDto(serializers.ModelSerializer):
    countryToStateId = serializers.IntegerField(source='country_to_state_id')
    fkCountryId = serializers.IntegerField(source='fk_country_id')
    stateCapital = serializers.CharField(source='state_capital', allow_null=True)
    stateLong = serializers.CharField(source='state_long', allow_null=True)
    stateShort = serializers.CharField(source='state_short', allow_null=True)

    class Meta:
        model = CountryToState
        fields = ['countryToStateId', 'fkCountryId', 'stateCapital', 'stateLong', 'stateShort']
