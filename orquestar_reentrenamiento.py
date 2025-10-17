#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Orquestador de reentrenamiento (bitácora PREPEND: lo nuevo arriba, estilo claro):

Flujo:
1) Lee dataset_principal.csv (total actual).
2) Consulta BD por registros NUEVOS (fragmento+respuesta) > last_id.
   - Descarta duplicados (si ya están en el CSV).
   - Descarta repetidos dentro de esta misma corrida.
3) Si hay suficientes (>= MIN_NUEVAS) o si FORCE_TRAIN=1:
   - Respalda el modelo comprimido (.tar.gz, conserva solo 3).
   - Agrega NUEVAS al CSV (append) —NO borra lo previo—.
   - Llama a entrenar_modelo.py.
4) Todo se escribe en reentrenamiento_log.txt con fecha en [..] y secciones con ************.
"""

import os, csv, tarfile, subprocess, datetime, json
from pathlib import Path
import mysql.connector  # pip install mysql-connector-python

# --------------------------
# Configuración
# --------------------------
BASE_DIR     = Path("/var/www/sistemagclectura")
DATASET_CSV  = BASE_DIR / "dataset_principal.csv"       # columnas: sentence,inference,label
LOG_FILE     = BASE_DIR / "reentrenamiento_log.txt"     # PREPEND
STATE_JSON   = BASE_DIR / "estado_orq.json"             # interno {"last_id": int}

TRAIN_SCRIPT = BASE_DIR / "entrenar_modelo.py"
VENV_PY      = BASE_DIR / "venv/bin/python3"

MODEL_DIR    = BASE_DIR / "trained_model"
BACKUP_DIR   = BASE_DIR / "backups_modelos"
MAX_BACKUPS  = 3
MIN_NUEVAS   = 100

# BD (usuario con permisos)
DB_HOST = "localhost"
DB_USER = "miros"
DB_PASS = "Kmslectura2025!"
DB_NAME = "kmslectura"
DB_PORT = 3306

TABLE   = "evaluacionescl_evaluacionlecturaindividual"
COL_ID  = "id"
COL_FRG = "fragmento"
COL_RSP = "respuesta_usuario"
COL_TAG = "tipo_inferencia"

# Mapa de etiquetas a IDs
ETIQUETAS = {
    "asociativa": 0,
    "elaborativa": 1,
    "predictiva": 2,
    "no_inferencia_parafrasis": 3,
    "no_inferencia_sinsentido": 4,
}

# --------------------------
# Bitácora PREPEND (lo nuevo arriba)
# --------------------------
def _ts():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def log(msg, seccion=False):
    """Inserta UNA o varias líneas al INICIO del log (nuevo arriba)."""
    if isinstance(msg, list):
        lines = msg
    else:
        lines = [msg]

    stamped = []
    for ln in lines:
        if seccion:
            stamped.append(f"[{_ts()}] ************ {ln} ************")
        else:
            stamped.append(f"[{_ts()}] {ln}")
    block = "\n".join(stamped) + "\n"

    try:
        old = LOG_FILE.read_text(encoding="utf-8", errors="ignore") if LOG_FILE.exists() else ""
    except Exception:
        old = ""
    LOG_FILE.write_text(block + old, encoding="utf-8")

# --------------------------
# Estado interno (no se loguea)
# --------------------------
def _load_last_id():
    try:
        if STATE_JSON.exists():
            d = json.loads(STATE_JSON.read_text(encoding="utf-8"))
            return int(d.get("last_id", 0))
    except Exception:
        pass
    return 0

def _save_last_id(last_id):
    try:
        STATE_JSON.write_text(json.dumps({"last_id": int(last_id)}, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass

# --------------------------
# IO / BD / backups
# --------------------------
def _conectar_bd():
    return mysql.connector.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASS, database=DB_NAME, port=DB_PORT
    )

def _leer_pares_existentes():
    """Lee el CSV 1 sola vez y arma set sentence||inference para detectar duplicados."""
    if not DATASET_CSV.exists():
        return set(), 0
    pares, total = set(), 0
    with open(DATASET_CSV, "r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            total += 1
            s = (row.get("sentence") or "").strip().lower()
            i = (row.get("inference") or "").strip().lower()
            pares.add(s + "||" + i)
    return pares, total

def _append_al_dataset(filas):
    """Agrega filas NUEVAS al CSV (append). NO borra lo previo."""
    header_needed = not DATASET_CSV.exists()
    with open(DATASET_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if header_needed:
            w.writerow(["sentence","inference","label"])
        for r in filas:
            w.writerow([r["sentence"], r["inference"], r["label"]])

def _backup_modelo():
    """Crea .tar.gz de trained_model/ y mantiene solo 3 más recientes."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    if not MODEL_DIR.exists():
        log("No existe la carpeta del modelo; se omite el respaldo.")
        return None
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    tarpath = BACKUP_DIR / f"model_{stamp}.tar.gz"
    with tarfile.open(tarpath, "w:gz") as tar:
        tar.add(MODEL_DIR, arcname=MODEL_DIR.name)
    backs = sorted(BACKUP_DIR.glob("model_*.tar.gz"))
    if len(backs) > MAX_BACKUPS:
        for p in backs[0:len(backs)-MAX_BACKUPS]:
            try: p.unlink()
            except: pass
    log(f"Se creó un respaldo del modelo: {tarpath.name}")
    return tarpath

