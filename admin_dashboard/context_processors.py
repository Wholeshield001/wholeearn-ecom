from users.models import Ticket


def admin_context(request):
    """Add admin-specific context data to all admin dashboard templates"""
    context = {}
    
    # Only add ticket count if user is admin
    if request.user.is_authenticated and hasattr(request.user, 'role'):
        from users.models import User
        if request.user.role == User.ADMINISTRATOR:
            # Count open/in_progress tickets
            context['pending_tickets_count'] = Ticket.objects.filter(
                status__in=['open', 'in_progress']
            ).count()
    
    return context
