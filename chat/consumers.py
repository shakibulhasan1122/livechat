import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import DirectMessage
from django.contrib.auth.models import User

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        if self.scope["user"].is_anonymous:
            await self.close()
            return

        # Create a notification group for this user
        self.notification_group_name = f'notifications_{self.scope["user"].username}'

        # Join notification group
        await self.channel_layer.group_add(
            self.notification_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        # Leave notification group
        if hasattr(self, 'notification_group_name'):
            await self.channel_layer.group_discard(
                self.notification_group_name,
                self.channel_name
            )

    async def notify(self, event):
        # Send notification to WebSocket
        await self.send(text_data=json.dumps(event))

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Check if user is authenticated
        if self.scope["user"].is_anonymous:
            await self.close()
            return

        # Get the other user's username from the URL
        self.other_username = self.scope['url_route']['kwargs']['username']
        
        try:
            # Get the other user
            self.other_user = await self.get_user(self.other_username)
            if not self.other_user:
                await self.close()
                return
        except User.DoesNotExist:
            await self.close()
            return

        # Create a unique room name for these two users
        users = sorted([self.scope["user"].username, self.other_username])
        self.room_group_name = f'chat_{users[0]}_{users[1]}'

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        # Leave room group
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    async def receive(self, text_data):
        if self.scope["user"].is_anonymous:
            await self.close()
            return

        text_data_json = json.loads(text_data)
        message = text_data_json.get('message', '')
        username = text_data_json['username']
        file_url = text_data_json.get('file_url')
        file_name = text_data_json.get('file_name')

        # Verify the username matches the authenticated user
        if username != self.scope["user"].username:
            await self.close()
            return

        # Save message to database
        if message or file_url:
            saved_message = await self.save_message(message, file_url, file_name)

        # Send message to room group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': message,
                'username': username,
                'file_url': file_url,
                'file_name': file_name,
            }
        )

        # Send notification to the other user
        notification_group_name = f'notifications_{self.other_username}'
        await self.channel_layer.group_send(
            notification_group_name,
            {
                'type': 'notify',
                'sender': username,
                'message': message if len(message) <= 50 else message[:47] + "...",
                'timestamp': saved_message.timestamp.strftime("%I:%M %p"),
            }
        )

    async def chat_message(self, event):
        message = event.get('message', '')
        username = event['username']
        file_url = event.get('file_url')
        file_name = event.get('file_name')

        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'message': message,
            'username': username,
            'file_url': file_url,
            'file_name': file_name,
        }))

    @database_sync_to_async
    def get_user(self, username):
        try:
            return User.objects.get(username=username)
        except User.DoesNotExist:
            return None

    @database_sync_to_async
    def save_message(self, message, file_url=None, file_name=None):
        return DirectMessage.objects.create(
            sender=self.scope["user"],
            receiver=self.other_user,
            content=message,
            file_name=file_name
        )

class VoiceCallConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Check if user is authenticated
        if self.scope["user"].is_anonymous:
            await self.close()
            return

        # Get the other user's username from the URL
        self.other_username = self.scope['url_route']['kwargs']['username']
        
        try:
            # Get the other user
            self.other_user = await self.get_user(self.other_username)
            if not self.other_user:
                await self.close()
                return
                
            # Create a unique room name for this call (sorted usernames to ensure same room both ways)
            usernames = sorted([self.scope["user"].username, self.other_username])
            self.room_group_name = f'voice_call_{usernames[0]}_{usernames[1]}'
            
            # Initialize last_offer attribute
            self.last_offer = None
            
            # Join room group
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            
            await self.accept()
            
            # Check if there's an active call in this room
            # This is useful when a user joins from a notification
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'check_active_call',
                    'username': self.scope["user"].username
                }
            )
            
        except Exception as e:
            print(f"Error in VoiceCallConsumer connect: {e}")
            await self.close()
    
    async def disconnect(self, close_code):
        # Leave room group
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
    
    # Receive message from WebSocket
    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            data['sender'] = self.scope["user"].username
            
            # Log the data for debugging
            print(f"VoiceCallConsumer received: {data}")
            
            # Validate data for offer type
            if data['type'] == 'offer' and 'offer' not in data:
                print("Error: Offer message missing offer data")
                return
                
            # Store the last offer for reconnecting users
            if data['type'] == 'offer':
                self.last_offer = data['offer']
                print(f"Stored last offer from {self.scope['user'].username}")
                
            # Send message to room group
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'signal_message',
                    'data': data
                }
            )
            
            # If this is an offer (new call), send a notification to the other user
            if data['type'] == 'offer' and hasattr(self, 'other_user'):
                notification_group_name = f'notifications_{self.other_username}'
                await self.channel_layer.group_send(
                    notification_group_name,
                    {
                        'type': 'notify',
                        'notification_type': 'incoming_call',
                        'from_user': self.scope['user'].username
                    }
                )
            
            # If this is a call end message, also send a notification to the other user
            elif data['type'] == 'call-ended' and hasattr(self, 'other_user'):
                notification_group_name = f'notifications_{self.other_username}'
                await self.channel_layer.group_send(
                    notification_group_name,
                    {
                        'type': 'notify',
                        'message': f"Missed voice call from {self.scope['user'].username}",
                        'notification_type': 'missed_call',
                        'from_user': self.scope['user'].username
                    }
                )
                
        except Exception as e:
            print(f"Error in VoiceCallConsumer receive: {e}")
    
    # Receive message from room group
    async def signal_message(self, event):
        data = event['data']
        
        # Log the data for debugging
        print(f"VoiceCallConsumer signal_message: {data}")
        
        # Send message to WebSocket only if it's not from the same user
        if data['sender'] != self.scope["user"].username:
            # Remove sender before sending to client
            sender = data.pop('sender')
            await self.send(text_data=json.dumps(data))
            # Restore sender for other consumers
            data['sender'] = sender
    
    # Check for active calls
    async def check_active_call(self, event):
        # Only the caller should respond to this
        if event['username'] != self.scope["user"].username and hasattr(self, 'last_offer') and self.last_offer:
            print(f"Resending last offer to {event['username']}")
            # Resend the last offer to the user who just joined
            await self.send(text_data=json.dumps({
                'type': 'offer',
                'offer': self.last_offer
            }))
        else:
            print(f"No active call to resend to {event['username']}")
    
    @database_sync_to_async
    def get_user(self, username):
        try:
            return User.objects.get(username=username)
        except User.DoesNotExist:
            return None 