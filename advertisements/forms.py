from django import forms
from django.utils.translation import gettext_lazy as _
from .models import Advertisement, AdPlacement
from django.core.exceptions import ValidationError
from django.utils import timezone

class AdvertisementForm(forms.ModelForm):
    # حقول تاريخ مخصصة مع اختيار الوقت
    start_date = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        initial=timezone.now
    )
    end_date = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        initial=timezone.now() + timezone.timedelta(days=30)
    )
    
    class Meta:
        model = Advertisement
        fields = [
            'title', 'placement', 'ad_type', 'image',
            'text_content', 'html_code', 'video_url',
            'link', 'start_date', 'end_date', 'active'
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'placement': forms.Select(attrs={'class': 'form-control'}),
            'ad_type': forms.Select(attrs={'class': 'form-control'}),
            'image': forms.FileInput(attrs={'class': 'form-control'}),
            'text_content': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': _('Enter text content for text ads')
            }),
            'html_code': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 5,
                'placeholder': _('<div>Your HTML ad code here</div>')
            }),
            'video_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://example.com/video.mp4'
            }),
            'link': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://example.com'
            }),
            'active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        ad_type = cleaned_data.get('ad_type')
        
        # التحقق من صحة التواريخ
        if start_date and end_date:
            if start_date >= end_date:
                raise ValidationError(_('End date must be after start date'))
            
            if start_date < timezone.now():
                raise ValidationError(_('Start date cannot be in the past'))
        
        # التحقق من الحقول المطلوبة حسب نوع الإعلان
        if ad_type == 'banner' and not cleaned_data.get('image'):
            raise ValidationError(_('Image is required for banner ads'))
        
        if ad_type == 'text' and not cleaned_data.get('text_content'):
            raise ValidationError(_('Text content is required for text ads'))
        
        if ad_type == 'html' and not cleaned_data.get('html_code'):
            raise ValidationError(_('HTML code is required for HTML ads'))
        
        if ad_type == 'video' and not cleaned_data.get('video_url'):
            raise ValidationError(_('Video URL is required for video ads'))
        
        return cleaned_data

class AdPlacementForm(forms.ModelForm):
    class Meta:
        model = AdPlacement
        fields = ['name', 'code', 'placement_type', 'description', 'width', 'height', 'active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., homepage_header'
            }),
            'placement_type': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            }),
            'width': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 50,
                'max': 2000
            }),
            'height': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 50,
                'max': 2000
            }),
            'active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def clean_code(self):
        code = self.cleaned_data['code']
        if not code.isidentifier():
            raise ValidationError(_('Code must be a valid identifier (letters, numbers, underscores)'))
        return code