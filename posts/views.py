from django.views.generic import ListView, DetailView
from .models import Post

import os
from io import BytesIO
from urllib.parse import urlparse
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.utils.text import slugify
from PIL import Image

class PostListView(ListView):
    model = Post
    template_name = 'posts/index.html'
    context_object_name = 'posts'
    # Mostra apenas posts publicados
    queryset = Post.objects.filter(status='published')

class PostDetailView(DetailView):
    model = Post
    template_name = 'posts/detail.html'
    context_object_name = 'post'



@csrf_exempt
def ckeditor5_custom_upload(request):
    if request.method == 'POST' and request.FILES.get('upload'):
        uploaded_file = request.FILES['upload']
        
        # --- ESTRATÉGIA PARA PEGAR O NOME CORRETO DA PASTA ---
        folder_name = "sem-titulo"
        
        # 1. Tenta pegar o título direto do POST (caso o editor consiga enviar)
        post_title = request.POST.get('title')
        
        # 2. Se não achar no POST, tenta descobrir se estamos editando um Post existente
        # Olhando a URL de onde a requisição veio (Ex: /admin/blog/post/cuid123/change/)
        if not post_title and 'HTTP_REFERER' in request.META:
            referer_path = urlparse(request.META['HTTP_REFERER']).path
            path_parts = [p for p in referer_path.split('/') if p]
            
            # Se a URL tem padrão de edição: ['admin', 'blog', 'post', 'id_do_post', 'change']
            if len(path_parts) >= 4 and path_parts[0] == 'admin' and path_parts[2] == 'post':
                post_id = path_parts[3]
                try:
                    # Busca o post no banco para usar o slug real dele
                    post_existente = Post.objects.get(pk=post_id)
                    folder_name = slugify(post_existente.title)
                except (Post.DoesNotExist, ValueError):
                    pass

        # 3. Se ainda assim for um post NOVO sendo criado agora, 
        # não temos o título no banco ainda. Vamos usar o ID do autor temporariamente
        # para agrupar as imagens dele, ou uma pasta limpa.
        if folder_name == "sem-titulo" and request.user.is_authenticated:
            # Cria algo como: post/criando-por-admin/imagens/...
            folder_name = f"criando-por-{slugify(request.user.username)}"

        # ---------------------------------------------------
        
        # Processamento e Compressão da imagem com o Pillow (Igual antes)
        try:
            img = Image.open(uploaded_file)
            
            if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.convert('RGBA').split()[3])
                img = background
            else:
                img = img.convert('RGB')
                
            if img.width > 1200:
                output_size = (1200, int((1200 / img.width) * img.height))
                img = img.resize(output_size, Image.Resampling.LANCZOS)
                
            image_io = BytesIO()
            img.save(image_io, format='WEBP', quality=80, optimize=True)
            
            filename_base = os.path.splitext(uploaded_file.name)[0]
            new_filename = f"{slugify(filename_base)}.webp"
            
            # SALVAMENTO NA PASTA CORRETA:
            # Para posts existentes: media/post/o-nome-do-seu-post/imagens/foto.webp
            # Para posts novos: media/post/criando-por-usuario/imagens/foto.webp
            custom_path = os.path.join('post', folder_name, 'imagens', new_filename)
            
            saved_path = default_storage.save(custom_path, ContentFile(image_io.getvalue()))
            file_url = default_storage.url(saved_path)
            
            return JsonResponse({'url': file_url})
            
        except Exception as e:
            return JsonResponse({'error': {'message': f'Erro ao processar imagem: {str(e)}'}}, status=400)
            
    return JsonResponse({'error': {'message': 'Método não permitido ou arquivo não enviado.'}}, status=400)