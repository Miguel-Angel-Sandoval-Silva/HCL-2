from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from .views import registro_usuario, registro_admin, login_usuario, login_admin, logout_usuario, dashboard_usuario, dashboard_admin, seleccion_tipo_texto, mostrar_texto_pdf, resultados_usuario, ver_grafica_tipo, admin_resultados, admin_estadisticas, mostrar_fragmento, guardar_respuesta, ver_resultados_alumno, ver_grafica_alumno_tipo, exportar_admin_estadisticas_excel, exportar_admin_resultados_excel, resetear_datos, eliminar_usuario, logout_admin,verificar_matricula_usuario,verificar_matricula_admin,subir_pdf

urlpatterns = [
    path('registro_usuario/', registro_usuario, name='registro_usuario'),
    path('verificar_matricula_usuario/',verificar_matricula_usuario, name='verificar_matricula_usuario'),
    path('registro_admin/', registro_admin, name='registro_admin'),
    path('verificar_matricula_admin/', verificar_matricula_admin, name='verificar_matricula_admin'),
    path('login_usuario/', login_usuario, name='login_usuario'),
    path('login_admin/', login_admin, name='login_admin'),
    path('logout_usuario/', logout_usuario, name='logout_usuario'),
    path('logout_admin/', logout_admin, name='logout_admin'),
    path('dashboard_usuario/', dashboard_usuario, name='dashboard_usuario'),
    path('seleccion_tipo_texto/', seleccion_tipo_texto, name='seleccion_tipo_texto'),
    path('mostrar_texto_pdf/', mostrar_texto_pdf, name='mostrar_texto_pdf'),
    path('resultados_usuario/', resultados_usuario, name='resultados_usuario'),
    path('grafica/<str:tipo_texto>/', ver_grafica_tipo, name='ver_grafica_tipo'),
    path('dashboard_admin/', dashboard_admin, name='dashboard_admin'),
    path('admin_resultados/', admin_resultados, name='admin_resultados'),
    path('admin_estadisticas/', admin_estadisticas, name='admin_estadisticas'),
    path('subir-pdf/', subir_pdf, name='subir_pdf'),
    path('mostrar_fragmento/', mostrar_fragmento, name='mostrar_fragmento'),
    path('guardar_respuesta/', guardar_respuesta, name='guardar_respuesta'),
    path("ver_resultados_alumno/<int:usuario_id>/", ver_resultados_alumno, name="ver_resultados_alumno"),
    path("ver_grafica_alumno_tipo/<int:usuario_id>/<str:tipo_texto>/", ver_grafica_alumno_tipo, name="ver_grafica_alumno_tipo"),
    path("exportar_estadisticas_excel/", exportar_admin_estadisticas_excel, name="exportar_estadisticas_excel"),
    path("exportar_resultados_excel/", exportar_admin_resultados_excel, name="exportar_resultados_excel"),
    path("resetear_datos/", resetear_datos, name="resetear_datos"),
    path('eliminar_usuario/<int:usuario_id>/', eliminar_usuario, name='eliminar_usuario'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
