from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('about/', views.about, name='about'),
    path('people/', views.people, name='people'),
    path('people/<str:username>/', views.profile_public, name='profile_public'),
    path('cv/<str:username>/', views.cv_pdf, name='cv_pdf'),
    path('publications/', views.publications, name='publications'),
    path('research/', views.research, name='research'),
    path('research/<slug:slug>/', views.research_detail, name='research_detail'),
    path('accounts/login/', views.login, name='login'),
    path('accounts/signup/', views.signup, name='signup'),
    path('accounts/logout/', views.logout_view, name='logout'),
    # Password reset
    path('accounts/forgot/', views.forgot_password, name='forgot_password'),
    path('accounts/reset/<uidb64>/<token>/', views.reset_password, name='reset_password'),
    path('search/', views.search, name='search'),
    # User profile management
    path('accounts/profile/', views.user_profile, name='user_profile'),
    path('accounts/change/', views.change_password, name='change_password'),
    path('admin/users/', views.admin_users, name='admin_users'),
    path('admin/actions/', views.admin_content_actions, name='admin_content_actions'),
    path('admin/reorder/', views.admin_reorder, name='admin_reorder'),
]