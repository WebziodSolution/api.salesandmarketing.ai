from django.urls import path
from .views.easdrive_views import (
    GetFoldersView, CreateFolderView, CopyFoldersAndFilesView,
    DeleteFoldersAndFilesView, CutFoldersAndFilesView, GetImagesView,
    FileUploadView, ImportImageFromUrlView, ImportImageFromAiUrlView,
    ImportVideoImageFromUrlView, EditImageView, AiTransactionsView
)
from .views.google_drive_views import (
    AuthenticateView, GoogleSignInView, OAuthCallbackView,
    GetListViewImagesView, GetFoldersAndFilesView, GetSearchFilesView,
    DownloadFileView
)
from .views import one_drive_views, dropbox_views

urlpatterns = [
    path('easDrive/getFolders', GetFoldersView.as_view(), name='get_folders'),
    path('easDrive/createFolder', CreateFolderView.as_view(), name='create_folder'),
    path('easDrive/copyFoldersAndFiles', CopyFoldersAndFilesView.as_view(), name='copy_folders_and_files'),
    path('easDrive/deleteFoldersAndFiles', DeleteFoldersAndFilesView.as_view(), name='delete_folders_and_files'),
    path('easDrive/cutFoldersAndFiles', CutFoldersAndFilesView.as_view(), name='cut_folders_and_files'),
    path('easDrive/getImages', GetImagesView.as_view(), name='get_images'),
    path('easDrive/uploadFile', FileUploadView.as_view(), name='upload_file'),
    path('easDrive/importImageFromUrl', ImportImageFromUrlView.as_view(), name='import_image_from_url'),
    path('easDrive/importImageFromAiUrl', ImportImageFromAiUrlView.as_view(), name='import_image_from_ai_url'),
    path('easDrive/importVideoImageFromUrl', ImportVideoImageFromUrlView.as_view(), name='import_video_image_from_url'),
    path('easDrive/editImage', EditImageView.as_view(), name='edit_image'),
    path('easDrive/aiTransactions', AiTransactionsView.as_view(), name='ai_transactions'),
    
    # Google Drive Endpoints
    path('googleDrive/authenticate', AuthenticateView.as_view(), name='google_drive_authenticate'),
    path('googleDrive/googleSignIn', GoogleSignInView.as_view(), name='google_drive_signin'),
    path('googleDrive/oauth', OAuthCallbackView.as_view(), name='google_drive_oauth'),
    path('googleDrive/getImages/<str:folder_id>', GetListViewImagesView.as_view(), name='google_drive_get_images'),
    path('googleDrive/getFolders/<str:folder_id>', GetFoldersAndFilesView.as_view(), name='google_drive_get_folders'),
    path('googleDrive/getSearchImages/<str:folder_id>/<str:search_string>', GetSearchFilesView.as_view(), name='google_drive_search'),
    path('googleDrive/getListViewImages/<str:folder_id>', GetListViewImagesView.as_view(), name='google_drive_list_view'),
    path('googleDrive/downloadFile/<str:file_id>', DownloadFileView.as_view(), name='google_drive_download'),

    # OneDrive Endpoints
    path('onedrive/authenticate', one_drive_views.AuthenticateView.as_view(), name='onedrive_authenticate'),
    path('onedrive/onedriveSignIn', one_drive_views.OneDriveSignInView.as_view(), name='onedrive_signin'),
    path('onedrive/oAuth', one_drive_views.OAuthCallbackView.as_view(), name='onedrive_oauth'),
    path('onedrive/getFolders', one_drive_views.GetFoldersView.as_view(), name='onedrive_get_folders'),
    path('onedrive/getImages', one_drive_views.GetImagesView.as_view(), name='onedrive_get_images'),
    path('onedrive/search', one_drive_views.SearchView.as_view(), name='onedrive_search'),
    path('onedrive/download', one_drive_views.DownloadView.as_view(), name='onedrive_download'),

    # Dropbox Endpoints
    path('dropbox/authenticate', dropbox_views.AuthenticateView.as_view(), name='dropbox_authenticate'),
    path('dropbox/dropboxSignIn', dropbox_views.DropboxSignInView.as_view(), name='dropbox_signin'),
    path('dropbox/oauth', dropbox_views.OAuthCallbackView.as_view(), name='dropbox_oauth'),
    path('dropbox/getFolders', dropbox_views.GetFoldersView.as_view(), name='dropbox_get_folders'),
    path('dropbox/getImages/', dropbox_views.GetImagesView.as_view(), name='dropbox_get_images'),
    path('dropbox/search', dropbox_views.SearchView.as_view(), name='dropbox_search'),
    path('dropbox/download', dropbox_views.DownloadView.as_view(), name='dropbox_download'),
]
