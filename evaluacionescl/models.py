from django.db import models

# Create your models here.
from django.db import models
from django.contrib.auth.hashers import make_password, check_password

SEXO_OPCIONES = [
    ('M', 'Masculino'),
    ('F', 'Femenino'),
    ('O', 'Otro / Prefiero no decirlo'),
]

class RegistroUsuarios(models.Model):
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    edad = models.IntegerField()
    matricula = models.CharField(max_length=20, unique=True)
    cuatrimestre = models.CharField(max_length=10)
    contrasena = models.CharField(max_length=200)
#    sexo = models.CharField(max_length=1, choices=SEXO_OPCIONES, null=True, blank=True)  # temporalmente opcional
    sexo = models.CharField(max_length=1, choices=SEXO_OPCIONES)  # ← obligatorio

    def set_contrasena(self, contrasena):
        self.contrasena = make_password(contrasena)

    def check_contrasena(self, contrasena):
        return check_password(contrasena, self.contrasena)

    def __str__(self):
        return f"{self.nombre} {self.apellido}"


class RegistroAdmin(models.Model):
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    matricula = models.CharField(max_length=20, unique=True)
    contrasena = models.CharField(max_length=200)
#    sexo = models.CharField(max_length=1, choices=SEXO_OPCIONES, null=True, blank=True)  # temporalmente opcional
    sexo = models.CharField(max_length=1, choices=SEXO_OPCIONES)  # ← obligatorio

    def set_contrasena(self, contrasena):
        self.contrasena = make_password(contrasena)

    def check_contrasena(self, contrasena):
        return check_password(contrasena, self.contrasena)

    def __str__(self):
        return f"{self.nombre} {self.apellido}"
    

class Lectura(models.Model):
    TIPO_TEXTO_OPCIONES = [
        ('Argumentativo', 'Argumentativo'),
        ('Descriptivo', 'Descriptivo'),
        ('Expositivo', 'Expositivo'),
        ('Narrativo', 'Narrativo'),
    ]
    
    titulo = models.CharField(max_length=255)
    tipo_texto = models.CharField(max_length=50, choices=TIPO_TEXTO_OPCIONES)
    archivo_pdf = models.FileField(upload_to='bancotext/')
    conteo_palabras = models.IntegerField(default=0, editable=False)

    def __str__(self):
        return self.titulo  


class EvaluacionLectura(models.Model):
    usuario = models.ForeignKey(RegistroUsuarios, on_delete=models.CASCADE)
    tipo_texto = models.CharField(max_length=100)
    textos_leidos = models.IntegerField(default=0)
    porcentaje = models.FloatField(default=0 )
    nivel_comprension = models.CharField(max_length=50)

    def __str__(self):
        return f"{self.usuario} - {self.tipo_texto}"

from django.db import models
from django.utils import timezone
from .models import RegistroUsuarios  # Asegúrate de importar tu modelo de usuario si no usas auth.User

class EvaluacionLecturaIndividual(models.Model):
    usuario = models.ForeignKey(RegistroUsuarios, on_delete=models.CASCADE)
    tipo_texto = models.CharField(max_length=50)
    titulo_lectura = models.CharField(max_length=255)
    
    fragmento = models.TextField(default="Fragmento no disponible")  # evita el error de migración
    instruccion = models.CharField(max_length=255, default="")       # en caso de que también sea nuevo

    respuesta_usuario = models.TextField(blank=True, null=True)  # opcional para que pueda quedar vacío
    puntaje = models.IntegerField(blank=True, null=True)         # también opcional hasta evaluar
    tipo_inferencia = models.CharField(max_length=100, blank=True, null=True)

    fecha_lectura = models.DateTimeField(auto_now_add=True)  # ok si ya migraste o diste default

    palabras_por_minuto = models.IntegerField(null=True, blank=True)
    tiempo_lectura_segundos = models.FloatField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.usuario} - {self.titulo_lectura} - {self.tipo_texto}"


class VistaAdmin(models.Model):
    usuarios_total = models.IntegerField()
    tipo_texto = models.CharField(max_length=100)
    textos_total = models.IntegerField()
    puntaje_total = models.FloatField()
    nivel_comprension_global = models.CharField(max_length=50)

    def __str__(self):
        return f"{self.tipo_texto} - Nivel: {self.nivel_comprension_global}"


class LecturaEnCurso(models.Model):
    usuario = models.ForeignKey(RegistroUsuarios, on_delete=models.CASCADE)
    tipo_texto = models.CharField(max_length=50)
    titulo_lectura = models.CharField(max_length=200)
    fecha_inicio = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("usuario", "tipo_texto")  # Solo una lectura activa por tipo

    def __str__(self):
        return f"{self.usuario} - {self.tipo_texto} - {self.titulo_lectura}"
