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
TIPOS_PERMITIDOS = ["HIBR", "CLAS", "EXAM", "PRBA", "AYUD"]

def prioridad_tipo(tipo, origen):
    tipo = str(tipo).upper()
    if origen == "POSTGRADO":
        orden = {"HIBR": 1, "CLAS": 2, "EXAM": 3, "PRBA": 3, "AYUD": 4}
    else:
        orden = {"CLAS": 1, "EXAM": 2, "PRBA": 2, "AYUD": 3}
    for k, v in orden.items():
        if k in tipo: return v
    return 99

def edificio_preferido(materia):
    materia = str(materia).upper()
    if any(x in materia for x in INGENIERIAS):
        return ["ING"]
    if any(x in materia for x in ADMIN):
        return ["CIEN", "REL", "BIB"]
    return ["HUM", "CEN", "REL", "CIEN", "BIB"]

# =========================================================
# VALIDACIONES DURAS (HARD CONSTRAINTS)
# =========================================================
def sala_valida(curso, sala):
    materia = str(curso.get("MATERIA", "")).upper()
    sala_name = str(sala.get("SALA", "")).upper()
    origen = curso.get("ORIGEN_BASE")

    if sala_name in DOCT_ONLY_POSTGRADO: return origen == "POSTGRADO"
    if materia == "KIN": return sala_name == KIN_EXCLUSIVE_ROOM
    if sala_name == KIN_EXCLUSIVE_ROOM: return materia == "KIN"
    return True

def colision(dia, horario, sala_id, ocupacion, lista_cruzada_actual=""):
    if (sala_id, dia, horario) in ocupacion:
        info_ocupante = ocupacion[(sala_id, dia, horario)]
        if (lista_cruzada_actual != "" and 
            isinstance(info_ocupante, dict) and 
            info_ocupante.get("LISTA_CRUZADA") == lista_cruzada_actual):
            return False
        return True
    return False

# =========================================================
# CAPA 2: SCORING (📌 PUNTO 2: PENALIZACIÓN POR DESPERDICIO)
# =========================================================
def score_sala(curso, sala, occ_sala, occ_edif, cupos_conjunto):
    # Ya no metemos el relax aquí. Esto calcula idoneidad física pura.
    tipo = str(curso.get("TIPO", ""))
    materia = str(curso.get("MATERIA", ""))
    origen = curso.get("ORIGEN_BASE")
    tipo_sala_infra = str(sala.get("TIPO DE SALA", "")).upper()

    score = 0
    # --- Idoneidad Pedagógica ---
    if origen == "POSTGRADO":
        if "HIBR" in tipo: score += 0 if tipo_sala_infra in ["HYFLEX", "AUDITORIO", "AULA MAGNA"] else 10
        elif "CLAS" in tipo: score += 0 if (tipo_sala_infra in ["STREAMING", "NORMAL"] and sala["EDIFICIO"] == "REL") else 8
        elif "EXAM" in tipo or "PRBA" in tipo: score += 0 if tipo_sala_infra in ["PLANA", "STREAMING"] else 8
        elif "AYUD" in tipo: score += 2 if tipo_sala_infra == "NORMAL" else 5
    else:
        if "CLAS" in tipo:
            pref = edificio_preferido(materia)
            score += pref.index(sala["EDIFICIO"]) if sala["EDIFICIO"] in pref else 10
        elif "EXAM" in tipo or "PRBA" in tipo: score += 5
        elif "AYUD" in tipo: score += 3

    # 📌 PUNTO 2: Castigo matemático al desperdicio de asientos (Eficiencia de Espacio)
    desperdicio = sala["CAPACIDAD"] - cupos_conjunto
    score += desperdicio * 0.05

    # Balance de carga complementario
    score += occ_sala * 0.2 + occ_edif * 0.5
    return score

