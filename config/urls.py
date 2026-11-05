from django.urls import path
from django.contrib.auth.views import LogoutView
from clinic import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('login/', views.ClinicLoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('patients/', views.search, name='patients'),
    path('patients/new/', views.patient_create, name='patient_create'),
    path('patients/<int:pk>/', views.patient_detail, name='patient_detail'),
    path('patients/<int:pk>/edit/', views.patient_edit, name='patient_edit'),
    path('accounts/', views.accounts, name='accounts'),
    path('audit/', views.audit, name='audit'),
]
# Local development only; runserver --insecure serves local CSS with DEBUG=False.
