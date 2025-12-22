from django import forms
from django.contrib.auth import authenticate
from users.models import User
from .models import Category, Product, BlogPost, BlogCategory
from django.forms.widgets import ClearableFileInput
from django_ckeditor_5.widgets import CKEditor5Widget




class MultipleFileInput(ClearableFileInput):
    allow_multiple_selected = True

class AdminLoginForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'w-full bg-transparent outline-none placeholder:text-gray-400',
            'placeholder': 'you@example.com'
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full bg-transparent outline-none placeholder:text-gray-400',
            'placeholder': '••••••••'
        })
    )
    remember_me = forms.BooleanField(required=False)

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user_cache = None
        super().__init__(*args, **kwargs)

    def clean(self):
        email = self.cleaned_data.get('email')
        password = self.cleaned_data.get('password')

        if email and password:
            self.user_cache = authenticate(
                self.request,
                username=email,
                password=password
            )
            
            if self.user_cache is None:
                raise forms.ValidationError(
                    "Invalid email or password. Please try again."
                )
            
            # Check if user is an administrator
            if self.user_cache.role != User.ADMINISTRATOR or not self.user_cache.is_staff:
                raise forms.ValidationError(
                    "You don't have permission to access the admin dashboard."
                )
            
            if not self.user_cache.is_active:
                raise forms.ValidationError(
                    "This account is inactive."
                )

        return self.cleaned_data

    def get_user(self):
        return self.user_cache
    

class ForgotPasswordForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'w-full bg-gray-50 border border-gray-300 rounded-lg px-4 py-3 outline-none focus:border-teal-500',
            'placeholder': 'Enter your email'
        })
    )

    def clean_email(self):
        email = self.cleaned_data.get('email')
        try:
            user = User.objects.get(email=email, role=User.ADMINISTRATOR, is_staff=True)
        except User.DoesNotExist:
            raise forms.ValidationError("No administrator account found with this email.")
        return email
    


class VerifyOTPForm(forms.Form):
    otp_1 = forms.CharField(max_length=1, widget=forms.TextInput(attrs={'class': 'otp-input', 'maxlength': '1'}))
    otp_2 = forms.CharField(max_length=1, widget=forms.TextInput(attrs={'class': 'otp-input', 'maxlength': '1'}))
    otp_3 = forms.CharField(max_length=1, widget=forms.TextInput(attrs={'class': 'otp-input', 'maxlength': '1'}))
    otp_4 = forms.CharField(max_length=1, widget=forms.TextInput(attrs={'class': 'otp-input', 'maxlength': '1'}))
    otp_5 = forms.CharField(max_length=1, widget=forms.TextInput(attrs={'class': 'otp-input', 'maxlength': '1'}))
    otp_6 = forms.CharField(max_length=1, widget=forms.TextInput(attrs={'class': 'otp-input', 'maxlength': '1'}))

    def get_otp(self):
        return ''.join([
            self.cleaned_data.get('otp_1', ''),
            self.cleaned_data.get('otp_2', ''),
            self.cleaned_data.get('otp_3', ''),
            self.cleaned_data.get('otp_4', ''),
            self.cleaned_data.get('otp_5', ''),
            self.cleaned_data.get('otp_6', ''),
        ])



class ResetPasswordForm(forms.Form):
    new_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full bg-gray-50 border border-gray-300 rounded-lg px-4 py-3 outline-none focus:border-teal-500',
            'placeholder': 'Enter new password'
        })
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full bg-gray-50 border border-gray-300 rounded-lg px-4 py-3 outline-none focus:border-teal-500',
            'placeholder': 'Re-type password'
        })
    )

    def clean(self):
        cleaned_data = super().clean()
        new_password = cleaned_data.get('new_password')
        confirm_password = cleaned_data.get('confirm_password')

        if new_password and confirm_password:
            if new_password != confirm_password:
                raise forms.ValidationError("Passwords do not match.")
            
            if len(new_password) < 8:
                raise forms.ValidationError("Password must be at least 8 characters long.")

        return cleaned_data
    





class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg',
                'placeholder': 'Category name'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg resize-none',
                'rows': 4,
                'placeholder': 'Description (optional)'
            })
        }


class BlogCategoryForm(forms.ModelForm):
    class Meta:
        model = BlogCategory
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg',
                'placeholder': 'Category name'
            }),
        }


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name','description','category','price','discount','stock',
                 'is_male', 'is_female', 'is_general', 'additional_info']
        widgets = {
            'name': forms.TextInput(attrs={'class':'w-full px-4 py-3 border border-gray-300 rounded-lg'}),
            'description': CKEditor5Widget(attrs={'class':'django_ckeditor_5'}, config_name='default'),
            'category': forms.Select(attrs={'class':'w-full px-4 py-3 border border-gray-300 rounded-lg'}),
            'price': forms.NumberInput(attrs={'class':'w-full px-4 py-3 border border-gray-300 rounded-lg','step':'0.01'}),
            'discount': forms.NumberInput(attrs={'class':'w-full px-4 py-3 border border-gray-300 rounded-lg','min':'0','max':'100'}),
            'stock': forms.NumberInput(attrs={'class':'w-full px-4 py-3 border border-gray-300 rounded-lg','min':'0'}),
            'is_male': forms.CheckboxInput(attrs={'class':'w-4 h-4 text-teal-600 border-gray-300 rounded'}),
            'is_female': forms.CheckboxInput(attrs={'class':'w-4 h-4 text-teal-600 border-gray-300 rounded'}),
            'is_general': forms.CheckboxInput(attrs={'class':'w-4 h-4 text-teal-600 border-gray-300 rounded'}),
            'additional_info': forms.Textarea(attrs={'class':'w-full px-4 py-3 border border-gray-300 rounded-lg','rows':4}),
        }


class ProductImageForm(forms.Form):
    images = forms.FileField(
        widget=MultipleFileInput(attrs={"multiple": True}),
        required=False
    )

    def clean_images(self):
        images = self.files.getlist('images')
        # Remove the required validation - images are optional
        for image in images:
            if image.size > 5 * 1024 * 1024:  # 5MB limit
                raise forms.ValidationError("Each image must be less than 5MB.")
        return images


class BlogPostForm(forms.ModelForm):
    class Meta:
        model = BlogPost
        fields = ['title', 'content', 'category', 'cover_image', 'is_published', 'parent']
        widgets = {
            'content': CKEditor5Widget(attrs={'class': 'django_ckeditor_5'}, config_name='extends'),
            'title': forms.TextInput(attrs={'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg'}),
            'category': forms.Select(attrs={'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg', 'form': 'blog-form'}),
            'parent': forms.Select(attrs={'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg', 'form': 'blog-form'}),
            'is_published': forms.CheckboxInput(attrs={'class': 'w-4 h-4 text-teal-600 border-gray-300 rounded'}),
            'cover_image': forms.FileInput(attrs={'class': 'w-full', 'form': 'blog-form'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = BlogCategory.objects.all().order_by('name')
        self.fields['category'].required = False
        self.fields['parent'].queryset = BlogPost.objects.all().order_by('title')
        self.fields['parent'].required = False
        self.fields['is_published'].required = False