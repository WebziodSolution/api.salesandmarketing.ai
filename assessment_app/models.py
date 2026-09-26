from django.db import models

class AssessmentGroups(models.Model):
    agId = models.BigAutoField(primary_key=True, db_column='AG_ID')
    agGroupName = models.CharField(max_length=75, db_column='AG_GROUP_NAME')
    agClientId = models.BigIntegerField(db_column='AG_CLIENT_ID')
    agDateRegistered = models.DateTimeField(db_column='AG_DATE_REGISTERED')
    cwaEmbedding = models.JSONField(db_column='CWA_EMBEDDING', null=True, blank=True)

    class Meta:
        db_table = 'ASSESSMENT_GROUPS'
        managed = False

class AssessmentQuestionCategory(models.Model):
    aqcId = models.BigAutoField(primary_key=True, db_column='AQC_ID')
    aqcCatName = models.CharField(max_length=255, db_column='AQC_CAT_NAME', null=True, blank=True)
    aqcClientId = models.BigIntegerField(db_column='AQC_CLIENT_ID', null=True, blank=True)
    aqcEmbedding = models.JSONField(db_column='AQC_EMBEDDING', null=True, blank=True)

    class Meta:
        db_table = 'ASSESSMENT_QUESTION_CATEGORY'
        managed = False

class Assessments(models.Model):
    assId = models.BigAutoField(primary_key=True, db_column='ASS_ID')
    assName = models.CharField(max_length=255, db_column='ASS_NAME', null=True, blank=True)
    assDescription = models.TextField(db_column='ASS_DESCRIPTION', null=True, blank=True)
    assData = models.TextField(db_column='ASS_DATA', null=True, blank=True)
    assAtAnalysis = models.TextField(db_column='ASS_AT_ANALYSIS', null=True, blank=True)
    assAtCategoryPageList = models.TextField(db_column='ASS_AT_CATEGORY_PAGE_LIST', null=True, blank=True)
    assCountryList = models.TextField(db_column='ASS_COUNTRY_LIST', null=True, blank=True)
    assStatus = models.IntegerField(db_column='ASS_STATUS', default=0)
    assAtId = models.BigIntegerField(db_column='ASS_AT_ID', null=True, blank=True)
    assAtTotalQuestions = models.IntegerField(db_column='ASS_AT_TOTAL_QUESTIONS', default=0)
    assClientId = models.BigIntegerField(db_column='ASS_CLIENT_ID', null=True, blank=True)
    assCreatedDate = models.DateField(db_column='ASS_CREATED_DATE', null=True, blank=True)
    assUpdateDate = models.DateField(db_column='ASS_UPDATE_DATE', null=True, blank=True)
    assGroupId = models.BigIntegerField(db_column='ASS_GROUP_ID', default=0)
    assEmbedding = models.JSONField(db_column='ASS_EMBEDDING', null=True, blank=True)

    class Meta:
        db_table = 'ASSESSMENTS'
        managed = False

class AssessmentsAnswers(models.Model):
    aa_id = models.BigAutoField(primary_key=True, db_column='AA_ID')
    aa_as_id = models.BigIntegerField(db_column='AA_ASS_ID', default=0)
    aa_apg_id = models.BigIntegerField(db_column='AA_APG_ID', default=0)
    aa_aque_id = models.BigIntegerField(db_column='AA_QUE_ID', default=0)
    aa_answers = models.TextField(db_column='AA_ANSWERS', blank=True, null=True)
    aa_comments = models.TextField(db_column='AA_COMMENTS', blank=True, null=True)
    aa_opt_points = models.BigIntegerField(db_column='AA_OPT_POINTS', default=0)
    aa_embedding = models.JSONField(null=True, blank=True, db_column='AA_EMBEDDING')

    class Meta:
        managed = False
        db_table = 'ASSESSMENTS_ANSWERS'

class AssessmentsOptions(models.Model):
    ao_id = models.BigAutoField(primary_key=True, db_column='AO_ID')
    ao_que_id = models.BigIntegerField(db_column='AO_QUE_ID', default=0)
    ao_value = models.CharField(max_length=2000, db_column='AO_VALUE', blank=True, null=True)
    ao_description = models.CharField(max_length=2000, db_column='AO_DESCRIPTION', blank=True, null=True)
    ao_display_order = models.BigIntegerField(db_column='AO_DISPLAY_ORDER', default=0)
    ao_has_comments = models.IntegerField(db_column='AO_HAS_COMMENTS', default=0)
    ao_opt_points = models.BigIntegerField(db_column='AO_OPT_POINTS', default=0)
    ao_embedding = models.JSONField(null=True, blank=True, db_column='AO_EMBEDDING')

    class Meta:
        managed = False
        db_table = 'ASSESSMENTS_OPTIONS'

