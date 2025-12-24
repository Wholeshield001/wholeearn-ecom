from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from .models import Ticket

User = get_user_model()


class SignUpForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-pink-200 focus:outline-none focus:ring-2 focus:ring-pink-500',
            'placeholder': 'Password',
            'minlength': '8',
        }),
        min_length=8,
        help_text='Password must be at least 8 characters long.'
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-pink-200 focus:outline-none focus:ring-2 focus:ring-pink-500',
            'placeholder': 'Confirm Password',
        }),
        label='Confirm Password'
    )
    role = forms.ChoiceField(
        choices=[
            (User.WHOLESALER, 'Wholesaler'),
            (User.RETAILER, 'Retailer'),
            (User.HOSPITAL, 'Hospital'),
            (User.PHARMACY, 'Pharmacy'),
            (User.END_USER, 'End User'),
        ],
        widget=forms.RadioSelect(attrs={
            'class': 'text-pink-500 focus:ring-pink-500',
        }),
        label='What describes you best?'
    )

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email', 'phone', 'role')
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 rounded-lg border border-pink-200 focus:outline-none focus:ring-2 focus:ring-pink-500',
                'placeholder': 'First Name',
                'required': 'required',
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 rounded-lg border border-pink-200 focus:outline-none focus:ring-2 focus:ring-pink-500',
                'placeholder': 'Last Name',
                'required': 'required',
            }),
            'email': forms.EmailInput(attrs={
                'class': 'w-full px-4 py-3 rounded-lg border border-pink-200 focus:outline-none focus:ring-2 focus:ring-pink-500',
                'placeholder': 'Email',
                'required': 'required',
            }),
            'phone': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 rounded-lg border border-pink-200 focus:outline-none focus:ring-2 focus:ring-pink-500',
                'placeholder': 'Phone Number',
                'required': 'required',
                'inputmode': 'tel',
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        password_confirm = cleaned_data.get('password_confirm')

        if password and password_confirm:
            if password != password_confirm:
                raise ValidationError('Passwords do not match.')

        return cleaned_data

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise ValidationError('An account with this email already exists.')
        return email

    def clean_phone(self):
        phone = (self.cleaned_data.get('phone') or '').strip()
        if not phone:
            raise ValidationError('Phone number is required.')
        # Basic sanity check: 7-20 digits with optional +, spaces, dashes
        import re
        if not re.fullmatch(r"[+\d][\d\s\-]{6,19}", phone):
            raise ValidationError('Enter a valid phone number.')
        return phone

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        user.is_active = False  # Account inactive until email verified
        # Save phone explicitly since model allows null/blank but we require at form level
        user.phone = self.cleaned_data.get('phone')
        if commit:
            user.save()
        return user


class LoginForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-pink-200 focus:outline-none focus:ring-2 focus:ring-pink-500',
            'placeholder': 'Email',
            'required': 'required',
        }),
        label='Email'
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-pink-200 focus:outline-none focus:ring-2 focus:ring-pink-500',
            'placeholder': 'Password',
            'required': 'required',
        }),
        label='Password'
    )
    remember_me = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'w-4 h-4 text-pink-500 focus:ring-pink-500 rounded',
        }),
        label='Remember me'
    )

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get('email')
        password = cleaned_data.get('password')

        if email and password:
            try:
                user = User.objects.get(email=email)
                if not user.check_password(password):
                    raise ValidationError('Invalid email or password.')
                if not user.is_active:
                    raise ValidationError('This account is inactive. Please contact support.')
                if not user.email_verified:
                    raise ValidationError('Please verify your email before logging in.')
            except User.DoesNotExist:
                raise ValidationError('Invalid email or password.')

        return cleaned_data


