import os
import re
from io import BytesIO
from django.core.files.base import ContentFile
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.text import slugify
from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver
from django_ckeditor_5.fields import CKEditor5Field
import cuid2
from PIL import Image, ImageOps  # Importa o Pillow para processar a imagem

def generate_cuid():
    return cuid2.cuid_wrapper()()

# --- FUNÇÃO PARA COMPRIMIR E CONVERTER PARA WEBP ---
def compress_and_convert_to_webp(image_field, max_width=1024, quality=80, is_avatar=False):
    """
    Recebe um ImageField, converte para .webp, redimensiona se for muito grande
    e comprime usando um buffer na memória.
    """
    if not image_field:
        return

    # Abre a imagem original usando o Pillow
    img = Image.open(image_field)

    img = ImageOps.exif_transpose(img)

    # Converte para RGB (necessário se a imagem original for PNG com transparência ou RGBA)
    if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
        # Cria um fundo branco para manter a visibilidade caso haja transparência
        background = Image.new('RGB', img.size, (255, 255, 255))
        background.paste(img, mask=img.convert('RGBA').split()[3])
        img = background
    else:
        img = img.convert('RGB')

    if is_avatar:
        img = ImageOps.fit(img, (max_width, max_width), Image.Resampling.LANCZOS)
    else:
    # Redimensiona proporcionalmente se a largura for maior que o permitido (ex: 1024px)
        if img.width > max_width:
            output_size = (max_width, int((max_width / img.width) * img.height))
            img = img.resize(output_size, Image.Resampling.LANCZOS)

    # Cria o buffer na memória (BytesIO)
    image_io = BytesIO()

    # Salva a imagem no buffer formato WEBP com a qualidade desejada (0-100)
    img.save(image_io, format='WEBP', quality=quality, optimize=True)

    # Altera a extensão do nome do arquivo original para .webp
    current_filename = os.path.splitext(image_field.name)[0]
    new_filename = f"{current_filename}.webp"

    # Substitui o arquivo original pelo arquivo comprimido no buffer
    image_field.save(new_filename, ContentFile(image_io.getvalue()), save=False)


# --- CONFIGURAÇÃO DOS CAMINHOS ---
def get_image_upload_path(instance, filename):
    folder_name = slugify(instance.username) or "usuario-sem-nome"
    return os.path.join('users', folder_name, filename)

def get_cover_upload_path(instance, filename):
    folder_name = slugify(instance.title) or "sem-titulo"
    return os.path.join('post', folder_name, filename)


# --- MODELOS ---
class Usuario(AbstractUser):
    id = models.CharField(primary_key=True, default=generate_cuid, editable=False, max_length=50)
    image = models.ImageField(upload_to=get_image_upload_path, blank=True, null=True, verbose_name="Foto")

    def save(self, *args, **kwargs):
        # Se uma nova imagem foi enviada, comprime antes de salvar
        if self.image and not self.image.name.endswith('.webp'):
            compress_and_convert_to_webp(self.image, max_width=400, quality=85, is_avatar=True) # Avatares podem ser menores (400px)
        super().save(*args, **kwargs)

class Post(models.Model):
    id = models.CharField(primary_key=True, default=generate_cuid, editable=False, max_length=50)
    STATUS_CHOICES = (('draft', 'Rascunho'), ('published', 'Publicado'))

    title = models.CharField(max_length=200, verbose_name="Título")
    slug = models.SlugField(max_length=200, unique=True, blank=True, verbose_name="slug")
    description = models.CharField(max_length=200, verbose_name="Descrição")
    image_cover = models.ImageField(upload_to=get_cover_upload_path, blank=True, null=True, verbose_name="Capa")
    content = CKEditor5Field('Conteúdo', config_name='default')
    author = models.ForeignKey(Usuario, on_delete=models.PROTECT, verbose_name="Autor")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Criado em")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Atualizado em")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft', verbose_name="Status")

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # 1. Gera o slug se não existir
        if not self.slug:
            self.slug = slugify(self.title)

        # 2. Se uma nova capa foi enviada, comprime e converte para .webp
        if self.image_cover and not self.image_cover.name.endswith('.webp'):
            compress_and_convert_to_webp(self.image_cover, max_width=1200, quality=80, is_avatar=False)

        # 3. --- SISTEMA DE LIMPEZA DE IMAGENS DO CKEDITOR ---
        if self.pk:  # Só faz isso se o post já existir (ou seja, se for uma EDIÇÃO)
            try:
                # Busca a versão atual do post diretamente do banco de dados antes de salvar o novo texto
                post_antigo = Post.objects.get(pk=self.pk)

                # Expressão regular para encontrar o caminho de todas as imagens (<img src="...">)
                # Ela captura o que estiver dentro de /media/...webp
                pattern = r'src="/media/([^"]+)"'

                imagens_antigas = set(re.findall(pattern, post_antigo.content))
                imagens_novas = set(re.findall(pattern, self.content))

                # Descobre quais imagens foram deletadas pelo usuário no editor
                imagens_removidas = imagens_antigas - imagens_novas

                # Apaga os arquivos físicos das imagens removidas
                from django.conf import settings
                for img_path_relativo in imagens_removidas:
                    # Converte o caminho relativo da URL para o caminho absoluto no seu computador
                    caminho_absoluto = os.path.join(settings.MEDIA_ROOT, img_path_relativo)
                    if os.path.isfile(caminho_absoluto):
                        os.remove(caminho_absoluto)

            except Post.DoesNotExist:
                pass
        # -----------------------------------------------------

        # Salva o post de fato com o novo conteúdo
        super().save(*args, **kwargs)


# ==============================================================================
# --- SIGNALS PARA EXCLUSÃO AUTOMÁTICA DE IMAGENS (SISTEMA DE LIMPEZA) ---
# ==============================================================================

# 1. Deleta o arquivo físico quando o objeto é excluído do banco de dados
@receiver(post_delete, sender=Post)
def delete_cover_on_post_delete(sender, instance, **kwargs):
    if instance.image_cover:
        if os.path.isfile(instance.image_cover.path):
            os.remove(instance.image_cover.path)

@receiver(post_delete, sender=Usuario)
def delete_avatar_on_user_delete(sender, instance, **kwargs):
    if instance.image:
        if os.path.isfile(instance.image.path):
            os.remove(instance.image.path)

# 2. Deleta o arquivo antigo quando o usuário altera a imagem por uma NOVA
@receiver(pre_save, sender=Post)
def delete_old_cover_on_change(sender, instance, **kwargs):
    if not instance.pk:
        return False
    try:
        old_post = Post.objects.get(pk=instance.pk)
    except Post.DoesNotExist:
        return False

    old_cover = old_post.image_cover
    new_cover = instance.image_cover
    if old_cover and old_cover != new_cover:
        if os.path.isfile(old_cover.path):
            os.remove(old_cover.path)

@receiver(pre_save, sender=Usuario)
def delete_old_avatar_on_change(sender, instance, **kwargs):
    if not instance.pk:
        return False
    try:
        old_user = Usuario.objects.get(pk=instance.pk)
    except Usuario.DoesNotExist:
        return False

    old_img = old_user.image
    new_img = instance.image
    if old_img and old_img != new_img:
        if os.path.isfile(old_img.path):
            os.remove(old_img.path)