class AssessmentsOptionsColumns(models.Model):
    aoc_opt_id = models.BigAutoField(primary_key=True, db_column='AOC_OPT_ID')
    aoc_que_id = models.BigIntegerField(db_column='AOC_QUE_ID', default=0)
    aoc_value = models.CharField(max_length=2000, db_column='AOC_VALUE', blank=True, null=True)
    aoc_display_order = models.BigIntegerField(db_column='AOC_DISPLAY_ORDER', default=0)
    aoc_points = models.BigIntegerField(db_column='AOC_POINTS', default=0)
    aoc_embedding = models.JSONField(null=True, blank=True, db_column='AOC_EMBEDDING')

    class Meta:
        managed = False
        db_table = 'ASSESSMENTS_OPTIONS_COLUMNS'

class AssessmentsPages(models.Model):
    ap_id = models.BigAutoField(db_column='AP_ID', primary_key=True)
    ap_ass_id = models.BigIntegerField(db_column='AP_ASS_ID', default=0)
    ap_page_number = models.BigIntegerField(db_column='AP_PAGE_NUMBER', default=0)
    ap_page_type = models.CharField(db_column='AP_PAGE_TYPE', max_length=250, null=True, blank=True)
    apc_embedding = models.JSONField(null=True, blank=True, db_column='APG_EMBEDDING')

    class Meta:
        db_table = 'ASSESSMENTS_PAGES'
        managed = False

class AssessmentsQuestions(models.Model):
    aq_que_id = models.BigAutoField(primary_key=True, db_column='AQ_QUE_ID')
    aq_page_id = models.BigIntegerField(db_column='AQ_PAGE_ID', default=0)
    aq_type = models.CharField(max_length=250, db_column='AQ_TYPE', blank=True, null=True)
    aq_question = models.CharField(max_length=2000, db_column='AQ_QUESTION', blank=True, null=True)
    aq_display_order = models.BigIntegerField(db_column='AQ_DISPLAY_ORDER', default=0)
    aq_que_cat_id = models.BigIntegerField(db_column='AQ_QUE_CAT_ID', default=0)
    aq_embedding = models.JSONField(null=True, blank=True, db_column='AQ_EMBEDDING')

    class Meta:
        managed = False
        db_table = 'ASSESSMENTS_QUESTIONS'

class AssessmentsStatistics(models.Model):
    as_id = models.BigAutoField(primary_key=True, db_column='AS_ID')
    as_ass_id = models.BigIntegerField(db_column='AS_ASS_ID', default=0)
    as_aque_complete = models.BigIntegerField(db_column='AS_AQUE_COMPLETE', default=0)
    as_is_complete = models.BigIntegerField(db_column='AS_IS_COMPLETE', default=0)
    as_session_id = models.CharField(max_length=255, db_column='AS_SESSION_ID', blank=True, null=True)
    as_ip_address = models.CharField(max_length=255, db_column='AS_IP_ADDRESS', blank=True, null=True)
    as_date = models.DateTimeField(db_column='AS_DATE')
    as_city = models.CharField(max_length=255, db_column='AS_CITY', blank=True, null=True)
    as_state = models.CharField(max_length=255, db_column='AS_STATE', blank=True, null=True)
    as_country = models.CharField(max_length=255, db_column='AS_COUNTRY', blank=True, null=True)
    as_technology = models.CharField(max_length=255, db_column='AS_TECHNOLOGY', blank=True, null=True)
    as_sources = models.CharField(max_length=255, db_column='AS_SOURCES', blank=True, null=True)
    apc_embedding = models.JSONField(null=True, blank=True, db_column='AS_EMBEDDING')

    class Meta:
        managed = False
        db_table = 'ASSESSMENTS_STATISTICS'

class AssessmentsTemplate(models.Model):
    at_id = models.BigAutoField(primary_key=True, db_column='AT_ID')
    at_client_id = models.BigIntegerField(db_column='AT_CLIENT_ID', null=True, blank=True)
    at_name = models.CharField(max_length=255, db_column='AT_NAME', null=True, blank=True)
    at_data = models.TextField(db_column='AT_DATA', null=True, blank=True)
    at_status = models.IntegerField(db_column='AT_STATUS', default=0)
    at_create_date = models.DateField(db_column='AT_CREATE_DATE', null=True, blank=True)
    at_update_date = models.DateField(db_column='AT_UPDATE_DATE', null=True, blank=True)
    at_html = models.TextField(db_column='AT_HTML', null=True, blank=True)
    at_logic_flow = models.TextField(db_column='AT_LOGIC_FLOW', null=True, blank=True)
    at_analysis = models.TextField(db_column='AT_ANALYSIS', null=True, blank=True)
    at_category_page_list = models.TextField(db_column='AT_CATEGORY_PAGE_LIST', null=True, blank=True)
    at_total_questions = models.IntegerField(db_column='AT_TOTAL_QUESTIONS', default=0)
    at_embedding = models.JSONField(null=True, blank=True, db_column='AT_EMBEDDING')

    class Meta:
        db_table = 'ASSESSMENTS_TEMPLATE'
        managed = False