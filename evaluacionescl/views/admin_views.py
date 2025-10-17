from django.shortcuts import render, redirect
from django.db.models import Count, Sum, Q
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.http import JsonResponse
from django.template.loader import render_to_string
import subprocess
import os
from ..models import RegistroUsuarios, EvaluacionLecturaIndividual

VAL_MAX = 3

# Vista: Dashboard del administrador
def dashboard_admin(request):
    usuarios_activos = RegistroUsuarios.objects.annotate(
        evaluaciones_realizadas=Count(
            'evaluacionlecturaindividual',
            filter=Q(evaluacionlecturaindividual__puntaje__isnull=False)
        )
    ).filter(evaluaciones_realizadas__gt=0)

    total_usuarios = usuarios_activos.count()

    tipos = ["Argumentativo", "Descriptivo", "Expositivo", "Narrativo"]
    resumen = []

    for tipo in tipos:
        lecturas = EvaluacionLecturaIndividual.objects.filter(tipo_texto=tipo)
        total_lecturas = lecturas.count()
        total_puntos = sum([e.puntaje for e in lecturas if e.puntaje is not None])
        promedio = (total_puntos / total_lecturas) if total_lecturas > 0 else 0
        porcentaje = (promedio / VAL_MAX) * 100 if total_lecturas > 0 else 0

        resumen.append({
            "tipo": tipo,
            "total_lecturas": total_lecturas,
            "promedio_porcentaje": round(porcentaje, 2)
        })
    contexto = {
        "total_usuarios": total_usuarios,
        "resumen_por_tipo": resumen,
    }

    # 🔴 ESTE return es obligatorio
    return render(request, "evaluacionescl/dashboard_admin.html", contexto)


# Vista: Resultados globales por tipo de texto
def admin_resultados(request):
    tipos = ["Argumentativo", "Descriptivo", "Expositivo", "Narrativo"]
    resumen = []

    for tipo in tipos:
        lecturas = EvaluacionLecturaIndividual.objects.filter(tipo_texto=tipo)
        cantidad = lecturas.count()
        suma_puntos = sum([e.puntaje for e in lecturas if e.puntaje is not None])

        if cantidad > 0:
            promedio = suma_puntos / cantidad
            porcentaje = (promedio / VAL_MAX) * 100  # Asumiendo VAL_MAX = 3

            if porcentaje >= 90:
                nivel = f"Alto (Comprensión profunda) - {int(porcentaje)}%"
            elif porcentaje >= 60:
                nivel = f"Medio (Comprensión adecuada) - {int(porcentaje)}%"
            elif porcentaje >= 30:
                nivel = f"Bajo (Comprensión superficial) - {int(porcentaje)}%"
            else:
                nivel = f"Deficiente (No comprensión) - {int(porcentaje)}%"
        else:
            nivel = "Sin evaluar"

        resumen.append({
            "tipo": tipo,
            "cantidad": cantidad,
            "puntaje_total": suma_puntos,
            "nivel": nivel
        })

    total_usuarios = RegistroUsuarios.objects.count()

    return render(request, 'evaluacionescl/admin_resultados.html', {
        'resumen': resumen,
        'total_usuarios': total_usuarios
    })

# Vista: Estadísticas por alumno con búsqueda
from django.db.models import Q
from django.shortcuts import render, get_object_or_404
from ..models import RegistroUsuarios, EvaluacionLecturaIndividual
from .evaluacion_views import calcular_porcentaje

VAL_MAX = 3

