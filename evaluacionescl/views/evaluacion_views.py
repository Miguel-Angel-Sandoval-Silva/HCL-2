
import os
import random
import fitz
import spacy
import torch
import numpy as np
from torch.nn.functional import softmax
from transformers import BertTokenizer, BertForSequenceClassification
from django.shortcuts import render, redirect
from django.conf import settings
from ..models import RegistroUsuarios, EvaluacionLecturaIndividual, EvaluacionLectura, LecturaEnCurso, Lectura
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.utils import timezone

from evaluacionescl.models import LecturaEnCurso, RegistroUsuarios

# Cargar modelo NLP y BERT
import os

nlp = spacy.load("es_core_news_md")
model_path = "trained_model"

try:
    model = BertForSequenceClassification.from_pretrained(model_path)
    tokenizer = BertTokenizer.from_pretrained(model_path)
    if torch.cuda.is_available():
        model.to('cuda')
except Exception as e:
    model = None
    tokenizer = None
    print(f" No se pudo cargar el modelo o el tokenizer. Detalles: {e}")

CLASS_NAMES = [
    "asociativa", "elaborativa", "predictiva",
    "no_inferencia_parafrasis", "no_inferencia_sinsentido"
]


import re
import fitz

def extraer_texto_limpio(pdf_path):
    doc = fitz.open(pdf_path)
    texto = "\n".join(pagina.get_text("text") for pagina in doc)

    # Eliminar URLs
    texto = re.sub(r'https?://\S+|www\.\S+', '', texto)

    # Eliminar líneas con palabras como Referencias o Bibliografía
    texto = re.sub(r'(?i)^.*\b(Referencias|Bibliografía)\b.*$', '', texto, flags=re.MULTILINE)

    # Eliminar citas tipo (Apellido, Año)
    texto = re.sub(r'\([A-Z][a-z]+,\s*\d{4}\)', '', texto)

    # Eliminar referencias estilo científico tipo “2016;569-70:1545-52.”
    texto = re.sub(r'\d{4};\d+-\d+:\d+-\d+\.?', '', texto)

    # Eliminar nombres largos en mayúsculas (encabezados o instituciones)
    texto = re.sub(r'^[A-Z\s]{5,}$', '', texto, flags=re.MULTILINE)

    # Eliminar números de página sueltos
    texto = re.sub(r'^\s*\d+\s*$', '', texto, flags=re.MULTILINE)

    # Compactar texto, quitar saltos innecesarios
    texto = re.sub(r'\n+', '\n', texto)
    texto = re.sub(r'\s{2,}', ' ', texto).strip()

    return texto



import random
import spacy
nlp = spacy.load("es_core_news_md")

def segmentar_texto(texto, min_palabras=50, max_palabras=80):
    doc = nlp(texto)
    oraciones = [sent.text.strip() for sent in doc.sents if sent.text.strip()]

    fragmentos = []
    bloque = []
    total_palabras = 0

    for oracion in oraciones:
        palabras = len(oracion.split())
        if total_palabras + palabras <= max_palabras:
            bloque.append(oracion)
            total_palabras += palabras
        else:
            if total_palabras >= min_palabras:
                fragmentos.append(" ".join(bloque))
            bloque = [oracion]
            total_palabras = palabras

    if bloque and total_palabras >= min_palabras:
        fragmentos.append(" ".join(bloque))

    return random.choice(fragmentos) if fragmentos else ""


def calcular_puntaje(inf):
    return {
        "asociativa": 2,
        "elaborativa": 3,
        "predictiva": 3,
        "no_inferencia_parafrasis": 1,
        "no_inferencia_sinsentido": 0
    }.get(inf, 0)

def calcular_porcentaje(prom):
    return (prom / 3) * 100 if prom is not None else 0

from time import time

# ✅ 1. mostrar_texto_pdf (FINAL)

