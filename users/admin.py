from django.contrib import admin
from .models import User, Ticket
from unfold.admin import ModelAdmin
# Register your models here.


@admin.register(User)
class UserAdmin(ModelAdmin):
    list_display = ('email', 'first_name', 'last_name', 'role', 'is_staff', 'is_active')
    search_fields = ('email', 'first_name', 'last_name')
    list_filter = ('is_staff', 'is_active')
    ordering = ('email',)


@admin.register(Ticket)
class TicketAdmin(ModelAdmin):
    list_display = ('id', 'user', 'title', 'status', 'created_at', 'updated_at')
    search_fields = ('title', 'description', 'user__email')
    list_filter = ('status', 'created_at')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at')
