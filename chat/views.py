from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Q
import json
from .models import DirectMessage

@login_required(login_url='login')
def index(request):
    # Get all users except the current user
    users = User.objects.exclude(id=request.user.id).order_by('username')
    
    # Get the last message for each conversation
    conversations = []
    for user in users:
        last_message = DirectMessage.objects.filter(
            Q(sender=request.user, receiver=user) |
            Q(sender=user, receiver=request.user)
        ).order_by('-timestamp').first()
        
        unread_count = DirectMessage.objects.filter(
            sender=user,
            receiver=request.user,
            is_read=False
        ).count()
        
        conversations.append({
            'user': user,
            'last_message': last_message,
            'unread_count': unread_count
        })
    
    return render(request, 'chat/index.html', {
        'conversations': conversations
    })

@login_required(login_url='login')
def chat(request, username):
    other_user = get_object_or_404(User, username=username)
    if other_user == request.user:
        return redirect('chat:index')
    
    # Mark messages as read
    DirectMessage.objects.filter(
        sender=other_user,
        receiver=request.user,
        is_read=False
    ).update(is_read=True)
    
    # Get conversation messages
    messages = DirectMessage.objects.filter(
        Q(sender=request.user, receiver=other_user) |
        Q(sender=other_user, receiver=request.user)
    ).order_by('timestamp')
    
    return render(request, 'chat/chat.html', {
        'other_user': other_user,
        'messages': messages,
        'max_upload_size': settings.MAX_UPLOAD_SIZE,
        'allowed_file_types': json.dumps(settings.ALLOWED_FILE_TYPES),
    })

@login_required
@require_http_methods(['POST'])
def upload_file(request):
    try:
        file = request.FILES.get('file')
        receiver_username = request.POST.get('receiver')
        message_text = request.POST.get('message', '')

        if not file or not receiver_username:
            return JsonResponse({'error': 'File and receiver are required'}, status=400)

        # Validate file size
        if file.size > settings.MAX_UPLOAD_SIZE:
            return JsonResponse({'error': 'File size exceeds limit'}, status=400)

        # Validate file type
        file_type = file.name.split('.')[-1].lower()
        if file_type not in settings.ALLOWED_FILE_TYPES:
            return JsonResponse({'error': 'File type not allowed'}, status=400)

        receiver = User.objects.get(username=receiver_username)
        message = DirectMessage.objects.create(
            sender=request.user,
            receiver=receiver,
            content=message_text,
            file=file
        )

        return JsonResponse({
            'file_url': message.file.url,
            'file_name': message.file_name,
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def register(request):
    if request.user.is_authenticated:
        return redirect('chat:index')
        
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('chat:index')
    else:
        form = UserCreationForm()
    
    return render(request, 'chat/register.html', {'form': form})

@login_required(login_url='login')
def voice_call(request, username):
    other_user = get_object_or_404(User, username=username)
    if other_user == request.user:
        return redirect('chat:index')
    
    return render(request, 'chat/voice_call.html', {
        'other_user': other_user
    })