def admin_estadisticas(request):
    query = request.GET.get('q', '')
    usuarios = RegistroUsuarios.objects.all()
    if query:
        usuarios = usuarios.filter(
            Q(nombre__icontains=query) |
            Q(apellido__icontains=query) |
            Q(matricula__icontains=query)
        )

    resultados = []
    for user in usuarios:
        lecturas = EvaluacionLecturaIndividual.objects.filter(usuario=user)
        total_textos = lecturas.count()
        total_puntos = sum([e.puntaje for e in lecturas if e.puntaje is not None])
        promedio = (total_puntos / total_textos) if total_textos > 0 else 0
        porcentaje = (promedio / VAL_MAX) * 100 if total_textos > 0 else 0

        if total_textos > 0:
            if porcentaje >= 90:
                nivel = f"Alto (Comprensión profunda) - {int(porcentaje)}%"
            elif porcentaje >= 60:
                nivel = f"Medio (Comprensión adecuada) - {int(porcentaje)}%"
            elif porcentaje >= 30:
                nivel = f"Bajo (Comprensión superficial) - {int(porcentaje)}%"
            else:
                nivel = f"Deficiente (No comprensión) - {int(porcentaje)}%"
        else:
            nivel = "Sin evaluar"

        resultados.append({
            "id": user.id,
            "nombre": f"{user.nombre} {user.apellido}",
            "matricula": user.matricula,
            "textos": total_textos,
            "puntaje": total_puntos,
            "nivel": nivel
        })

    return render(request, 'evaluacionescl/admin_estadisticas.html', {
        'resultados': resultados,
        'query': query
    })

#--------------------------------------------------------------------------------------------

from django.contrib import messages
from django.shortcuts import redirect

def eliminar_usuario(request, usuario_id):
    if request.method == "POST":
        try:
            usuario = RegistroUsuarios.objects.get(id=usuario_id)
            usuario.delete()
            messages.success(request, "Usuario eliminado correctamente.")
        except RegistroUsuarios.DoesNotExist:
            messages.error(request, "El usuario no existe.")
    return redirect("admin_estadisticas")

#----------------------------------------------------------------------------------------------

from django.shortcuts import get_object_or_404, render, redirect
from ..models import RegistroUsuarios, EvaluacionLecturaIndividual
from .evaluacion_views import calcular_porcentaje  # Asegúrate de importar si está separado


def ver_resultados_alumno(request, usuario_id):
    alumno = get_object_or_404(RegistroUsuarios, id=usuario_id)
    tipos = ["Argumentativo", "Descriptivo", "Expositivo", "Narrativo"]
    resultados = []

    for tipo in tipos:
        lecturas = EvaluacionLecturaIndividual.objects.filter(usuario=alumno, tipo_texto=tipo)
        total = lecturas.count()

        if total:
            puntos = sum([e.puntaje for e in lecturas if e.puntaje is not None])
            promedio = puntos / total
            porcentaje = calcular_porcentaje(promedio)
            if porcentaje >= 90:
                nivel = f"Alto (Comprensión profunda) - {int(porcentaje)}%"
            elif porcentaje >= 60:
                nivel = f"Medio (Comprensión adecuada) - {int(porcentaje)}%"
            elif porcentaje >= 30:
                nivel = f"Bajo (Comprensión superficial) - {int(porcentaje)}%"
            else:
                nivel = f"Deficiente (No comprensión) - {int(porcentaje)}%"
        else:
            porcentaje = 0
            nivel = "Sin evaluar"

        resultados.append({
            "tipo": tipo,
            "cantidad": total,
            "nivel": nivel,
            "porcentaje": porcentaje
        })

    # Validación si no hay lecturas
    evaluaciones_total = sum([r["cantidad"] for r in resultados])
    if evaluaciones_total == 0:
        return render(request, "evaluacionescl/sin_resultados_alumno.html", {
            "mensaje": f"El alumno {alumno.nombre} aún no ha realizado ninguna evaluación."
        })

    # 📌 AQUI EMPIEZA LA LÓGICA DE LA GRÁFICA GLOBAL MENSUAL
    from collections import defaultdict
    from django.utils.timezone import localtime
    from datetime import datetime

    individuales = EvaluacionLecturaIndividual.objects.filter(
        usuario=alumno,
        respuesta_usuario__isnull=False,
        puntaje__isnull=False
    )

    mes_tipo_set = defaultdict(set)
    for indiv in individuales:
        fecha_local = indiv.fecha_lectura
        mes_clave = fecha_local.strftime("%Y-%m")
        mes_tipo_set[mes_clave].add(indiv.tipo_texto)

    resumenes = EvaluacionLectura.objects.filter(usuario=alumno)
    porcentajes_por_tipo = {r.tipo_texto: r.porcentaje or 0 for r in resumenes}

    meses = []
    promedios_globales = []
    meses_esp = {
        "Jan": "Ene", "Feb": "Feb", "Mar": "Mar", "Apr": "Abr", "May": "May",
        "Jun": "Jun", "Jul": "Jul", "Aug": "Ago", "Sep": "Sep",
        "Oct": "Oct", "Nov": "Nov", "Dec": "Dic"
    }

    for mes in sorted(mes_tipo_set.keys()):
        suma = sum([porcentajes_por_tipo.get(t, 0) for t in tipos])
        promedio = suma / 4
        promedios_globales.append(round(promedio, 1))

        fecha_obj = datetime.strptime(mes, "%Y-%m")
        mes_abbr = fecha_obj.strftime("%b")
        mes_nombre = meses_esp.get(mes_abbr, mes_abbr)
        meses.append(f"{mes_nombre} {fecha_obj.year}")

    # ➕ Nivel global textual
    if promedios_globales:
        ultimo = promedios_globales[-1]
        if ultimo >= 90:
            nivel_global = "Alto (Comprensión profunda)"
        elif ultimo >= 60:
            nivel_global = "Medio (Comprensión adecuada)"
        elif ultimo >= 30:
            nivel_global = "Bajo (Comprensión superficial)"
        else:
            nivel_global = "Deficiente (No comprensión)"
    else:
        nivel_global = "Sin evaluar"

    # ⬇️ RETURN COMPLETO
    return render(request, "evaluacionescl/ver_resultados_alumno.html", {
        "resultados": resultados,
        "alumno": alumno,
        "usuario_id": alumno.id,
        "nombre_alumno": alumno.nombre,
        "meses": meses,
        "promedios": promedios_globales,
        "nivel_global": nivel_global
    })
