#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# ============================================================
# ENTRENAMIENTO BERT – OPTIMIZADO PARA CPU / RAM LIMITADA
# ============================================================
# - AdamW (torch.optim).
# - Micro-batching real para evitar picos de memoria.
# - padding="longest" y truncation="only_first" (ahorro de RAM).
# - Respuestas outlier: head+tail si superan RESP_MAX.
# - Guardado atómico del modelo.
# - Bitácora PREPEND (lo nuevo arriba) con [fecha] y secciones.
# - FIX: no usar .detach() antes de backward (para no romper el grafo).
# ============================================================

import os
import gc
import shutil
import pandas as pd
import torch
from torch.utils.data import Dataset, DataLoader
from torch.optim import AdamW
from transformers import BertTokenizer, BertForSequenceClassification
from datetime import datetime

# Limitar hilos BLAS (CPU chica más estable)
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

# -----------------------
# CONFIGURACIÓN GENERAL
# -----------------------
CARPETA_BASE    = "/var/www/sistemagclectura/"
RUTA_DATASET    = os.path.join(CARPETA_BASE, "dataset_principal.csv")
CARPETA_MODELO  = os.path.join(CARPETA_BASE, "trained_model/")
CARPETA_BACKUPS = os.path.join(CARPETA_BASE, "backups_modelos/")
LOG_FILE        = os.path.join(CARPETA_BASE, "reentrenamiento_log.txt")

BATCH_SIZE      = int(os.getenv("BATCH_SIZE", "8"))     # tamaño de lote macro
MICRO_BATCH     = int(os.getenv("MICRO_BATCH", "4"))    # sub-lote real
LEARNING_RATE   = float(os.getenv("LR", "5e-5"))
NUM_EPOCHS      = int(os.getenv("EPOCHS", "5"))

MAX_LEN         = int(os.getenv("MAX_LEN", "512"))
RESP_MAX        = int(os.getenv("RESP_MAX", "256"))
MODEL_NAME      = os.getenv("MODEL_NAME", "dccuchile/bert-base-spanish-wwm-cased")
NUM_LABELS      = int(os.getenv("NUM_LABELS", "5"))

# -----------------------
# BITÁCORA PREPEND (estilo claro)
# -----------------------
def registrar_progreso(mensaje: str, seccion: bool = False):
    """Escribe UNA línea al INICIO del log (nuevo arriba), con [fecha]."""
    fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if seccion:
        linea = f"[{fecha_hora}] ************ {mensaje} ************\n"
    else:
        linea = f"[{fecha_hora}] {mensaje}\n"

    try:
        old = ""
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
                old = f.read()
    except Exception:
        old = ""
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(linea + old)

# -----------------------
# DATASET
# -----------------------
class CustomInferenceDataset(Dataset):
    """Dataset con columnas: sentence (fragmento), inference (respuesta), label (int)."""
    def __init__(self, df: pd.DataFrame):
        self.s = df["sentence"].astype(str).tolist()
        self.i = df["inference"].astype(str).tolist()
        self.l = df["label"].astype(int).tolist()
    def __len__(self): return len(self.l)
    def __getitem__(self, idx: int):
        return {
            "sentence": self.s[idx],
            "inference": self.i[idx],
            "label": torch.tensor(self.l[idx], dtype=torch.long)
        }

# -----------------------
# UTILIDADES
# -----------------------
def hacer_backup_carpeta(origen: str, destino_base: str):
    """Backup simple de la carpeta del modelo a una subcarpeta con timestamp."""
    hoy = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    destino = os.path.join(destino_base, f"trained_model_backup_{hoy}")
    os.makedirs(destino, exist_ok=True)
    if os.path.isdir(origen):
        for archivo in os.listdir(origen):
            src, dst = os.path.join(origen, archivo), os.path.join(destino, archivo)
            if os.path.isfile(src):
                shutil.copy2(src, dst)
    registrar_progreso(f"Backup del modelo realizado en: {destino}")

def crear_modelo():
    """Carga modelo/tokenizer y selecciona CPU o GPU."""
    tokenizer = BertTokenizer.from_pretrained(MODEL_NAME)
    model = BertForSequenceClassification.from_pretrained(MODEL_NAME, num_labels=NUM_LABELS)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    registrar_progreso(f"Modelo/tokenizer listos. Dispositivo: {device}")
    return model, tokenizer

def truncate_head_tail_ids(ids, max_tokens):
    """Para respuestas outlier: conserva inicio+final de la respuesta (head+tail)."""
    if len(ids) <= max_tokens: return ids
    front = (max_tokens + 1) // 2
    tail  = max_tokens // 2
    return ids[:front] + ids[-tail:] if tail > 0 else ids[:front]

