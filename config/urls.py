"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
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
from app.views import (
    battle_create,
    battle_join,
    battle_page,
    battle_progress,
    battle_start,
    battle_state,
    home,
)

urlpatterns = [
    path('', home, name='home'),
    path('battle/', battle_page, name='battle_lobby'),
    path('battle/<uuid:room_id>/', battle_page, name='battle_room'),
    path('api/battles/create/', battle_create, name='battle_create'),
    path('api/battles/<uuid:room_id>/join/', battle_join, name='battle_join'),
    path('api/battles/<uuid:room_id>/start/', battle_start, name='battle_start'),
    path('api/battles/<uuid:room_id>/progress/', battle_progress, name='battle_progress'),
    path('api/battles/<uuid:room_id>/state/', battle_state, name='battle_state'),
    path('admin/', admin.site.urls),
]