def mostrar_texto_pdf(request):
    tipo_texto = request.session.get("tipo_texto")
    usuario_id = request.session.get("usuario_id")
    if not tipo_texto or not usuario_id:
        return redirect("seleccion_tipo_texto")

    usuario = RegistroUsuarios.objects.get(id=usuario_id)

    # 1) Verificar si ya hay texto guardado en sesión
    texto_en_sesion = request.session.get(f"lectura_en_curso_{tipo_texto}")

    if texto_en_sesion:
        texto_seleccionado = texto_en_sesion
        es_pendiente = True
    else:
        # 2) Buscar respaldo en base de datos
        lectura_guardada = LecturaEnCurso.objects.filter(
            usuario=usuario, tipo_texto=tipo_texto
        ).first()

        if lectura_guardada:
            texto_seleccionado = lectura_guardada.titulo_lectura
            request.session[f"lectura_en_curso_{tipo_texto}"] = texto_seleccionado
            es_pendiente = True
        else:
            # 3) Buscar evaluación pendiente (ya iniciada en fragmento)
            pendiente = EvaluacionLecturaIndividual.objects.filter(
                usuario=usuario,
                tipo_texto=tipo_texto,
                respuesta_usuario__isnull=True
            ).first()

            if pendiente:
                texto_seleccionado = pendiente.titulo_lectura
                request.session[f"lectura_en_curso_{tipo_texto}"] = texto_seleccionado
                LecturaEnCurso.objects.update_or_create(
                    usuario=usuario,
                    tipo_texto=tipo_texto,
                    defaults={"titulo_lectura": texto_seleccionado}
                )
                es_pendiente = True
            else:
                # 4) Elegir nuevo texto no leído
                carpeta = os.path.join(settings.MEDIA_ROOT, "bancotext", tipo_texto)
                archivos = [f for f in os.listdir(carpeta) if f.endswith(".pdf")]

                leidos = EvaluacionLecturaIndividual.objects.filter(
                    usuario=usuario,
                    tipo_texto=tipo_texto,
                    respuesta_usuario__isnull=False
                ).values_list("titulo_lectura", flat=True)

                no_leidos = [a for a in archivos if a not in leidos]

                if not no_leidos:
                    return render(
                        request,
                        "evaluacionescl/no_textos_disponibles.html",
                        {"mensaje": "Has leído todos los textos de esta categoría."}
                    )

                texto_seleccionado = random.choice(no_leidos)
                request.session[f"lectura_en_curso_{tipo_texto}"] = texto_seleccionado
                es_pendiente = False
                # Guardar lectura en curso en la BD
                LecturaEnCurso.objects.update_or_create(
                    usuario=usuario,
                    tipo_texto=tipo_texto,
                    defaults={"titulo_lectura": texto_seleccionado}
                )

    # NUEVO: Garantiza el registro y prepara el tiempo acumulado
    lc, _ = LecturaEnCurso.objects.update_or_create(
        usuario=usuario,
        tipo_texto=tipo_texto,
        defaults={"titulo_lectura": texto_seleccionado}
    )

    # Si no está en pausa y no hay reloj corriendo, arráncalo
    if lc.ultimo_inicio is None and not lc.en_pausa:
        lc.ultimo_inicio = timezone.now()
        lc.save(update_fields=["ultimo_inicio"])

    initial_elapsed = lc.segundos_acumulados or 0.0

    ruta = f"{settings.MEDIA_URL}bancotext/{tipo_texto}/{texto_seleccionado}"

    return render(request, "evaluacionescl/mostrar_texto_pdf.html", {
        "ruta_texto": ruta,
        "titulo": texto_seleccionado,
        "timestamp": int(time()),
        "es_pendiente": es_pendiente,
        "tipo_texto": tipo_texto,
        "initial_elapsed": initial_elapsed,
    })

       


# ✅ 2. mostrar_fragment

