from django.urls import path
from . import views

app_name = 'chat'

urlpatterns = [
    path('', views.index, name='index'),
    path('upload/', views.upload_file, name='upload_file'),
    path('<str:username>/', views.chat, name='chat'),
    path('<str:username>/voice/', views.voice_call, name='voice_call'),
] 