def _run_training():
    """Lanza el script de entrenamiento; captura salida por si falla."""
    proc = subprocess.run(
        [str(VENV_PY), str(TRAIN_SCRIPT)],
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True
    )
    return proc.returncode, proc.stdout, proc.stderr

# --------------------------
# Proceso principal
# --------------------------
def main():
    log("INICIO DEL PROCESO DE REENTRENAMIENTO", seccion=True)

    # 1) Dataset actual
    try:
        pares_exist, base_count = _leer_pares_existentes()
        log(f"El dataset actual tiene {base_count} registros.")
    except Exception as e:
        log([f"Error al leer dataset_principal.csv: {e}",
             "Fin del proceso (error al leer el dataset)."], seccion=True)
        return

    # 2) Revisar BD (solo nuevo) y recolectar hasta MIN_NUEVAS
    last_id = _load_last_id()
    nuevas, repetidas_dataset, repetidas_lote = [], 0, 0
    visto_lote, max_id_visto = set(), last_id

    try:
        cn = _conectar_bd()
        cur = cn.cursor(dictionary=True)
        q = (f"SELECT {COL_ID}, {COL_FRG}, {COL_RSP}, {COL_TAG} "
             f"FROM {TABLE} "
             f"WHERE {COL_ID} > %s AND {COL_TAG} IS NOT NULL AND {COL_FRG} IS NOT NULL AND {COL_RSP} IS NOT NULL "
             f"ORDER BY {COL_ID} ASC")
        cur.execute(q, (last_id,))
        for row in cur:
            rid  = int(row[COL_ID])
            frag = (row[COL_FRG] or "").strip()
            resp = (row[COL_RSP] or "").strip()
            typ  = (row[COL_TAG] or "").strip().lower() or "no_inferencia_sinsentido"

            if rid > max_id_visto:
                max_id_visto = rid
            if typ not in ETIQUETAS:
                continue

            clave = frag.lower() + "||" + resp.lower()
            if clave in pares_exist:
                repetidas_dataset += 1
                continue
            if clave in visto_lote:
                repetidas_lote += 1
                continue

            visto_lote.add(clave)
            nuevas.append({"sentence": frag, "inference": resp, "label": ETIQUETAS[typ]})

            if len(nuevas) >= MIN_NUEVAS:
                break

        cur.close(); cn.close()
    except Exception as e:
        log([f"Error al leer la base de datos: {e}",
             "Fin del proceso (error en la BD)."], seccion=True)
        return

    # 3) Resumen entendible
    log("VERIFICACIÓN DEL DATASET", seccion=True)
    log(f"Duplicados encontrados (ya estaban en el dataset): {repetidas_dataset}")
    log(f"Duplicados dentro de esta corrida: {repetidas_lote}")
    log(f"Nuevas inferencias detectadas: {len(nuevas)}")

    # 4) ¿Entrenamiento forzado?
    force = (os.getenv("FORCE_TRAIN") == "1")
    if len(nuevas) < MIN_NUEVAS and not force:
        log(["No hay suficientes nuevas inferencias. No se entrenará en esta ocasión.",
             "Fin del proceso."], seccion=True)
        _save_last_id(max_id_visto)  # interno
        return

    if force and len(nuevas) == 0:
        log("Entrenamiento forzado: se usará el dataset actual (sin nuevas).")
    elif force and len(nuevas) > 0:
        log(f"Entrenamiento forzado: se agregarán {len(nuevas)} nuevas y se entrenará.")

    # 5) Agregar nuevas (si hay) → el dataset crece
    nuevas_count = len(nuevas)
    total_para_entrenar = base_count
    if nuevas_count > 0:
        try:
            _append_al_dataset(nuevas)
            total_para_entrenar = base_count + nuevas_count
            log(f"Se agregaron {nuevas_count} nuevas inferencias. Total ahora: {total_para_entrenar}.")
        except Exception as e:
            log([f"Error al agregar nuevas inferencias al dataset: {e}",
                 "Fin del proceso (error al actualizar el dataset)."], seccion=True)
            return
    else:
        log("No se agregaron nuevas inferencias al dataset.")

    # 6) Guardar hasta qué id llegamos (interno)
    _save_last_id(max_id_visto)

    # 7) Respaldo comprimido del modelo
    try:
        _backup_modelo()
    except Exception as e:
        log(f"Error al crear el respaldo del modelo (se continúa): {e}")

    # 8) Entrenamiento
    if nuevas_count > 0:
        log(f"Inicia entrenamiento del modelo (con {nuevas_count} nuevas y {total_para_entrenar} en total).", seccion=True)
    else:
        log(f"Inicia entrenamiento del modelo (sin nuevas; {total_para_entrenar} en total).", seccion=True)

    code, out, err = _run_training()

    if code == 0:
        log("Entrenamiento finalizado correctamente.", seccion=True)
        if nuevas_count > 0:
            log(f"El modelo se entrenó con {nuevas_count} nuevas inferencias; total usado: {total_para_entrenar}.")
        else:
            log(f"El modelo se entrenó sin nuevas inferencias; total usado: {total_para_entrenar}.")
    else:
        log("Error durante el entrenamiento.", seccion=True)
        if out: log(f"STDOUT: {out[-1000:]}")
        if err: log(f"STDERR: {err[-1000:]}")

    log("Fin del proceso de reentrenamiento.", seccion=True)

if __name__ == "__main__":
    main()