def mostrar_fragmento(request):
    usuario_id = request.session.get("usuario_id")
    if not usuario_id:
        return redirect("login_usuario")

    usuario = RegistroUsuarios.objects.get(id=usuario_id)

    tipo_texto = request.GET.get("tipo") or request.session.get("tipo_texto")
    titulo = request.GET.get("titulo")

    tiempo_lectura = request.GET.get('tiempo_lectura_segundos', '0')

    if not tipo_texto or not titulo:
        return render(request, "evaluacionescl/no_fragmento.html", {
            "mensaje": "Aún no has seleccionado un texto para evaluar. Por favor, elige una categoría primero."
        })

    request.session["tipo_texto"] = tipo_texto

    # Buscar evaluación pendiente para ese texto
    evaluacion = EvaluacionLecturaIndividual.objects.filter(
        usuario=usuario,
        tipo_texto=tipo_texto,
        titulo_lectura=titulo,
        respuesta_usuario__isnull=True
    ).first()

    if evaluacion and evaluacion.fragmento != "pendiente" and evaluacion.fragmento.strip():
        # Ya hay fragmento generado, lo usamos
        return render(request, "evaluacionescl/fragmento_lectura.html", {
            "fragmento": evaluacion.fragmento,
            "instruccion": evaluacion.instruccion,
            "evaluacion_id": evaluacion.id,
            "es_pendiente": True,
            "tiempo_lectura": tiempo_lectura
        })

    # Si no hay evaluación previa o el fragmento está vacío, generamos nuevo
    if not evaluacion:
        evaluacion = EvaluacionLecturaIndividual.objects.create(
            usuario=usuario,
            tipo_texto=tipo_texto,
            titulo_lectura=titulo,
            fragmento="pendiente",
            instruccion="pendiente"
        )

    # Confirmamos que exista el PDF
    pdf_path = os.path.join(settings.MEDIA_ROOT, "bancotext", tipo_texto, titulo)

    if not os.path.exists(pdf_path):
        return render(request, "error.html", {"mensaje": "No se encontró el archivo del texto."})

    # Extraer texto limpio del PDF
    texto_limpio = extraer_texto_limpio(pdf_path)
    fragmento = segmentar_texto(texto_limpio)
    if not fragmento:
        return render(request, "error.html", {"mensaje": "No se pudo segmentar el texto correctamente."})

    # Elegir una instrucción aleatoria
    instrucciones = [
        "Escribe lo que entendiste del siguiente fragmento:",
        "¿A qué se refiere el siguiente fragmento?:",
        "Escribe con tus palabras la idea del siguiente fragmento:"
    ]
    instruccion = random.choice(instrucciones)

    # Guardar el fragmento y la instrucción
    evaluacion.fragmento = fragmento
    evaluacion.instruccion = instruccion
    evaluacion.save()

    return render(request, "evaluacionescl/fragmento_lectura.html", {
        "fragmento": fragmento,
        "instruccion": instruccion,
        "evaluacion_id": evaluacion.id,
        "es_pendiente": True,
        "tiempo_lectura": tiempo_lectura
    })

def classify_inference(sentence, inference):
    model.eval()
    with torch.no_grad():
        inputs = tokenizer.encode_plus(sentence, inference, return_tensors="pt", truncation=True, padding=True)
        if torch.cuda.is_available():
            inputs = {k: v.to('cuda') for k, v in inputs.items()}
        logits = model(**inputs).logits
        probs = softmax(logits, dim=1).cpu().numpy()[0]
        return CLASS_NAMES[probs.argmax()], probs

from django.contrib import messages  # Asegúrate de tener esto importado

# ✅ 3. guardar_respuesta (con limpieza de sesión)

