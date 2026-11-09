#!/usr/bin/env python3
"""Horas más baratas de mañana (6.1TD): precio OMIE horario + peaje por periodo -> email."""
import os
import smtplib
from collections import defaultdict
from datetime import datetime, timedelta
from email.message import EmailMessage
from zoneinfo import ZoneInfo

import requests

# Peajes en €/MWh por periodo
PEAJES = {"P1": 46.274, "P2": 26.717, "P3": 12.928, "P4": 6.678, "P5": 2.619, "P6": 1.588}

# Tabla 6.1TD: un patrón por mes (ene..dic) para cada bloque horario
# A = horas 9-14 y 18-22 | B = horas 8-9, 14-18 y 22-24 | 0-8h siempre P6
A = ["P1", "P1", "P2", "P4", "P4", "P3", "P1", "P3", "P3", "P4", "P2", "P1"]
B = ["P2", "P2", "P3", "P5", "P5", "P4", "P2", "P4", "P4", "P5", "P3", "P2"]

# Festivos nacionales fijos (mes, día): cuentan como P6 todo el día. Revísalos.
FESTIVOS = {(1, 1), (1, 6), (5, 1), (8, 15), (10, 12), (11, 1), (12, 6), (12, 8), (12, 25)}


def periodo(fecha, hora):
    if fecha.weekday() >= 5 or (fecha.month, fecha.day) in FESTIVOS or hora < 8:
        return "P6"
    m = fecha.month - 1
    return A[m] if (9 <= hora < 14 or 18 <= hora < 22) else B[m]


TZ = ZoneInfo("Europe/Madrid")
TOP = 6  # cuántas horas baratas destacar


def precios_horarios(fecha):
    """Devuelve {hora: €/MWh} para España, promediando cuartos de hora si hace falta."""
    r = requests.get(
        "https://www.omie.es/es/file-download",
        params={"parents": "marginalpdbc", "filename": f"marginalpdbc_{fecha:%Y%m%d}.1"},
        timeout=30,
    )
    r.raise_for_status()
    filas = []
    for linea in r.text.splitlines():
        p = linea.strip().split(";")
        if len(p) >= 6 and p[0].isdigit():
            filas.append((int(p[3]), float(p[5].replace(",", "."))))
    if not filas:
        raise RuntimeError("OMIE aún no ha publicado el día siguiente")
    por_hora = 4 if max(n for n, _ in filas) > 30 else 1
    horas = defaultdict(list)
    for n, precio in filas:
        horas[(n - 1) // por_hora].append(precio)
    return {h: sum(v) / len(v) for h, v in horas.items()}


def main():
    manana = (datetime.now(TZ) + timedelta(days=1)).date()
    filas = []
    for h, omie in sorted(precios_horarios(manana).items()):
        per = periodo(manana, h)
        filas.append((h, per, omie, omie + PEAJES[per]))

    mejores = sorted(filas, key=lambda f: f[3])[:TOP]
    txt = [f"Horas más baratas de mañana ({manana:%d/%m/%Y}), OMIE + peaje en €/MWh:\n"]
    for h, per, e, t in sorted(mejores):
        txt.append(f"  {h:02d}:00-{h + 1:02d}:00  {per}  total {t:.2f}  (OMIE {e:.2f})")
    txt.append("\nTabla completa:")
    for h, per, e, t in filas:
        txt.append(f"  {h:02d}h  {per}  {t:.2f}")

    msg = EmailMessage()
    msg["Subject"] = f"Luz {manana:%d/%m}: horas más baratas"
    msg["From"] = os.environ["EMAIL_FROM"]
    msg["To"] = os.environ["EMAIL_TO"]
    msg.set_content("\n".join(txt))

    clave = os.environ["EMAIL_APP_PASSWORD"].replace(" ", "").replace("\xa0", "").strip()
    usuario = os.environ["EMAIL_FROM"].strip()
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as s:
        s.starttls()
        s.login(usuario, clave)
        s.send_message(msg)

if __name__ == "__main__":
    main()
