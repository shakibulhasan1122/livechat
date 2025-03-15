from django.contrib import admin
from .models import Room, Message, DirectMessage

@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at')
    search_fields = ('name',)

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('user', 'room', 'content', 'timestamp')
    list_filter = ('room', 'user')
    search_fields = ('content',)

admin.site.register(DirectMessage)