from django.shortcuts import render, get_object_or_404
from ..models import RegistroUsuarios, EvaluacionLecturaIndividual

def calcular_porcentaje(promedio):
    if promedio is None:
        return 0
    return (promedio / VAL_MAX) * 100

# ✅ 4. ver_grafica_alumno_tipo (con título, fecha y hora en líneas separadas)
# ✅ 4. ver_grafica_alumno_tipo (con multilínea real para Chart.js)

def ver_grafica_alumno_tipo(request, usuario_id, tipo_texto):
    alumno = get_object_or_404(RegistroUsuarios, id=usuario_id)
    lecturas = EvaluacionLecturaIndividual.objects.filter(
        usuario=alumno,
        tipo_texto=tipo_texto
    ).order_by('fecha_lectura')

    if not lecturas.exists():
        return render(request, "evaluacionescl/no_evaluaciones_admin.html", {
            "mensaje": f"No hay lecturas evaluadas para el tipo '{tipo_texto}' de este alumno."
        })

    titulos, porcentajes, tipos_inferencia, tooltips = [], [], [], []
    vistos = set()

    for l in lecturas:
        if l.titulo_lectura not in vistos:
            vistos.add(l.titulo_lectura)

            from django.utils.timezone import localtime
            fecha_local = l.fecha_lectura
            meses = {
                "Jan": "Ene", "Feb": "Feb", "Mar": "Mar", "Apr": "Abr",
                "May": "May", "Jun": "Jun", "Jul": "Jul", "Aug": "Ago",
                "Sep": "Sep", "Oct": "Oct", "Nov": "Nov", "Dec": "Dic"
            }
            mes_abbr = fecha_local.strftime("%b")
            mes_esp = meses.get(mes_abbr, mes_abbr)
            fecha_linea1 = f"{fecha_local.strftime('%d')}/{mes_esp}/{fecha_local.strftime('%Y')}"
            fecha_linea2 = fecha_local.strftime("%H:%M")
            titulo = l.titulo_lectura
            if len(titulo) > 20:
                titulo = titulo[:20] + "…"
            etiqueta = f"{titulo}\n{fecha_linea1}\n{fecha_linea2}"
            titulos.append(etiqueta)

            porcentaje = calcular_porcentaje(l.puntaje) if l.puntaje is not None else 0
            porcentajes.append(porcentaje)
            tooltips.append(f"{int(porcentaje)}%" if l.puntaje is not None else "Sin evaluar")

            tipo = l.tipo_inferencia
            if tipo == "no_inferencia_sinsentido":
                tipo = "No inferencia: sin sentido"
            elif tipo == "no_inferencia_parafrasis":
                tipo = "No inferencia: paráfrasis"
            elif tipo:
                tipo = tipo.capitalize()
            else:
                tipo = "No inferencia: sin sentido"

            tipos_inferencia.append(tipo)

    return render(request, "evaluacionescl/ver_grafica_alumno_tipo.html", {
        "tipo": tipo_texto,
        "titulos": titulos,
        "porcentajes": porcentajes,
        "tipos_inferencia": tipos_inferencia,
        "tooltips": tooltips,
        "alumno_id": alumno.id  # 👈 ESTA LÍNEA SOLUCIONA TU ERROR
    })







