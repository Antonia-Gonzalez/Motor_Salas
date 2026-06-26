# motor.py
import numpy as np
import pandas as pd

# =========================================================
# REGLAS INSTITUCIONALES CONSTANTES
# =========================================================
DOCT_ONLY_POSTGRADO = ["DOCT", "DOCT II"]
KIN_EXCLUSIVE_ROOM = "UDS 201"

INGENIERIAS = ["ICA", "ICC", "ICE", "ICI", "ING", "INM", "IOC"]
ADMIN = ["ADM", "DEM", "DER", "EAD", "EAI", "EAM", "ECN", "MAD"]

# =========================================================
# JUEGO DE REGLAS Y PRIORIDADES
# =========================================================
def prioridad_tipo(tipo, origen):
    tipo = str(tipo).upper()

    if origen == "POSTGRADO":
        orden = {"HIBR": 1, "CLAS": 2, "EXAM": 3, "PRBA": 3, "AYUD": 4}
    else:
        orden = {"CLAS": 1, "EXAM": 2, "PRBA": 2, "AYUD": 3}

    for k, v in orden.items():
        if k in tipo:
            return v
    return 99

def edificio_preferido(materia):
    materia = str(materia).upper()

    if any(x in materia for x in INGENIERIAS):
        return ["ING", "CIEN"]
    if any(x in materia for x in ADMIN):
        return ["CIEN", "REL", "BIB"]

    return ["HUM", "CEN", "REL", "CIEN"]

# =========================================================
# CAPA 1: VALIDACIONES DURAS (HARD CONSTRAINTS)
# =========================================================
def sala_valida(curso, sala):
    materia = str(curso.get("MATERIA", "")).upper()
    sala_name = str(sala.get("SALA", "")).upper()
    origen = curso.get("ORIGEN_BASE")

    # Regla DOCT
    if sala_name in DOCT_ONLY_POSTGRADO:
        return origen == "POSTGRADO"

    # Regla Kinesiología
    if materia == "KIN":
        return sala_name == KIN_EXCLUSIVE_ROOM

    if sala_name == KIN_EXCLUSIVE_ROOM:
        return materia == "KIN"

    return True

def colision(dia, horario, sala_id, ocupacion):
    # Coordenada espaciotemporal exacta en el mapa de bits del sistema
    return (sala_id, dia, horario) in ocupacion

# =========================================================
# CAPA 2: SCORING (SOFT CONSTRAINTS + RELAJACIÓN)
# =========================================================
def score_sala(curso, sala, ocup_sala, ocup_edif, relax):
    tipo = str(curso.get("TIPO_REUNION", ""))
    materia = curso.get("MATERIA", "")
    origen = curso.get("ORIGEN_BASE")

    score = 0

    # --- Lógica Postgrado ---
    if origen == "POSTGRADO":
        if "HIBR" in tipo:
            score += 0 if sala["TIPO_SALA"] in ["HYFLEX", "AUDITORIO", "AULA MAGNA"] else 10
        elif "CLAS" in tipo:
            score += 0 if (sala["TIPO_SALA"] in ["STREAMING", "NORMAL"] and sala["EDIFICIO"] == "REL") else 8
        elif "EXAM" in tipo or "PRBA" in tipo:
            score += 0 if sala["TIPO_SALA"] in ["PLANA", "STREAMING"] else 8
        elif "AYUD" in tipo:
            score += 2 if sala["TIPO_SALA"] == "NORMAL" else 5

    # --- Lógica Pregrado ---
    else:
        if "CLAS" in tipo:
            pref = edificio_preferido(materia)
            score += pref.index(sala["EDIFICIO"]) if sala["EDIFICIO"] in pref else 10
        elif "EXAM" in tipo or "PRBA" in tipo:
            score += 5
        elif "AYUD" in tipo:
            score += 3

    # --- Balance de Carga del Campus ---
    score += ocup_sala * 0.2
    score += ocup_edif * 0.5

    # --- Relajación como Penalización Matemática Estricta ---
    score += (100 - relax) * 0.1

    return score

