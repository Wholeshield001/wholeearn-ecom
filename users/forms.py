from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from decimal import Decimal
from ecom.models import RewardPointConfig
from .models import Ticket, KYCSubmission

User = get_user_model()


class SignUpForm(forms.ModelForm):
    """Simplified form for end-user signup only"""
    referral_code_input = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-pink-200 focus:outline-none focus:ring-2 focus:ring-pink-500 uppercase',
            'placeholder': 'Referral Code (Optional)',
            'autocomplete': 'off',
        }),
        label='Referral Code',
    )
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

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email', 'phone')
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

    def clean_referral_code_input(self):
        referral_code = (self.cleaned_data.get('referral_code_input') or '').strip().upper()
        if not referral_code:
            return ''

        try:
            User.objects.get(referral_code=referral_code)
        except User.DoesNotExist as exc:
            raise ValidationError('Invalid referral code.') from exc
        return referral_code

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        user.role = User.END_USER  # Hardcode end-user role
        user.is_active = False  # Account inactive until email verified
        # Save phone explicitly since model allows null/blank but we require at form level
        user.phone = self.cleaned_data.get('phone')

        referral_code = self.cleaned_data.get('referral_code_input')
        if referral_code:
            user.referred_by = User.objects.get(referral_code=referral_code)

        if commit:
            user.save()
        return user


class PartnerRegistrationForm(forms.ModelForm):
    """Registration form for business partners (wholesalers, retailers, etc.)"""
    referral_code_input = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-pink-200 focus:outline-none focus:ring-2 focus:ring-pink-500 uppercase',
            'placeholder': 'Referral Code (Optional)',
            'autocomplete': 'off',
        }),
        label='Referral Code',
    )
    partner_type = forms.ChoiceField(
        choices=[
            (User.WHOLESALER, 'Wholesaler'),
            (User.RETAILER, 'Retailer'),
            (User.PHARMACY, 'Pharmacy'),
            (User.HOSPITAL, 'Hospital'),
            (User.ONLINE_VENDOR, 'Online Vendor'),
        ],
        widget=forms.RadioSelect(attrs={
            'class': 'text-pink-500 focus:ring-pink-500',
        }),
        label='Business Type'
    )
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

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email', 'phone')
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
                'placeholder': 'Business Email',
                'required': 'required',
            }),
            'phone': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 rounded-lg border border-pink-200 focus:outline-none focus:ring-2 focus:ring-pink-500',
                'placeholder': 'Business Phone',
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
        import re
        if not re.fullmatch(r"[+\d][\d\s\-]{6,19}", phone):
            raise ValidationError('Enter a valid phone number.')
        return phone

    def clean_referral_code_input(self):
        referral_code = (self.cleaned_data.get('referral_code_input') or '').strip().upper()
        if not referral_code:
            return ''

        try:
            User.objects.get(referral_code=referral_code)
        except User.DoesNotExist as exc:
            raise ValidationError('Invalid referral code.') from exc
        return referral_code

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        user.role = self.cleaned_data.get('partner_type')  # Set role based on selection
        user.is_active = False  # Account inactive until email verified
        user.phone = self.cleaned_data.get('phone')

        referral_code = self.cleaned_data.get('referral_code_input')
        if referral_code:
            user.referred_by = User.objects.get(referral_code=referral_code)

        if commit:
            user.save()
        return user