# Exportar estadisticas admin
from django.http import HttpResponse
import openpyxl
from openpyxl.utils import get_column_letter
from ..models import EvaluacionLecturaIndividual

def exportar_admin_estadisticas_excel(request):
    from ..models import RegistroUsuarios
    from .evaluacion_views import calcular_porcentaje

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Estadísticas por alumno"

    headers = ["Nombre", "Matrícula", "Textos leídos", "Puntaje total", "Porcentaje", "Nivel de comprensión"]
    ws.append(headers)

    usuarios = RegistroUsuarios.objects.all()
    for user in usuarios:
        lecturas = EvaluacionLecturaIndividual.objects.filter(usuario=user)
        total = lecturas.count()
        puntaje_total = sum([e.puntaje for e in lecturas if e.puntaje is not None])
        porcentaje = calcular_porcentaje(puntaje_total / total) if total else 0

        if total:
            if porcentaje >= 90:
                nivel = "Alto (Comprensión profunda)"
            elif porcentaje >= 60:
                nivel = "Medio (Comprensión adecuada)"
            elif porcentaje >= 30:
                nivel = "Bajo (Comprensión superficial)"
            else:
                nivel = "Deficiente (No comprensión)"
        else:
            nivel = "Sin evaluar"

        fila = [
            f"{user.nombre} {user.apellido}",
            user.matricula,
            total,
            puntaje_total,
            int(porcentaje),
            nivel
        ]
        ws.append(fila)

    for col in range(1, len(headers) + 1):
        ws.column_dimensions[get_column_letter(col)].auto_size = True

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename=admin_estadisticas_alumnos.xlsx'
    wb.save(response)
    return response


# Vista para exportar resultados globales
from django.http import HttpResponse
import openpyxl
from openpyxl.utils import get_column_letter
from ..models import EvaluacionLecturaIndividual

VAL_MAX = 3  # Si no está definido arriba, agrégalo

def exportar_admin_resultados_excel(request):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Resumen por tipo de texto"

    headers = ["Tipo de texto", "Documentos leídos", "Puntaje total", "Porcentaje", "Nivel de comprensión"]
    ws.append(headers)

    tipos = ["Argumentativo", "Descriptivo", "Expositivo", "Narrativo"]

    for tipo in tipos:
        lecturas = EvaluacionLecturaIndividual.objects.filter(tipo_texto=tipo)
        cantidad = lecturas.count()
        suma = sum([e.puntaje for e in lecturas if e.puntaje is not None])
        promedio = (suma / cantidad) if cantidad > 0 else 0
        porcentaje = (promedio / VAL_MAX * 100) if cantidad > 0 else 0

        if cantidad > 0:
            if porcentaje >= 90:
                nivel = f"Alto (Comprensión profunda) - {int(porcentaje)}%"
            elif porcentaje >= 60:
                nivel = f"Medio (Comprensión adecuada) - {int(porcentaje)}%"
            elif porcentaje >= 30:
                nivel = f"Bajo (Comprensión superficial) - {int(porcentaje)}%"
            else:
                nivel = f"Deficiente (No comprensión) - {int(porcentaje)}%"
        else:
            nivel = "Sin evaluar"

        fila = [tipo, cantidad, suma, int(porcentaje), nivel]
        ws.append(fila)

    for col in range(1, len(headers) + 1):
        ws.column_dimensions[get_column_letter(col)].auto_size = True

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename=admin_resultados_globales.xlsx'
    wb.save(response)
    return response



#-----------------------------------------------------------------------------
from django.db import connection
from django.shortcuts import render, redirect
from django.contrib import messages
from ..models import RegistroAdmin, RegistroUsuarios, EvaluacionLectura, EvaluacionLecturaIndividual, VistaAdmin

def reset_auto_increment(tabla):
    with connection.cursor() as cursor:
        cursor.execute(f"ALTER TABLE {tabla} AUTO_INCREMENT = 1")

