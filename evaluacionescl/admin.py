from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models import RegistroUsuarios, RegistroAdmin, EvaluacionLectura, EvaluacionLecturaIndividual, VistaAdmin, LecturaEnCurso

admin.site.register(RegistroUsuarios)
admin.site.register(RegistroAdmin)
admin.site.register(EvaluacionLectura)
admin.site.register(EvaluacionLecturaIndividual)
admin.site.register(VistaAdmin)
admin.site.register(LecturaEnCurso)
