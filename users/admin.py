from django.contrib import admin
from .models import User, Ticket, KYCSubmission
from unfold.admin import ModelAdmin
# Register your models here.


@admin.register(User)
class UserAdmin(ModelAdmin):
    list_display = ('email', 'unique_code', 'referral_code', 'reward_points', 'first_name', 'last_name', 'role', 'is_staff', 'is_active', 'kyc_status')
    search_fields = ('email', 'first_name', 'last_name', 'unique_code', 'referral_code')
    list_filter = ('is_staff', 'is_active', 'kyc_status', 'role')
    ordering = ('email',)
    readonly_fields = ('unique_code', 'referral_code', 'kyc_verified_at', 'kyc_submitted_at')


@admin.register(Ticket)
class TicketAdmin(ModelAdmin):
    list_display = ('id', 'user', 'title', 'status', 'created_at', 'updated_at')
    search_fields = ('title', 'description', 'user__email')
    list_filter = ('status', 'created_at')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(KYCSubmission)
class KYCSubmissionAdmin(ModelAdmin):
    list_display = ('id', 'user', 'user_type', 'status', 'created_at', 'verified_at')
    search_fields = ('user__email', 'business_name', 'contact_number')
    list_filter = ('status', 'user_type', 'created_at')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at', 'verified_at', 'verified_by')
    
    def get_readonly_fields(self, request, obj=None):
        """Make fields readonly for approved/rejected submissions"""
        readonly = list(self.readonly_fields)
        if obj and obj.status != 'pending':
            readonly.extend(['user_type', 'business_name', 'contact_number', 'business_address', 'cac_document'])
        return readonly