def resetear_datos(request):
    if 'admin_id' not in request.session:
        return redirect('login_admin')  # validación personalizada
    if request.method == "POST":
        if "reset_todo" in request.POST:
            # Eliminar todo, incluyendo el admin actual
            RegistroUsuarios.objects.all().delete()
            RegistroAdmin.objects.all().delete()
            EvaluacionLectura.objects.all().delete()
            EvaluacionLecturaIndividual.objects.all().delete()
            VistaAdmin.objects.all().delete()

            reset_auto_increment("evaluacionescl_registrousuarios")
            reset_auto_increment("evaluacionescl_registroadmin")
            reset_auto_increment("evaluacionescl_evaluacionlectura")
            reset_auto_increment("evaluacionescl_evaluacionlecturaindividual")
            reset_auto_increment("evaluacionescl_vistaadmin")

            # Guardar mensaje antes de limpiar sesión
            add_message(request, messages.SUCCESS, "⚠️ Se reseteó TODO, incluyendo el admin en sesión.")

            # Limpiar la sesión y redirigir
            request.session.flush()
            return redirect("login_admin")

        elif "cancelar" in request.POST:
            messages.info(request, "🚫 Operación cancelada.")
            return redirect("dashboard_admin")

    return render(request, "evaluacionescl/resetear_datos_confirmacion.html")


#---------------------------------------------------------------------------------
# subir pdfs

import os
from django.conf import settings
from django.contrib import messages
from django.shortcuts import render, redirect

def subir_pdf(request):
    # mapa: nombre del input (minúscula) -> carpeta destino (Capitalizada)
    inputs_a_carpetas = {
        'argumentativo': 'Argumentativo',
        'descriptivo': 'Descriptivo',
        'expositivo': 'Expositivo',
        'narrativo': 'Narrativo',
    }

    if request.method == 'POST':
        subidos_ok = 0

        for input_name, carpeta in inputs_a_carpetas.items():
            archivo = request.FILES.get(input_name)

            if not archivo:
                messages.error(request, f"⚠ No se seleccionó archivo para '{carpeta}'.")
                continue

            # Validaciones de tipo
            es_pdf_ext = archivo.name.lower().endswith('.pdf')
            # algunos navegadores mandan 'application/pdf' (esperado) y otros variantes; toleramos ambas
            es_pdf_mime = getattr(archivo, 'content_type', '') in ('application/pdf', 'application/x-pdf')
            if not (es_pdf_ext or es_pdf_mime):
                messages.error(request, f"❌ El archivo '{archivo.name}' no parece ser un PDF válido.")
                continue

            # Carpeta destino (DEBE existir)
            ruta_destino = os.path.join(settings.MEDIA_ROOT, 'bancotext', carpeta)
            if not os.path.isdir(ruta_destino):
                messages.error(
                    request,
                    f"❌ La carpeta destino '{carpeta}' no existe en bancotext. "
                    "Verifica la estructura en el servidor."
                )
                continue  # no crearla

            # Normalizar nombre (evita espacios)
            nombre_archivo = archivo.name.replace(' ', '_')
            ruta_archivo = os.path.join(ruta_destino, nombre_archivo)

            # No sobrescribir
            if os.path.exists(ruta_archivo):
                messages.error(
                    request,
                    f"⚠ Ya existe un archivo llamado '{nombre_archivo}' en {carpeta}. "
                    "Cámbiale el nombre e inténtalo de nuevo."
                )
                continue

            # Guardado en chunks
            try:
                with open(ruta_archivo, 'wb+') as destino:
                    for chunk in archivo.chunks():
                        destino.write(chunk)
                subidos_ok += 1
                messages.success(request, f"✅ '{nombre_archivo}' subido a {carpeta}.")
            except Exception as e:
                messages.error(request, f"❌ Error al guardar '{nombre_archivo}': {e}")

        # Mensaje global al final del POST
        if subidos_ok > 0:
            messages.success(request, f"Se subieron exitosamente {subidos_ok} PDF(s).")
        else:
            messages.warning(request, "No se subió ningún PDF válido.")

        return redirect('subir_pdf')

    # Para GET
    return render(request, 'evaluacionescl/subir_pdf.html')

