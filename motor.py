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

# LISTA MAESTRA DE TIPOS PERMITIDOS (Filtro Estricto)
TIPOS_PERMITIDOS = ["HIBR", "CLAS", "EXAM", "PRBA", "AYUD"]

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
        return ["ING"]
    if any(x in materia for x in ADMIN):
        return ["CIEN", "REL", "BIB"]

    return ["HUM", "CEN", "REL", "CIEN", "BIB"]

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

def colision(dia, horario, sala_id, ocupacion, lista_cruzada_actual=""):
    # Si la coordenada espacio-tiempo ya tiene un registro...
    if (sala_id, dia, horario) in ocupacion:
        info_ocupante = ocupacion[(sala_id, dia, horario)]
        # Si ambas asignaturas comparten la misma lista cruzada válida, NO es colisión (cohabitan)
        if (lista_cruzada_actual != "" and 
            isinstance(info_ocupante, dict) and 
            info_ocupante.get("LISTA_CRUZADA") == lista_cruzada_actual):
            return False
        return True
    return False

# =========================================================
# CAPA 2: SCORING (SOFT CONSTRAINTS + RELAJACIÓN)
# =========================================================
def score_sala(curso, sala, ocup_sala, ocup_edif, relax):
    tipo = str(curso.get("TIPO", ""))
    materia = str(curso.get("MATERIA", ""))
    origen = curso.get("ORIGEN_BASE")
    
    tipo_sala_infra = str(sala.get("TIPO DE SALA", "")).upper()

    score = 0

    # --- Lógica Postgrado ---
    if origen == "POSTGRADO":
        if "HIBR" in tipo:
            score += 0 if tipo_sala_infra in ["HYFLEX", "AUDITORIO", "AULA MAGNA"] else 10
        elif "CLAS" in tipo:
            score += 0 if (tipo_sala_infra in ["STREAMING", "NORMAL"] and sala["EDIFICIO"] == "REL") else 8
        elif "EXAM" in tipo or "PRBA" in tipo:
            score += 0 if tipo_sala_infra in ["PLANA", "STREAMING"] else 8
        elif "AYUD" in tipo:
            score += 2 if tipo_sala_infra == "NORMAL" else 5

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
# CAPA 3: ENGINE PRINCIPAL DE ASIGNACIÓN (REESTRUCTURADO)
# =========================================================
def ejecutar_asignacion_escenario(df_cursos, lista_salas, relax_level=90, ocupacion_previa=None):
    # Salvaguarda si el set de datos entrante viene vacío desde el app.py
    if df_cursos.empty:
        return pd.DataFrame(), {}

    df_origen = df_cursos.copy()
    
    # 📌 FILTRO ESTRICTO TEMPRANO: Excluir todo lo que no pertenezca a los tipos autorizados
    if "TIPO" in df_origen.columns:
        df_origen["TIPO"] = df_origen["TIPO"].fillna("DESCONOCIDO").astype(str)
        
        mascara_permitidos = df_origen["TIPO"].str.upper().apply(
            lambda x: any(t in x for t in TIPOS_PERMITIDOS)
        )
        df_origen = df_origen[mascara_permitidos].reset_index(drop=True)
    
    if "MATERIA" in df_origen.columns:
        df_origen["CARRERA"] = df_origen["MATERIA"]
    else:
        df_origen["CARRERA"] = "DESCONOCIDA"

    # -----------------------------------------------------------------
    # APALANAMIENTO HORARIO: Transformación matricial a registros lineales
    # -----------------------------------------------------------------
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
        return pd.DataFrame(), {}

    # Sanitizar explícitamente la columna de listas cruzadas sin borrar datos anteriores
    if "LISTA CRUZADA" in df_procesable.columns:
        df_procesable["LISTA CRUZADA"] = df_procesable["LISTA CRUZADA"].fillna("").astype(str).str.strip()
    else:
        df_procesable["LISTA CRUZADA"] = ""

    df_procesable["_p_origen"] = np.where(df_procesable["ORIGEN_BASE"] == "POSTGRADO", 1, 2)
    df_procesable["_p_tipo"] = df_procesable.apply(
        lambda r: prioridad_tipo(r.get("TIPO", ""), r.get("ORIGEN_BASE", "")), axis=1
    )

    # -----------------------------------------------------------------
    # 🧬 CÁLCULO SUMATORIO DE CUPOS COMPARTIDOS (LISTAS CRUZADAS)
    # -----------------------------------------------------------------
    df_procesable["CUPOS"] = pd.to_numeric(df_procesable["CUPOS"], errors='coerce').fillna(0).astype(int)
    df_procesable["CUPOS_TOTALES_CONJUNTO"] = df_procesable["CUPOS"]

    mask_cruzadas = (df_procesable["LISTA CRUZADA"] != "")
    if mask_cruzadas.any():
        cupos_sumados = df_procesable[mask_cruzadas].groupby(["LISTA CRUZADA", "DIA", "HORARIO"])["CUPOS"].transform("sum")
        df_procesable.loc[mask_cruzadas, "CUPOS_TOTALES_CONJUNTO"] = cupos_sumados

    # Orden jerárquico usando la métrica del conjunto agrupado
    df_procesable = df_procesable.sort_values(
        by=["_p_origen", "_p_tipo", "CUPOS_TOTALES_CONJUNTO"], ascending=[True, True, False]
    )

    cursos = df_procesable.to_dict("records")

    for s in lista_salas:
        s["SALA_ID"] = f"{s['EDIFICIO']}_{s['SALA']}".replace(" ", "_")

    # 📌 HERENCIA MÁSTER: El motor adopta el estado exacto de las corridas previas congeladas
    ocupacion = ocupacion_previa.copy() if ocupacion_previa is not None else {}
    malla = []
    
    # Registro de anclaje para asegurar que las colisiones autorizadas queden en la misma sala física
    lideres_cruzados_asignados = {}

    for c in list(cursos):
        mejor_s = None
        mejor_score = 1e9
        
        # Evaluamos basándonos en los alumnos agrupados si es lista cruzada, si no, usa sus cupos normales
        cupos_curso = int(c.get("CUPOS_TOTALES_CONJUNTO", c.get("CUPOS", 0)))
        dia_curso = c.get("DIA")
        hora_curso = c.get("HORARIO")
        lc_actual = c.get("LISTA CRUZADA")

        if dia_curso == "SIN DIA" or hora_curso == "SIN HORARIO":
            malla.append({
                **c, "SALA": "SIN SALA", "EDIFICIO": "N/A", "TIPO DE SALA": "N/A",
                "ESTADO": "SIN SALA", "MOTIVO_RECHAZO": "Falta definición horaria en archivo origen"
            })
            continue

        # Regla Ancla: ¿El líder o hermano de esta lista cruzada ya reservó una sala en este bloque?
        clave_ancla = (lc_actual, dia_curso, hora_curso)
        if lc_actual != "" and clave_ancla in lideres_cruzados_asignados:
            mejor_s = lideres_cruzados_asignados[clave_ancla]
        else:
            # Búsqueda normal e iterativa evaluando la capacidad total requerida
            for s in lista_salas:
                if s["CAPACIDAD"] < cupos_curso:
                    continue
                if not sala_valida(c, s):
                    continue
                if colision(dia_curso, hora_curso, s["SALA_ID"], ocupacion, lc_actual):
                    continue

                occ_sala = sum(1 for k in ocupacion if k[0] == s["SALA_ID"])
                occ_edif = sum(1 for k in ocupacion if k[0].startswith(s["EDIFICIO"]))

                sc = score_sala(c, s, occ_sala, occ_edif, relax_level)

                if sc < mejor_score:
                    mejor_score = sc
                    mejor_s = s

        if mejor_s:
            identificador_curso = c.get("NRC", c.get("N°", "N/A"))
            
            # Guardamos la estructura en la ocupación global, indexando la lista cruzada para autorizar cohabitaciones
            ocupacion[(mejor_s["SALA_ID"], dia_curso, hora_curso)] = {
                "IDENTIFICADOR": identificador_curso,
                "LISTA_CRUZADA": lc_actual
            }
            
            if lc_actual != "":
                lideres_cruzados_asignados[clave_ancla] = mejor_s

            malla.append({
                **c, 
                "SALA": mejor_s["SALA"], 
                "EDIFICIO": mejor_s["EDIFICIO"],
                "TIPO DE SALA": mejor_s.get("TIPO DE SALA", "N/A"), 
                "ESTADO": "ASIGNADO", 
                "MOTIVO_RECHAZO": "N/A"
            })
        else:
            malla.append({
                **c, 
                "SALA": "SIN SALA", 
                "EDIFICIO": "N/A", 
                "TIPO DE SALA": "N/A",
                "ESTADO": "SIN SALA", 
                "MOTIVO_RECHAZO": f"Capacidad insuficiente para conjunto sumado ({cupos_curso} alumnos) o colisión insalvable"
            })

    return pd.DataFrame(malla), ocupacion
