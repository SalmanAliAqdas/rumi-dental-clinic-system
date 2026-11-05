from django.urls import path
from django.contrib.auth.views import LogoutView
from clinic import views
from clinic import clinical_views as clinical

urlpatterns = [
    path('catalogue/', clinical.catalogue, name='catalogue'),
    path('catalogue/<int:procedure_id>/', clinical.catalogue, name='procedure_edit'),
    path('patients/<int:pk>/clinical/<str:section>/', clinical.section, name='clinical_section'),
    path('patients/<int:pk>/visits/new/', clinical.visit_new, name='visit_new'),
    path('patients/<int:pk>/visits/<int:visit_id>/', clinical.visit_detail, name='visit_detail'),
    path('patients/<int:pk>/visits/<int:visit_id>/edit/', clinical.visit_edit, name='visit_edit'),
    path('patients/<int:pk>/visits/<int:visit_id>/draft/', clinical.visit_autosave, name='visit_autosave'),
    path('patients/<int:pk>/visits/<int:visit_id>/amend/', clinical.amend, name='visit_amend'),
    path('patients/<int:pk>/visits/<int:visit_id>/work/', clinical.work_add, name='work_add'),
    path('patients/<int:pk>/medical/review/', clinical.medical_review, name='medical_review'),
    path('patients/<int:pk>/chart/add/', clinical.chart_add, name='chart_add'),
    path('patients/<int:pk>/plans/new/', clinical.plan_edit, name='plan_new'),
    path('patients/<int:pk>/plans/<int:plan_id>/', clinical.plan_detail, name='plan_detail'),
    path('patients/<int:pk>/plans/<int:plan_id>/edit/', clinical.plan_edit, name='plan_edit'),
    path('patients/<int:pk>/plans/<int:plan_id>/items/new/', clinical.item_edit, name='item_new'),
    path('patients/<int:pk>/plans/<int:plan_id>/items/<int:item_id>/', clinical.item_edit, name='item_edit'),
    path('patients/<int:pk>/attachments/upload/', clinical.upload, name='attachment_upload'),
    path('patients/<int:pk>/attachments/<int:attachment_id>/<str:mode>/', clinical.attachment_file, name='attachment_file'),
    path('_local/trial-ready/', views.trial_ready, name='trial_ready'),
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