def forward_micro_batches(model, tokenizer, batch, device):
    """
    Procesa un batch en micro-batches (para ahorrar RAM).
    - Respuestas outlier: head+tail si superan RESP_MAX.
    - Fragmento: truncation='only_first'.
    - padding='longest' para no inflar.
    """
    sentences, inferences, labels = batch["sentence"], batch["inference"], batch["label"]
    total, start, losses = len(labels), 0, []

    while start < total:
        end = min(start + MICRO_BATCH, total)
        sentences_mb, inferences_mb = sentences[start:end], inferences[start:end]
        labels_mb = labels[start:end].to(device)

        # Truncar respuestas muy largas preservando inicio y final
        resp_proc = []
        for r in inferences_mb:
            ids = tokenizer.encode(r, add_special_tokens=False)
            if len(ids) > RESP_MAX:
                ids = truncate_head_tail_ids(ids, RESP_MAX)
            resp_proc.append(tokenizer.decode(ids, skip_special_tokens=True))

        enc = tokenizer(
            text=sentences_mb,
            text_pair=resp_proc,
            add_special_tokens=True,
            truncation="only_first",
            max_length=MAX_LEN,
            padding="longest",
            return_tensors="pt"
        )
        enc = {k: v.to(device) for k, v in enc.items()}

        outputs = model(**enc, labels=labels_mb)
        losses.append(outputs.loss)  # <<-- sin .detach(): mantiene grad_fn

        del enc, outputs
        if device.type == "cuda": torch.cuda.empty_cache()
        gc.collect()
        start = end

    return torch.stack(losses).mean()  # mantiene grad_fn para backward

def entrenar_modelo(model, tokenizer, dataloader):
    """Entrena por épocas con AdamW + micro-batching."""
    device = next(model.parameters()).device
    optimizer = AdamW(model.parameters(), lr=LEARNING_RATE)
    model.train()

    for epoch in range(NUM_EPOCHS):
        registrar_progreso(f"Época {epoch+1}/{NUM_EPOCHS}", seccion=True)
        pasos, acum_loss = 0, 0.0
        for batch in dataloader:
            loss = forward_micro_batches(model, tokenizer, batch, device)
            loss.backward()
            optimizer.step()
            optimizer.zero_grad()
            pasos += 1
            # Para promedio en bitácora usamos item() sin romper grafo del siguiente batch
            acum_loss += loss.detach().item()
            if pasos % 50 == 0:
                registrar_progreso(f"Batch {pasos}, Pérdida: {loss.detach().item():.6f}")
        registrar_progreso(f"Época {epoch+1} finalizada. Loss promedio: {acum_loss/max(1,pasos):.6f}")

    registrar_progreso("Entrenamiento completado.")

def guardar_modelo(model, tokenizer, carpeta_destino: str):
    """Guardado atómico: escribe en tmp y luego reemplaza la carpeta destino."""
    os.makedirs(carpeta_destino, exist_ok=True)
    tmp_dir = os.path.join(CARPETA_BASE, f"trained_model_tmp_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    os.makedirs(tmp_dir, exist_ok=True)
    model.save_pretrained(tmp_dir)
    tokenizer.save_pretrained(tmp_dir)
    if os.path.exists(carpeta_destino):
        shutil.rmtree(carpeta_destino)
    shutil.move(tmp_dir, carpeta_destino)
    registrar_progreso(f"Modelo actualizado en: {carpeta_destino}")

def main():
    registrar_progreso("INICIO DEL ENTRENAMIENTO", seccion=True)

    if not os.path.exists(RUTA_DATASET):
        registrar_progreso("❌ dataset_principal.csv no encontrado. Abortando.", seccion=True)
        raise FileNotFoundError(RUTA_DATASET)

    df_total = pd.read_csv(RUTA_DATASET)
    for col in ("sentence", "inference", "label"):
        if col not in df_total.columns:
            raise ValueError(f"Falta la columna '{col}' en dataset_principal.csv")
    registrar_progreso(f"Dataset cargado con {len(df_total)} registros.")

    os.makedirs(CARPETA_BACKUPS, exist_ok=True)
    hacer_backup_carpeta(CARPETA_MODELO, CARPETA_BACKUPS)

    dataset = CustomInferenceDataset(df_total)
    dataloader = DataLoader(dataset, batch_size=BATCH_SIZE, shuffle=True,
                            num_workers=0, pin_memory=False)

    model, tokenizer = crear_modelo()
    entrenar_modelo(model, tokenizer, dataloader)
    guardar_modelo(model, tokenizer, CARPETA_MODELO)

    with open(os.path.join(CARPETA_BASE, "ultima_fecha_entrenamiento.txt"), "w", encoding="utf-8") as f:
        f.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    registrar_progreso("Proceso de entrenamiento finalizado exitosamente.", seccion=True)

if __name__ == "__main__":
    main()