class VerifyOTPForm(forms.Form):
    otp = forms.CharField(
        max_length=6,
        min_length=6,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-pink-200 focus:outline-none focus:ring-2 focus:ring-pink-500 text-center text-2xl tracking-widest',
            'placeholder': '000000',
            'inputmode': 'numeric',
            'pattern': '[0-9]*',
            'maxlength': '6',
            'required': 'required',
        }),
        label='Enter OTP',
        error_messages={
            'required': 'OTP is required.',
            'max_length': 'OTP must be 6 digits.',
            'min_length': 'OTP must be 6 digits.',
        }
    )


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'phone')
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 rounded-lg border border-pink-200 focus:outline-none focus:ring-2 focus:ring-pink-500',
                'placeholder': 'First Name',
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 rounded-lg border border-pink-200 focus:outline-none focus:ring-2 focus:ring-pink-500',
                'placeholder': 'Last Name',
            }),
            'phone': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 rounded-lg border border-pink-200 focus:outline-none focus:ring-2 focus:ring-pink-500',
                'placeholder': 'Phone',
            }),
        }


class PasswordChangeForm(forms.Form):
    current_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-pink-200 focus:outline-none focus:ring-2 focus:ring-pink-500',
            'placeholder': 'Current Password',
            'required': 'required',
        })
    )
    new_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-pink-200 focus:outline-none focus:ring-2 focus:ring-pink-500',
            'placeholder': 'New Password',
            'required': 'required',
            'minlength': '8',
        }),
        min_length=8
    )
    new_password_confirm = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-pink-200 focus:outline-none focus:ring-2 focus:ring-pink-500',
            'placeholder': 'Confirm New Password',
            'required': 'required',
        })
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_current_password(self):
        pwd = self.cleaned_data.get('current_password')
        if not self.user.check_password(pwd):
            raise ValidationError('Current password is incorrect.')
        return pwd

    def clean(self):
        cleaned = super().clean()
        new_pwd = cleaned.get('new_password')
        new_confirm = cleaned.get('new_password_confirm')
        if new_pwd and new_confirm and new_pwd != new_confirm:
            raise ValidationError('New passwords do not match.')
        if new_pwd:
            validate_password(new_pwd, self.user)
        return cleaned


class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-pink-200 focus:outline-none focus:ring-2 focus:ring-pink-500',
            'placeholder': 'Email',
            'required': 'required',
        })
    )


class PasswordResetVerifyForm(forms.Form):
    otp = forms.CharField(
        max_length=6,
        min_length=6,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-pink-200 focus:outline-none focus:ring-2 focus:ring-pink-500 text-center text-2xl tracking-widest',
            'placeholder': '000000',
            'inputmode': 'numeric',
            'pattern': '[0-9]*',
            'maxlength': '6',
            'required': 'required',
        }),
        label='Enter OTP',
        error_messages={
            'required': 'OTP is required.',
            'max_length': 'OTP must be 6 digits.',
            'min_length': 'OTP must be 6 digits.',
        }
    )


class PasswordResetSetForm(forms.Form):
    new_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-pink-200 focus:outline-none focus:ring-2 focus:ring-pink-500',
            'placeholder': 'New Password',
            'required': 'required',
            'minlength': '8',
        }),
        min_length=8
    )
    new_password_confirm = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-pink-200 focus:outline-none focus:ring-2 focus:ring-pink-500',
            'placeholder': 'Confirm New Password',
            'required': 'required',
        })
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        pwd = cleaned.get('new_password')
        confirm = cleaned.get('new_password_confirm')
        if pwd and confirm and pwd != confirm:
            raise ValidationError('Passwords do not match.')
        if pwd:
            validate_password(pwd, self.user)
        return cleaned


class TicketForm(forms.ModelForm):
    """Form for creating support tickets"""
    class Meta:
        model = Ticket
        fields = ("title", "description")
        widgets = {
            "title": forms.TextInput(attrs={
                "class": "w-full px-4 py-3 rounded-lg border-2 border-[#ec3183] focus:outline-none focus:ring-2 focus:ring-pink-500",
                "placeholder": "Main Title",
            }),
            "description": forms.Textarea(attrs={
                "class": "w-full px-4 py-3 rounded-lg border-2 border-[#ec3183] focus:outline-none focus:ring-2 focus:ring-pink-500",
                "placeholder": "Describe your complaint or issue...",
                "rows": 8,
            }),
        }

