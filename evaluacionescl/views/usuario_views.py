from django.shortcuts import render, redirect
from collections import defaultdict
from datetime import datetime
from django.utils.timezone import localtime
from ..models import RegistroUsuarios, EvaluacionLecturaIndividual, EvaluacionLectura

    
#def calcular_porcentaje(promedio):
    #VAL_MAX=3
    #if promedio is None:
        #return 0
    #return (promedio / VAL_MAX) * 100


def dashboard_usuario(request):
    if 'usuario_id' not in request.session:
        return redirect('login_usuario')

    usuario_id = request.session.get("usuario_id")
    nombre_usuario = request.session.get("nombre_usuario", '')
    usuario = RegistroUsuarios.objects.get(id=usuario_id)

    tipos = ["Argumentativo", "Descriptivo", "Expositivo", "Narrativo"]

    # 1. Obtener las fechas de EvaluacionLecturaIndividual
    individuales = EvaluacionLecturaIndividual.objects.filter(
        usuario=usuario,
        respuesta_usuario__isnull=False,
        puntaje__isnull=False
    )

    from collections import defaultdict
    from datetime import datetime
    from django.utils.timezone import localtime

    mes_tipo_set = defaultdict(set)
    for indiv in individuales:
        fecha_local = indiv.fecha_lectura
        mes_clave = fecha_local.strftime("%Y-%m")
        mes_tipo_set[mes_clave].add(indiv.tipo_texto)

    # 2. Obtener porcentajes reales de EvaluacionLectura
    resumenes = EvaluacionLectura.objects.filter(usuario=usuario)
    porcentajes_por_tipo = {r.tipo_texto: r.porcentaje or 0 for r in resumenes}

    # 3. Armar datos mensuales
    meses = []
    porcentajes = []
    meses_esp = {
        "Jan": "Ene", "Feb": "Feb", "Mar": "Mar", "Apr": "Abr", "May": "May",
        "Jun": "Jun", "Jul": "Jul", "Aug": "Ago", "Sep": "Sep",
        "Oct": "Oct", "Nov": "Nov", "Dec": "Dic"
    }

    for mes in sorted(mes_tipo_set.keys()):
        suma = sum([porcentajes_por_tipo.get(t, 0) for t in tipos])
        promedio = suma / 4
        porcentajes.append(round(promedio, 1))

        fecha_obj = datetime.strptime(mes, "%Y-%m")
        mes_abbr = fecha_obj.strftime("%b")
        mes_nombre = meses_esp.get(mes_abbr, mes_abbr)
        meses.append(f"{mes_nombre} {fecha_obj.year}")

    if porcentajes:
        ultimo = porcentajes[-1]
        if ultimo >= 90:
            nivel = "Alto (Comprensión profunda)"
        elif ultimo >= 60:
            nivel = "Medio (Comprensión adecuada)"
        elif ultimo >= 30:
            nivel = "Bajo (Comprensión superficial)"
        else:
            nivel = "Deficiente (No comprensión)"
    else:
        nivel = "Sin evaluar"

    return render(request, 'evaluacionescl/dashboard_usuario.html', {
        'nombre': nombre_usuario,
        'meses': meses,
        'porcentajes': porcentajes,
        'nivel_global': nivel
    })


def seleccion_tipo_texto(request):
    tipos_texto = ["Argumentativo", "Descriptivo", "Expositivo", "Narrativo"]

    if request.method == "POST":
        tipo_seleccionado = request.POST.get("tipo_texto_seleccionado")
        request.session["tipo_texto"] = tipo_seleccionado
        return redirect("mostrar_texto_pdf")

    return render(request, "evaluacionescl/seleccion_tipo_texto.html", {"tipos_texto": tipos_texto})

