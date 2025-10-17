import csv, io
from evaluacionescl.models import RegistroUsuarios, RegistroAdmin

def importar(path, modelo, etiqueta):
    # Leer archivo, quitar BOM y detectar delimitador
    with open(path, 'r', encoding='utf-8') as f:
        data = f.read()
    data = data.lstrip('\ufeff')  # quita BOM si está

    try:
        sample = '\n'.join(data.splitlines()[:2]) or 'matricula,sexo'
        dialect = csv.Sniffer().sniff(sample)
        delim = dialect.delimiter if dialect.delimiter in (',', ';') else ','
    except Exception:
        delim = ','

    reader = csv.DictReader(io.StringIO(data), delimiter=delim)

    # Normaliza encabezados
    if reader.fieldnames:
        reader.fieldnames = [h.strip().lower().lstrip('\ufeff') for h in reader.fieldnames]

    def getcol(row, *names):
        for n in names:
            if n in row and row[n] is not None:
                return row[n]
        return ''

    ok, fail = 0, []
    for i, row in enumerate(reader, start=2):
        mat = getcol(row, 'matricula', 'matrícula', 'id', 'mat').strip()
        sx  = getcol(row, 'sexo', 'genero', 'género').strip().upper()

        if not mat:
            fail.append((i, mat, sx, 'matricula vacía o columna mal nombrada'))
            continue
        if sx not in ('M', 'F', 'O'):
            fail.append((i, mat, sx, 'sexo inválido (usa M/F/O)'))
            continue

        try:
            obj = modelo.objects.get(matricula=mat)
            obj.sexo = sx
            obj.save(update_fields=['sexo'])
            ok += 1
        except modelo.DoesNotExist:
            fail.append((i, mat, sx, f'{etiqueta} no encontrado'))

    print(f'{etiqueta} actualizados OK:', ok)
    print(f'{etiqueta} fallidos:', fail)

# Ejecutar importación
importar('/var/www/sistemagclectura/sexo_pendientes_usuarios.csv', RegistroUsuarios, 'Usuario')
importar('/var/www/sistemagclectura/sexo_pendientes_admins.csv', RegistroAdmin, 'Admin')
