from django.contrib import admin
from django.utils.html import format_html
from django.contrib.auth.admin import UserAdmin
from .models import Post, Usuario

class CustomUserAdmin(UserAdmin):
    # Adiciona o campo de foto na tela de edição do usuário no Admin
    # fieldsets controla a divisão das seções dentro da página do usuário
    fieldsets = UserAdmin.fieldsets + (
        ('Informações Extras', {'fields': ('image',)}),
    )
    
    # Adiciona a foto na lista de usuários para você ver a miniatura de quem é quem
    list_display = ('exibir_avatar', 'username', 'email', 'first_name', 'last_name', 'is_staff')
    list_display_links = ("username",)
    
    def exibir_avatar(self, obj):
        if obj.image and hasattr(obj.image, 'url'):
            return format_html('<img src="{}" style="height: 40px; width: 40px; border-radius: 50%; object-cover: cover;" />', obj.image.url)
        return "Sem foto"
    
    exibir_avatar.short_description = 'Avatar'

# Registra o Usuario usando a classe customizada que criamos acima
admin.site.register(Usuario, CustomUserAdmin)

@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("image_thumbnail",'title', 'status', 'created_at')
    list_display_links = ("title",)
    list_filter = ('status',)
    search_fields = ('title', 'content')
    ordering = ("-created_at",)
    prepopulated_fields = {'slug': ('title',)}

    @admin.display(description="Capa")
    def image_thumbnail(self, obj):
        if obj.image_cover and hasattr(obj.image_cover, 'url'):
            return format_html(
                '<a href="{0}" target="_blank">'
                '<img src="{0}" style="height: 50px; width: 50px; object-fit: cover; border-radius: 5px;" />'
                '</a>',
                obj.image_cover.url
            )
        return "Sem imagem"