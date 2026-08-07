from django.urls import path,re_path
from .consumers import MyConsumer

websocket_urls = [
    path("ws/Meeting/<str:id>",MyConsumer.as_asgi())
]