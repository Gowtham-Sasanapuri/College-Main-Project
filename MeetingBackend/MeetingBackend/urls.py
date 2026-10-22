"""
URL configuration for MeetingBackend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from Meeting import views, room_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path("createLink/", views.CreateLink),
    path("JoinMeeting/", views.SearchMeeting),
    path("endMeeting/", views.EndMeeting),
    path("transcript/edit/<int:entry_id>/", views.UpdateTranscript),
    path("transcript/<str:meeting_id>/", views.GetTranscript),

    # Room Meeting endpoints (addition)
    path("roomMeeting/create/", room_views.CreateRoomMeeting),
    path("roomMeeting/process/", room_views.ProcessRoomAudio),
    path("roomMeeting/transcript/<int:entry_id>/", room_views.UpdateRoomTranscript),
    path("roomMeeting/generateSummary/", room_views.GenerateRoomSummary),

    # Follow-Up Question endpoints (Video and general)
    path("meeting/followup/", views.AskFollowUpQuestion),
    path("meeting/followup/<str:meeting_id>/", views.GetFollowUpHistory),
    path("meeting/details/<str:meeting_id>/", views.GetMeetingDetails),

    # Room Meeting follow-up endpoints
    path("roomMeeting/followup/", room_views.AskRoomFollowUpQuestion),
    path("roomMeeting/followup/<str:meeting_id>/", room_views.GetRoomFollowUpHistory),
    path("roomMeeting/details/<str:meeting_id>/", room_views.GetRoomMeetingDetails),

    # Participant Management endpoints
    path("meeting/participants/", views.RegisterParticipant),
    path("meeting/participants/<str:meeting_id>/", views.GetMeetingParticipants),
    path("roomMeeting/participants/", room_views.SetupRoomParticipants),
    path("roomMeeting/participants/<str:meeting_id>/", room_views.GetRoomParticipants),

    # Report Data & PDF Download endpoints
    path("meeting/report/<str:meeting_id>/", views.GetMeetingReportData),
    path("meeting/download-report/<str:meeting_id>/", views.DownloadMeetingReport),
    path("roomMeeting/report/<str:meeting_id>/", room_views.GetRoomMeetingReportData),
    path("roomMeeting/download-report/<str:meeting_id>/", room_views.DownloadRoomMeetingReport),

    # Email Delivery endpoints
    path("meeting/send-report/", views.SendMeetingReport),
    path("roomMeeting/send-report/", room_views.SendRoomMeetingReport),
]


