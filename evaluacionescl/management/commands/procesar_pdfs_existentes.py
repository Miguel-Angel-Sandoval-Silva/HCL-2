import os
import fitz
from django.core.management.base import BaseCommand
from django.conf import settings
from evaluacionescl.models import Lectura

class Command(BaseCommand):
    help = 'Scans existing PDFs in the media folder, counts their words, and registers them in the database.'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS('--- Starting processing of existing PDFs ---'))
        
        bancotext_path = os.path.join(settings.MEDIA_ROOT, 'bancotext')
        tipos_texto = ['Argumentativo', 'Descriptivo', 'Expositivo', 'Narrativo']
        
        archivos_procesados = 0
        archivos_omitidos = 0

        for tipo in tipos_texto:
            carpeta_path = os.path.join(bancotext_path, tipo)
            if not os.path.isdir(carpeta_path):
                self.stdout.write(self.style.WARNING(f"Warning: Folder for '{tipo}' does not exist."))
                continue

            for nombre_archivo in os.listdir(carpeta_path):
                if nombre_archivo.endswith('.pdf'):
                    # Clean the title to match how it's saved elsewhere
                    titulo_base = nombre_archivo.replace('.pdf', '').replace('_', ' ')
                    
                    # 1. Check if it already exists in the database to avoid duplicates
                    if Lectura.objects.filter(titulo=titulo_base, tipo_texto=tipo).exists():
                        self.stdout.write(f"Skipping '{nombre_archivo}', already in DB.")
                        archivos_omitidos += 1
                        continue

                    # 2. If it doesn't exist, process it
                    self.stdout.write(f"Processing '{nombre_archivo}'...")
                    ruta_completa_pdf = os.path.join(carpeta_path, nombre_archivo)
                    
                    try:
                        # 3. Count the words
                        texto_completo = ""
                        with fitz.open(ruta_completa_pdf) as doc:
                            for pagina in doc:
                                texto_completo += pagina.get_text("text")
                        
                        conteo = len(texto_completo.split())

                        # 4. Create the record in the database
                        Lectura.objects.create(
                            titulo=titulo_base,
                            tipo_texto=tipo,
                            # The path for the FileField is saved relative to MEDIA_ROOT
                            archivo_pdf=os.path.join('bancotext', tipo, nombre_archivo), 
                            conteo_palabras=conteo
                        )
                        self.stdout.write(self.style.SUCCESS(f" -> Created record for '{titulo_base}' with {conteo} words."))
                        archivos_procesados += 1
                    
                    except Exception as e:
                        self.stderr.write(self.style.ERROR(f"Error processing '{nombre_archivo}': {e}"))

        self.stdout.write(self.style.SUCCESS(f'--- Process finished ---'))
        self.stdout.write(f'New files processed: {archivos_procesados}')
        self.stdout.write(f'Skipped files (already existing): {archivos_omitidos}')