def guardar_respuesta(request):
    if request.method == "POST":
        try:
            eval_id = int(request.POST.get("evaluacion_id"))
        except (TypeError, ValueError):
            messages.error(request, "ID de evaluación inválido.")
            return redirect("dashboard_usuario")
        
        respuesta = request.POST.get("respuesta", "").strip()
        
        try:
            evaluacion = EvaluacionLecturaIndividual.objects.get(id=eval_id)
        except EvaluacionLecturaIndividual.DoesNotExist:
            messages.error(request, "La evaluación no existe.")
            return redirect("dashboard_usuario")

        if not respuesta:
            messages.warning(request, "Debes escribir una respuesta antes de continuar.")
            return redirect(f"/mostrar_fragmento?titulo={evaluacion.titulo_lectura}&tipo={evaluacion.tipo_texto}")

        if evaluacion.respuesta_usuario:
            messages.warning(request, "Esta evaluación ya fue respondida.")
            return redirect("resultados_usuario")

        # --- Guardado de los datos de la evaluación actual ---
        evaluacion.respuesta_usuario = respuesta
        clase, _ = classify_inference(evaluacion.fragmento, respuesta)
        if not clase:
            clase = "no_inferencia_sinsentido"
        evaluacion.puntaje = calcular_puntaje(clase)
        evaluacion.tipo_inferencia = clase
        
        try:
            tiempo_lectura_segundos = float(request.POST.get('tiempo_lectura', 0))
            evaluacion.tiempo_lectura_segundos = tiempo_lectura_segundos

            # Corrección clave: reemplazar guiones bajos para buscar el título correctamente
            titulo_base = evaluacion.titulo_lectura.replace('.pdf', '').replace('_', ' ')
            lectura_obj = Lectura.objects.get(titulo=titulo_base, tipo_texto=evaluacion.tipo_texto)
            
            ppm = 0
            if tiempo_lectura_segundos > 0 and lectura_obj.conteo_palabras > 0:
                ppm = round((lectura_obj.conteo_palabras / tiempo_lectura_segundos) * 60)
            evaluacion.palabras_por_minuto = ppm
        except (Lectura.DoesNotExist, Exception) as e:
            print(f"ADVERTENCIA al calcular PPM: {e}")
        
        evaluacion.save() # Guardamos la evaluación individual con todos sus datos

        # --- LÓGICA FINAL PARA CALCULAR EL PROMEDIO PONDERADO ---
        usuario = evaluacion.usuario
        tipo = evaluacion.tipo_texto

        # 1. Obtenemos TODAS las evaluaciones completadas de este tipo para el usuario
        todas_las_evaluaciones = EvaluacionLecturaIndividual.objects.filter(
            usuario=usuario, tipo_texto=tipo, puntaje__isnull=False
        )
        
        puntajes_ponderados = []
        # 2. Calculamos el puntaje ponderado para CADA UNA de ellas
        for eval_individual in todas_las_evaluaciones:
            puntaje_inferencia = calcular_porcentaje(eval_individual.puntaje)
            
            ppm_eval = eval_individual.palabras_por_minuto or 0
            puntaje_velocidad = 50 # Por defecto es 'Bajo'
            if ppm_eval >= 230: puntaje_velocidad = 100
            elif ppm_eval >= 150: puntaje_velocidad = 75
            
            puntaje_final_ponderado = (puntaje_inferencia * 0.80) + (puntaje_velocidad * 0.20)
            puntajes_ponderados.append(puntaje_final_ponderado)

        # 3. Calculamos el promedio de todos los puntajes
        promedio_final = 0
        if puntajes_ponderados:
            promedio_final = sum(puntajes_ponderados) / len(puntajes_ponderados)

        # 4. Determinamos el nivel basado en el PROMEDIO
        if promedio_final >= 90: nivel = "Alto (Comprensión profunda)"
        elif promedio_final >= 60: nivel = "Medio (Comprensión adecuada)"
        elif promedio_final >= 30: nivel = "Bajo (Comprensión superficial)"
        else: nivel = "Deficiente (No comprensión)"
            
        # 5. Guardamos o actualizamos el resumen con los datos promediados correctos
        EvaluacionLectura.objects.update_or_create(
            usuario=usuario,
            tipo_texto=tipo,
            defaults={
                'textos_leidos': todas_las_evaluaciones.count(),
                'porcentaje': promedio_final,
                'nivel_comprension': nivel
            }
        )
        
        # --- Limpieza de sesión ---
        request.session.pop(f"lectura_en_curso_{tipo}", None)
        LecturaEnCurso.objects.filter(usuario=usuario, tipo_texto=tipo).delete()

        return redirect("resultados_usuario")

    return redirect("dashboard_usuario")

def resultados_usuario(request):
    usuario_id = request.session.get("usuario_id")
    if not usuario_id:
        return redirect("login_usuario")

    usuario = RegistroUsuarios.objects.get(id=usuario_id)
    tipos = ["Argumentativo", "Descriptivo", "Expositivo", "Narrativo"]
    resultados = []

    for tipo in tipos:
        resumen = EvaluacionLectura.objects.filter(usuario=usuario, tipo_texto=tipo).first()

        if resumen:
            total = resumen.textos_leidos
            porcentaje = resumen.porcentaje or 0
            if porcentaje >= 90:
                nivel = f"Alto (Comprensión profunda) - {int(porcentaje)}%"
            elif porcentaje >= 60:
                nivel = f"Medio (Comprensión adecuada) - {int(porcentaje)}%"
            elif porcentaje >= 30:
                nivel = f"Bajo (Comprensión superficial) - {int(porcentaje)}%"

            else:
                nivel = f"Deficiente (No comprensión) - {int(porcentaje)}%"
        else:
            total = 0
            nivel = "Sin evaluar"

        resultados.append({"tipo": tipo, "cantidad": total, "nivel": nivel})

    # Última inferencia del usuario
    ultima_eval = EvaluacionLecturaIndividual.objects.filter(
        usuario=usuario,
        tipo_inferencia__isnull=False
    ).order_by("-fecha_lectura").first()

    inferencia_limpia = "Sin evaluar"
    if ultima_eval and ultima_eval.tipo_inferencia:
        tipo = ultima_eval.tipo_inferencia
        if tipo == "no_inferencia_sinsentido":
            inferencia_limpia = "No inferencia: sin sentido"
        elif tipo == "no_inferencia_parafrasis":
            inferencia_limpia = "No inferencia: paráfrasis"
        else:
            inferencia_limpia = tipo.capitalize()

    # ✅ Evaluaciones pendientes (solo si NO hay ninguna finalizada del tipo)
        # ✅ Evaluaciones pendientes
    pendientes = []
    for tipo_texto in tipos:
        tiene_pendiente = EvaluacionLecturaIndividual.objects.filter(
            usuario=usuario,
            tipo_texto=tipo_texto,
            respuesta_usuario__isnull=True
        ).exists()

        if tiene_pendiente:
            pendientes.append(tipo_texto)

    return render(request, "evaluacionescl/tabla_resultados.html", {
        "resultados": resultados,
        "ultima_inferencia": inferencia_limpia,
        "pendientes": pendientes,
        "ultima_eval": ultima_eval
    })