# =========================================================
# ENGINE PRINCIPAL REESTRUCTURADO
# =========================================================
def ejecutar_asignacion_escenario(df_cursos, lista_salas_origen, relax_level=90, ocupacion_previa=None, id_corrida="GLOBAL_RUN"):
    # Inicialización del Objeto Escenario unificado en caso de error
    if df_cursos.empty:
        return {"malla": pd.DataFrame(), "ocupacion": {}, "resumen": {"total_cursos": 0, "total_asignadas": 0}, "metricas": pd.DataFrame(), "rechazos": pd.DataFrame()}

    # 📌 PUNTO 4: Clonación profunda protectora
    lista_salas = [s.copy() for s in lista_salas_origen]
    for s in lista_salas:
        s["SALA_ID"] = f"{s['EDIFICIO']}_{s['SALA']}".replace(" ", "_")

    df_origen = df_cursos.copy()
    if "TIPO" in df_origen.columns:
        df_origen["TIPO"] = df_origen["TIPO"].fillna("DESCONOCIDO").astype(str)
        mascara_permitidos = df_origen["TIPO"].str.upper().apply(lambda x: any(t in x for t in TIPOS_PERMITIDOS))
        df_origen = df_origen[mascara_permitidos].reset_index(drop=True)
    
    df_origen["CARRERA"] = df_origen["MATERIA"] if "MATERIA" in df_origen.columns else "DESCONOCIDA"

    # Linealización Horaria
    dias_columnas = ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES", "SABADO"]
    registros_planos = []
    for item in df_origen.to_dict("records"):
        tiene_horarios = False
        for dia in dias_columnas:
            val_dia = item.get(dia)
            if pd.notna(val_dia) and str(val_dia).strip() != "" and "-" in str(val_dia):
                nuevo_bloque = item.copy()
                nuevo_bloque["DIA"] = dia
                nuevo_bloque["HORARIO"] = str(val_dia).strip()
                registros_planos.append(nuevo_bloque)
                tiene_horarios = True
        if not tiene_horarios:
            nuevo_bloque = item.copy()
            nuevo_bloque["DIA"] = "SIN DIA"
            nuevo_bloque["HORARIO"] = "SIN HORARIO"
            registros_planos.append(nuevo_bloque)

    df_procesable = pd.DataFrame(registros_planos)
    if df_procesable.empty:
        return {"malla": pd.DataFrame(), "ocupacion": {}, "resumen": {"total_cursos": 0, "total_asignadas": 0}, "metricas": pd.DataFrame(), "rechazos": pd.DataFrame()}

    df_procesable["LISTA CRUZADA"] = df_procesable["LISTA CRUZADA"].fillna("").astype(str).str.strip() if "LISTA CRUZADA" in df_procesable.columns else ""
    df_procesable["_p_origen"] = np.where(df_procesable["ORIGEN_BASE"] == "POSTGRADO", 1, 2)
    df_procesable["_p_tipo"] = df_procesable.apply(lambda r: prioridad_tipo(r.get("TIPO", ""), r.get("ORIGEN_BASE", "")), axis=1)

    df_procesable["CUPOS"] = pd.to_numeric(df_procesable["CUPOS"], errors='coerce').fillna(0).astype(int)
    df_procesable["CUPOS_TOTALES_CONJUNTO"] = df_procesable["CUPOS"]

    mask_cruzadas = (df_procesable["LISTA CRUZADA"] != "")
    if mask_cruzadas.any():
        cupos_sumados = df_procesable[mask_cruzadas].groupby(["LISTA CRUZADA", "DIA", "HORARIO"])["CUPOS"].transform("sum")
        df_procesable.loc[mask_cruzadas, "CUPOS_TOTALES_CONJUNTO"] = cupos_sumados

    df_procesable = df_procesable.sort_values(by=["_p_origen", "_p_tipo", "CUPOS_TOTALES_CONJUNTO"], ascending=[True, True, False])
    cursos = df_procesable.to_dict("records")

    # 📌 PUNTO 3: CONTADORES HORIZONTALES PARA PASAR DE O(n²) A O(1) EN CÁLCULO DE USO
    ocupacion = ocupacion_previa.copy() if ocupacion_previa is not None else {}
    ocupacion_salas_counter = {}
    ocupacion_edificios_counter = {}

    # Inicializar contadores indexados rápidos basados en la ocupación previa heredada
    for (sala_id, _, _), info in ocupacion.items():
        ocupacion_salas_counter[sala_id] = ocupacion_salas_counter.get(sala_id, 0) + 1
        edif = sala_id.split("_")[0]
        ocupacion_edificios_counter[edif] = ocupacion_edificios_counter.get(edif, 0) + 1

    malla = []
    asignados_esta_corrida = 0
    lideres_cruzados_asignados = {}

    for c in list(cursos):
        mejor_s = None
        mejor_score = 1e9
        
        cupos_curso = int(c.get("CUPOS_TOTALES_CONJUNTO", c.get("CUPOS", 0)))
        dia_curso = c.get("DIA")
        hora_curso = c.get("HORARIO")
        lc_actual = c.get("LISTA CRUZADA")
        nrc_actual = str(c.get("NRC", c.get("N°", "N/A")))

        id_bloque = f"{nrc_actual}_{dia_curso}_{hora_curso}".replace(" ", "")
        c["ID_ASIGNACION_UNICO"] = id_bloque

        if dia_curso == "SIN DIA" or hora_curso == "SIN HORARIO":
            malla.append({**c, "SALA": "SIN SALA", "EDIFICIO": "N/A", "TIPO DE SALA": "N/A", "ESTADO": "SIN SALA", "MOTIVO_RECHAZO": "Falta definición horaria"})
            continue

        clave_ancla = (lc_actual, dia_curso, hora_curso)
        if lc_actual != "" and clave_ancla in lideres_cruzados_asignados:
            mejor_s = lideres_cruzados_asignados[clave_ancla]
        else:
            # 📌 PUNTO 1: SISTEMA ESTRATÉGICO MULTI-FASE CON FILTRADO GEOGRÁFICO REAL
            pref_edificios = edificio_preferido(c["CARRERA"])
            
            # Construcción de conjuntos de salas según el espectro del Relax configurado
            if relax_level == 100:
                salas_fase_1 = [s for s in lista_salas if s["EDIFICIO"] in pref_edificios]
                salas_fase_2 = []
            elif relax_level >= 90:
                salas_fase_1 = [s for s in lista_salas if s["EDIFICIO"] in pref_edificios]
                # Secundarias: El resto del campus
                salas_fase_2 = [s for s in lista_salas if s["EDIFICIO"] not in pref_edificios]
            else:
                # Si el relax es crítico (<90), todas compiten en igualdad de condiciones en Fase 1
                salas_fase_1 = lista_salas
                salas_fase_2 = []

            # --- EJECUCIÓN FASE 1: Edificios Ideales ---
            for s in salas_fase_1:
                if s["CAPACIDAD"] < cupos_curso: continue
                if not sala_valida(c, s): continue
                if colision(dia_curso, hora_curso, s["SALA_ID"], ocupacion, lc_actual): continue

                # Consultas Hash Map O(1)
                occ_s = ocupacion_salas_counter.get(s["SALA_ID"], 0)
                occ_e = ocupacion_edificios_counter.get(s["EDIFICIO"], 0)
                
                sc = score_sala(c, s, occ_s, occ_e, cupos_curso)
                if sc < mejor_score:
                    mejor_score = sc
                    mejor_s = s

            # --- EJECUCIÓN FASE 2: Activa solo si Fase 1 fracasó y el relax lo permite ---
            if mejor_s is None and salas_fase_2:
                for s in salas_fase_2:
                    if s["CAPACIDAD"] < cupos_curso: continue
                    if not sala_valida(c, s): continue
                    if colision(dia_curso, hora_curso, s["SALA_ID"], ocupacion, lc_actual): continue

                    occ_s = ocupacion_salas_counter.get(s["SALA_ID"], 0)
                    occ_e = ocupacion_edificios_counter.get(s["EDIFICIO"], 0)
                    
                    sc = score_sala(c, s, occ_s, occ_e, cupos_curso)
                    if sc < mejor_score:
                        mejor_score = sc
                        mejor_s = s

        if mejor_s:
            # 📌 PUNTO 4: AUDITORÍA ENRIQUECIDA EN LA COORDENA DE OCUPACIÓN
            ocupacion[(mejor_s["SALA_ID"], dia_curso, hora_curso)] = {
                "IDENTIFICADOR": nrc_actual,
                "LISTA_CRUZADA": lc_actual,
                "CORRIDA": id_corrida,
                "MATERIA": c["CARRERA"],
                "ORIGEN": c.get("ORIGEN_BASE", "PREGRADO"),
                "TIPO": c.get("TIPO", "CLAS"),
                "CUPOS": cupos_curso
            }
            
            # Actualización O(1) de los contadores rápidos
            ocupacion_salas_counter[mejor_s["SALA_ID"]] = ocupacion_salas_counter.get(mejor_s["SALA_ID"], 0) + 1
            ocupacion_edificios_counter[mejor_s["EDIFICIO"]] = ocupacion_edificios_counter.get(mejor_s["EDIFICIO"], 0) + 1

            if lc_actual != "":
                lideres_cruzados_asignados[clave_ancla] = mejor_s

            asignados_esta_corrida += 1
            malla.append({**c, "SALA": mejor_s["SALA"], "EDIFICIO": mejor_s["EDIFICIO"], "TIPO DE SALA": mejor_s.get("TIPO DE SALA", "N/A"), "ESTADO": "ASIGNADO", "MOTIVO_RECHAZO": "N/A"})
        else:
            malla.append({**c, "SALA": "SIN SALA", "EDIFICIO": "N/A", "TIPO DE SALA": "N/A", "ESTADO": "SIN SALA", "MOTIVO_RECHAZO": "Capacidad insuficiente o colisión insalvable"})

    df_res = pd.DataFrame(malla)

    # Re-generación de Metricas e Informes de Infraestructura
    metricas_infra = []
    for s in lista_salas:
        occ = ocupacion_salas_counter.get(s["SALA_ID"], 0)
        metricas_infra.append({
            "SALA": s["SALA"], "EDIFICIO": s["EDIFICIO"], "CAPACIDAD": s["CAPACIDAD"], 
            "BLOQUES_OCUPADOS": occ, "HORAS_OCUPADAS": occ, "HORAS_LIBRES": max(0, 50 - occ)
        })
    df_metricas_salas = pd.DataFrame(metricas_infra)

    df_sin_sala = df_res[df_res["ESTADO"] == "SIN SALA"]
    df_rech = df_sin_sala.groupby("CARRERA").size().reset_index(name="sin_sala") if not df_sin_sala.empty else pd.DataFrame(columns=["CARRERA", "sin_sala"])

    resumen = {
        "total_cursos": len(cursos),
        "total_asignadas": asignados_esta_corrida,
        "porcentaje_asignacion": round((asignados_esta_corrida / len(cursos) * 100), 2) if len(cursos) > 0 else 0,
        "sin_sala": len(cursos) - asignados_esta_corrida
    }

    # 📌 PUNTO 5: ENCAPSULACIÓN TOTAL DE RETORNO EN OBJETO ESCENARIO
    return {
        "malla": df_res,
        "ocupacion": ocupacion,
        "resumen": resumen,
        "metricas": df_metricas_salas,
        "rechazos": df_rech
    }