class KYCSubmissionForm(forms.ModelForm):
    """Form for KYC document submission"""
    class Meta:
        model = KYCSubmission
        fields = ('user_type', 'business_name', 'contact_number', 'business_address', 'cac_document')
        widgets = {
            'user_type': forms.RadioSelect(attrs={
                'class': 'text-pink-500 focus:ring-pink-500',
                'disabled': 'disabled',
            }),
            'business_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 rounded-lg border border-pink-200 focus:outline-none focus:ring-2 focus:ring-pink-500',
                'placeholder': 'Business Name',
                'required': 'required',
            }),
            'contact_number': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 rounded-lg border border-pink-200 focus:outline-none focus:ring-2 focus:ring-pink-500',
                'placeholder': 'Contact Number',
                'inputmode': 'tel',
                'required': 'required',
            }),
            'business_address': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 rounded-lg border border-pink-200 focus:outline-none focus:ring-2 focus:ring-pink-500',
                'placeholder': 'Business Address',
                'rows': 3,
                'required': 'required',
            }),
            'cac_document': forms.FileInput(attrs={
                'class': 'block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-pink-50 file:text-pink-700 hover:file:bg-pink-100',
                'accept': '.pdf,.jpg,.jpeg,.png',
                'required': 'required',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # user_type is set server-side in the view; do not block form submission.
        self.fields['user_type'].required = False

    def clean_contact_number(self):
        contact_number = (self.cleaned_data.get('contact_number') or '').strip()
        if not contact_number:
            raise ValidationError('Contact number is required.')
        import re
        if not re.fullmatch(r"[+\d][\d\s\-]{6,19}", contact_number):
            raise ValidationError('Enter a valid contact number.')
        return contact_number

    def clean_business_address(self):
        address = (self.cleaned_data.get('business_address') or '').strip()
        if not address:
            raise ValidationError('Business address is required.')
        if len(address) < 10:
            raise ValidationError('Business address must be at least 10 characters.')
        return address

    def clean_cac_document(self):
        doc = self.cleaned_data.get('cac_document')
        if not doc and self.instance and self.instance.pk and self.instance.cac_document:
            return self.instance.cac_document
        if not doc:
            raise ValidationError('Document is required.')
        # Max file size: 5MB
        if doc.size > 5 * 1024 * 1024:
            raise ValidationError('File size must not exceed 5MB.')
        # Allowed extensions
        if not doc.name.lower().endswith(('.pdf', '.jpg', '.jpeg', '.png')):
            raise ValidationError('Only PDF, JPG, and PNG files are allowed.')
        return doc



class LoginForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'w-full border bg-white px-4 py-3 text-sm text-gray-900 rounded-md focus:outline-none',
            'style': 'border-color:#f1a2c0;',
            'placeholder': 'Email',
            'autocomplete': 'email',
            'required': 'required',
        }),
        label='Email'
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full border bg-white px-4 py-3 text-sm text-gray-900 rounded-md focus:outline-none',
            'style': 'border-color:#f1a2c0;',
            'placeholder': 'Password',
            'autocomplete': 'current-password',
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


class RewardConversionForm(forms.Form):
    points = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-pink-200 focus:outline-none focus:ring-2 focus:ring-pink-500',
            'placeholder': 'Enter points to convert',
        })
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_points(self):
        points = self.cleaned_data['points']
        if points > self.user.reward_points:
            raise ValidationError('You do not have enough reward points for this conversion.')
        return points


class WalletBankAccountForm(forms.Form):
    account_number = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-pink-200 focus:outline-none focus:ring-2 focus:ring-pink-500',
            'placeholder': 'Account number',
            'inputmode': 'numeric',
        })
    )
    bank_code = forms.CharField(
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-pink-200 focus:outline-none focus:ring-2 focus:ring-pink-500 bg-white',
        })
    )
    bank_name = forms.CharField(
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-pink-200 focus:outline-none focus:ring-2 focus:ring-pink-500',
            'placeholder': 'Bank name (optional)',
        })
    )
    set_default = forms.BooleanField(required=False, initial=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['bank_code'].widget.choices = [('', 'Select bank')]

    def clean_account_number(self):
        account_number = (self.cleaned_data.get('account_number') or '').strip()
        if not account_number.isdigit() or len(account_number) not in {10}:
            raise ValidationError('Enter a valid 10-digit account number.')
        return account_number

    def clean_bank_code(self):
        import re
        bank_code = (self.cleaned_data.get('bank_code') or '').strip()
        if not bank_code:
            raise ValidationError('Please select a bank.')
        if not re.fullmatch(r'[\w\-]{1,20}', bank_code):
            raise ValidationError('Invalid bank code.')
        return bank_code


class WalletWithdrawalForm(forms.Form):
    amount = forms.DecimalField(
        decimal_places=2,
        max_digits=12,
        min_value=Decimal('0.01'),
        widget=forms.NumberInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-pink-200 focus:outline-none focus:ring-2 focus:ring-pink-500',
            'placeholder': 'Amount in naira',
            'step': '0.01',
            'min': '0.01',
        })
    )
    bank_account_id = forms.UUIDField(
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-pink-200 focus:outline-none focus:ring-2 focus:ring-pink-500',
        })
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        from ecom.models import WalletBankAccount

        accounts = WalletBankAccount.objects.filter(user=user, is_verified=True, is_active=True)
        self.fields['bank_account_id'].widget.choices = [
            (str(acc.id), f"{acc.account_name} - {acc.account_number} ({acc.bank_name or acc.bank_code})")
            for acc in accounts
        ]

    def clean_bank_account_id(self):
        bank_account_id = self.cleaned_data['bank_account_id']
        from ecom.models import WalletBankAccount

        if not WalletBankAccount.objects.filter(
            id=bank_account_id,
            user=self.user,
            is_verified=True,
            is_active=True,
        ).exists():
            raise ValidationError('Please select a valid verified bank account.')
        return bank_account_id

    def clean_amount(self):
        amount = self.cleaned_data['amount']
        config = RewardPointConfig.get_solo()
        minimum = Decimal(str(config.minimum_withdrawal_amount or 0))
        if amount < minimum:
            raise ValidationError(f'Minimum withdrawal is {minimum:.2f}.')
        return amount