# ✅ 5. ver_grafica_tipo (con título, fecha y hora en líneas separadas)
# ✅ 5. ver_grafica_tipo (con multilínea real para Chart.js)

def ver_grafica_tipo(request, tipo_texto):
    usuario_id = request.session.get("usuario_id")
    if not usuario_id:
        return redirect("login_usuario")

    usuario = RegistroUsuarios.objects.get(id=usuario_id)
    lecturas = EvaluacionLecturaIndividual.objects.filter(
        usuario=usuario,
        tipo_texto=tipo_texto
    ).order_by('fecha_lectura')

    if not lecturas.exists():
        return render(request, "evaluacionescl/no_fragmento.html", {"mensaje": "No hay lecturas evaluadas de este tipo todavía."})

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

            puntaje_inferencia = calcular_porcentaje(l.puntaje) if l.puntaje is not None else 0
            
            # 2. Puntaje de velocidad (0-100)
            ppm = l.palabras_por_minuto or 0
            puntaje_velocidad = 50 # Por defecto es 'Bajo'
            if ppm >= 230:
                puntaje_velocidad = 100
            elif ppm >= 150:
                puntaje_velocidad = 75
            
            # 3. Aplicar fórmula ponderada
            porcentaje_ponderado = (puntaje_inferencia * 0.80) + (puntaje_velocidad * 0.20)
            
            porcentajes.append(porcentaje_ponderado)
            tooltips.append(f"{int(porcentaje_ponderado)}%")

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

    return render(request, "evaluacionescl/grafica_texto_tipo.html", {
        "tipo": tipo_texto,
        "titulos": titulos,
        "porcentajes": porcentajes,
        "tipos_inferencia": tipos_inferencia,
        "tooltips": tooltips
    })
@require_POST
def pausar_lectura(request):
    usuario_id = request.session.get("usuario_id")
    if not usuario_id:
        return JsonResponse({"ok": False, "error": "no-auth"}, status=401)

    titulo = request.POST.get("titulo")
    tipo = request.POST.get("tipo")
    if not (titulo and tipo):
        return JsonResponse({"ok": False, "error": "bad-params"}, status=400)

    usuario = RegistroUsuarios.objects.get(id=usuario_id)
    try:
        lc = LecturaEnCurso.objects.get(
            usuario=usuario, tipo_texto=tipo, titulo_lectura=titulo
        )
    except LecturaEnCurso.DoesNotExist:
        return JsonResponse({"ok": False, "error": "not-found"}, status=404)

    if lc.ultimo_inicio and not lc.en_pausa:
        delta = (timezone.now() - lc.ultimo_inicio).total_seconds()
        lc.segundos_acumulados = (lc.segundos_acumulados or 0) + max(0, delta)

    lc.en_pausa = True
    lc.ultimo_inicio = None
    lc.save(update_fields=["segundos_acumulados", "en_pausa", "ultimo_inicio"])
    return JsonResponse({"ok": True, "segundos_acumulados": round(lc.segundos_acumulados, 2)})


@require_POST
def reanudar_lectura(request):
    usuario_id = request.session.get("usuario_id")
    if not usuario_id:
        return JsonResponse({"ok": False, "error": "no-auth"}, status=401)

    titulo = request.POST.get("titulo")
    tipo = request.POST.get("tipo")
    if not (titulo and tipo):
        return JsonResponse({"ok": False, "error": "bad-params"}, status=400)

    usuario = RegistroUsuarios.objects.get(id=usuario_id)
    lc, _ = LecturaEnCurso.objects.get_or_create(
        usuario=usuario, tipo_texto=tipo, titulo_lectura=titulo
    )

    if lc.en_pausa or lc.ultimo_inicio is None:
        lc.ultimo_inicio = timezone.now()
        lc.en_pausa = False
        lc.save(update_fields=["ultimo_inicio", "en_pausa"])

    return JsonResponse({"ok": True, "segundos_acumulados": round(lc.segundos_acumulados or 0, 2)})

#--------------------------------------------------------------------