# =========================================================
# CAPA 3: ENGINE PRINCIPAL DE ASIGNACIÓN
# =========================================================
def ejecutar_asignacion_escenario(archivo_cursos_excel, escenario_id, lista_salas, relax_level=90):
    # Carga nativa desde la pestaña correcta de la programación
    df_origen = pd.read_excel(archivo_cursos_excel, sheet_name="BASE PREGRADO")

    # Pre-procesamiento de Ranking Jerárquico Global (Pregrado vs Postgrado)
    df_origen["_p_origen"] = df_origen["ORIGEN_BASE"].apply(lambda x: 1 if x == "POSTGRADO" else 2)
    df_origen["_p_tipo"] = df_origen.apply(lambda r: prioridad_tipo(r.get("TIPO_REUNION", ""), r.get("ORIGEN_BASE", "")), axis=1)

    # Ordenamiento estable por criticidad de la asignación
    df_origen = df_origen.sort_values(by=["_p_origen", "_p_tipo", "CUPOS"], ascending=[True, True, False])
    cursos = df_origen.to_dict("records")

    # Inyección de IDs Unificados Libres de conflictos por strings duplicados
    for s in lista_salas:
        s["SALA_ID"] = f"{s['EDIFICIO']}_{s['SALA']}".replace(" ", "_")

    ocupacion = {}
    malla = []
    asignados = 0

    # Algoritmo de asignación óptimo de pasada única
    for c in list(cursos):
        mejor_s = None
        mejor_score = 1e9
        cupos_curso = c.get("CUPOS", 0)

        for s in lista_salas:
            # 1. Filtros Duros Iniciales
            if s["CAPACIDAD"] < cupos_curso:
                continue
            if not sala_valida(c, s):
                continue
            if colision(c.get("DIA"), c.get("HORARIO"), s["SALA_ID"], ocupacion):
                continue

            # Conteo dinámico en caliente para balancear la carga física
            occ_sala = sum(1 for k in ocupacion if k[0] == s["SALA_ID"])
            occ_edif = sum(1 for k in ocupacion if k[0].startswith(s["EDIFICIO"]))

            # 2. Evaluación de Aptitud (Score)
            sc = score_sala(c, s, occ_sala, occ_edif, relax_level)

            if sc < mejor_score:
                mejor_score = sc
                mejor_s = s

        # Registro del estado definitivo
        if mejor_s:
            ocupacion[(mejor_s["SALA_ID"], c.get("DIA"), c.get("HORARIO"))] = c["ID"]
            asignados += 1

            malla.append({
                **c, "SALA": mejor_s["SALA"], "EDIFICIO": mejor_s["EDIFICIO"],
                "TIPO_SALA": mejor_s["TIPO_SALA"], "ESTADO": "ASIGNADO", "MOTIVO_RECHAZO": "N/A"
            })
        else:
            malla.append({
                **c, "SALA": "SIN SALA", "EDIFICIO": "N/A", "TIPO_SALA": "N/A",
                "ESTADO": "SIN SALA", "MOTIVO_RECHAZO": "Capacidad insuficiente o colisión de horario insalvable"
            })

    df_res = pd.DataFrame(malla)

    # =========================================================
    # CAPA 4: ADAPTER / PROCESAMIENTO DE MÉTRICAS VISUALES
    # =========================================================
    metricas = []
    for s in lista_salas:
        occ = sum(1 for k in ocupacion if k[0] == s["SALA_ID"])
        metricas.append({
            "SALA": s["SALA"], "EDIFICIO": s["EDIFICIO"],
            "CAPACIDAD": s["CAPACIDAD"], "BLOQUES_OCUPADOS": occ,
            "HORAS_OCUPADAS": occ, "HORAS_LIBRES": max(0, 50 - occ)  # 50 bloques teóricos semanales
        })
    df_s = pd.DataFrame(metricas)

    resumen = {
        "total_cursos": len(cursos),
        "total_asignadas": asignados,
        "porcentaje_asignacion": round((asignados / len(cursos) * 100), 2) if len(cursos) > 0 else 0,
        "sin_sala": len(cursos) - asignados
    }

    df_sin_sala_only = df_res[df_res["ESTADO"] == "SIN SALA"]
    if not df_sin_sala_only.empty and "CARRERA" in df_sin_sala_only.columns:
        df_rech = df_sin_sala_only.groupby("CARRERA").size().reset_index(name="sin_sala")
    else:
        df_rech = pd.DataFrame(columns=["CARRERA", "sin_sala"])

    # 🔴 CONTRATO EXACTO CON EL UNPACK DE APP.PY (11 Objetos)
    return df_res, ocupacion, df_origen, resumen, df_s, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), df_rech
