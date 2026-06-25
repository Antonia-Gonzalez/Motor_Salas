import pandas as pd
import numpy as np

def parse_time_to_minutes(time_str):
    """Convierte un string de hora (ej: '08:30') a minutos desde la medianoche."""
    try:
        time_str = str(time_str).strip()
        if "-" in time_str:
            time_str = time_str.split("-")[0].strip()
        parts = time_str.split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except:
        return 0

def parse_horario_range(horario_str):
    """Convierte un rango horario (ej: '08:30-10:00') en tupla de minutos."""
    try:
        horario_str = str(horario_str).strip()
        if "-" in horario_str:
            parts = horario_str.split("-")
            return parse_time_to_minutes(parts[0]), parse_time_to_minutes(parts[1])
        return 0, 0
    except:
        return 0, 0

def verificar_colision(start_min, end_min, start_date, end_date, asignaciones_sala_dia):
    """Verifica si existe solapamiento temporal y de fechas real."""
    for a_start_min, a_end_min, a_start_date, a_end_date, _ in asignaciones_sala_dia:
        if max(start_date, a_start_date) <= min(end_date, a_end_date):
            if max(start_min, a_start_min) < min(end_min, a_end_min):
                return True
    return False

def calcular_score_sala(sala_dict, origen_base, tipo_reunion, materia, cupos):
    """
    Calcula la idoneidad exacta de la sala bajo las reglas institucionales.
    Retorna (score_preferencia, score_edificio, desperdicio_capacidad) -> Menor es mejor.
    """
    tipo_sala = str(sala_dict["TIPO_SALA"]).strip().upper()
    edificio = str(sala_dict["EDIFICIO"]).strip().upper()
    capacity = sala_dict["CAPACIDAD"]
    
    score_preferencia = 99
    score_edificio = 99
    
    if capacity < cupos:
        return (999, 999, 999) # Descalificada por aforo insuficiente
        
    # Diccionarios de asignación estricta por carrera
    INGENIERIAS = ["ICA", "ICC", "ICE", "ICI", "ING", "INM", "IOC"]
    ADMINISTRACION = ["ADM", "DEM", "DER", "EAD", "EAI", "EAM", "ECN", "MAD"]
    
    # --- LÓGICA DE POSTGRADO ---
    if origen_base == "POSTGRADO":
        if "HIBR" in tipo_reunion:
            prefs = ["HYFLEX", "AUDITORIO", "AULA MAGNA", "STREAMING", "SALA NORMAL", "SALA TRADICIONAL"]
            if tipo_sala in prefs: score_preferencia = prefs.index(tipo_sala)
        elif "CLAS" in tipo_reunion:
            if tipo_sala == "STREAMING":
                score_preferencia = 0
            elif tipo_sala in ["SALA NORMAL", "SALA TRADICIONAL"] and edificio == "REL":
                score_preferencia = 1
            elif tipo_sala in ["SALA NORMAL", "SALA TRADICIONAL"]:
                score_preferencia = 2
            elif tipo_sala == "AUDITORIO":
                score_preferencia = 3
            elif tipo_sala == "HYFLEX":
                score_preferencia = 4
        elif "EXAM" in tipo_reunion or "PBRA" in tipo_reunion:
            prefs = ["SALA PLANA", "STREAMING", "SALA NORMAL", "SALA TRADICIONAL"]
            if tipo_sala in prefs: score_preferencia = prefs.index(tipo_sala)
        elif "AYUD" in tipo_reunion:
            if tipo_sala in ["SALA NORMAL", "SALA TRADICIONAL"]: score_preferencia = 0
            
    # --- LÓGICA DE PREGRADO ---
    else:  
        if "CLAS" in tipo_reunion:
            if tipo_sala == "STREAMING":
                score_preferencia = 0
            elif tipo_sala in ["SALA NORMAL", "SALA TRADICIONAL"]:
                score_preferencia = 1
            
            if any(cod in materia for cod in INGENIERIAS):
                edificios_pref = ["ING", "CIEN"]
            elif any(cod in materia for cod in ADMINISTRACION):
                edificios_pref = ["REL", "BIB"]
            else:
                edificios_pref = ["HUM", "CIEN"]
                
            if edificio in edificios_pref:
                score_edificio = edificios_pref.index(edificio)
                
        elif "EXAM" in tipo_reunion or "PBRA" in tipo_reunion:
            prefs = ["SALA PLANA", "STREAMING", "SALA NORMAL", "SALA TRADICIONAL"]
            if tipo_sala in prefs: score_preferencia = prefs.index(tipo_sala)
        elif "AYUD" in tipo_reunion:
            if tipo_sala in ["SALA NORMAL", "SALA TRADICIONAL"]: score_preferencia = 0
            
    desperdicio_capacidad = capacity - cupos
    return (score_preferencia, score_edificio, desperdicio_capacidad)


def ejecutar_asignacion_escenario(
    archivo_cursos_excel, escenario_id, eficiencia_minima, 
    modo_estricto, modo_lista_cruzada, ocupacion_previa, 
    lista_carreras, lista_edificios=None, lista_salas=None
):
    # 1. CARGA DE INFRAESTRUCTURA CONSTANTE
    try:
        df_infra = pd.read_excel("infraestructura_constante.xlsx", sheet_name="SALAS")
    except:
        df_infra = pd.DataFrame(columns=["SALA", "EDIFICIO", "CAPACIDAD", "TIPO_SALA"])
    
    # --- NUEVA SECCIÓN DE CONTROL: Normalizar nombres de columnas físicas de Infraestructura ---
    df_infra.columns = [str(c).strip().upper() for c in df_infra.columns]
    if "TIPO DE SALA" in df_infra.columns:
        df_infra = df_infra.rename(columns={"TIPO DE SALA": "TIPO_SALA"})
    if "TIPO DE RESTRICCIÓN" in df_infra.columns:
        df_infra = df_infra.rename(columns={"TIPO DE RESTRICCIÓN": "TIPO_RESTRICCION"})
    # ------------------------------------------------------------------------------------------

    df_infra["EDIFICIO"] = df_infra["EDIFICIO"].fillna("").astype(str).str.strip().str.upper()
    df_infra["SALA"] = df_infra["SALA"].fillna("").astype(str).str.strip().str.upper()
    df_infra["CAPACIDAD"] = df_infra["CAPACIDAD"].fillna(0).astype(int)
    df_infra["TIPO_SALA"] = df_infra["TIPO_SALA"].fillna("SALA TRADICIONAL").astype(str).str.strip().str.upper()
    
    duplicadas = df_infra[df_infra.duplicated(subset=["SALA"], keep=False)]["SALA"].unique()
    if len(duplicadas) > 0:
        df_infra["SALA"] = df_infra.apply(
            lambda r: f"{r['SALA']} {int(r['CAPACIDAD'])}" if r["SALA"] in duplicadas else r["SALA"], axis=1
        )

    if lista_edificios:
        df_infra = df_infra[df_infra["EDIFICIO"].isin([str(e).strip().upper() for e in lista_edificios])]
    if lista_salas:
        df_infra = df_infra[df_infra["SALA"].isin([str(s).strip().upper() for s in lista_salas])]
        
    salas_universo = df_infra.to_dict("records")

    # 2. CARGA Y FILTRADO DE CURSOS DEMANDANTES
    hojas_cargar = []
    xl = pd.ExcelFile(archivo_cursos_excel)
    for hoja in ["BASE POSTGRADO", "BASE PREGRADO"]:
        if hoja in xl.sheet_names:
            df_h = xl.parse(hoja)
            df_h["ORIGEN_BASE"] = "POSTGRADO" if "POSTGRADO" in hoja.upper() else "PREGRADO"
            hojas_cargar.append(df_h)
            
    if not hojas_cargar:
        return pd.DataFrame(), {}, pd.DataFrame(), {}, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
        
    df_cursos = pd.concat(hojas_cargar, ignore_index=True)
    
    # Estandarizar también las columnas de los cursos
    df_cursos.columns = [str(c).strip().upper() for c in df_cursos.columns]
    
    df_cursos["MATERIA"] = df_cursos["MATERIA"].fillna("").astype(str).str.strip().str.upper()
    
    lista_carreras_caps = [str(c).strip().upper() for c in lista_carreras]
    df_cursos = df_cursos[df_cursos["MATERIA"].isin(lista_carreras_caps)]
    
    if df_cursos.empty:
        return pd.DataFrame(), {}, pd.DataFrame(), {}, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    col_ini = next((c for c in df_cursos.columns if "FECHA" in str(c).upper() and ("INI" in str(c).upper() or "COM" in str(c).upper())), None)
    col_fin = next((c for c in df_cursos.columns if "FECHA" in str(c).upper() and ("TER" in str(c).upper() or "FIN" in str(c).upper())), None)
    
    # --- NUEVA SECCIÓN DE CONTROL: Forzar fechas a Series para evitar fallos de AttributeError con .dt ---
    if col_ini and col_ini in df_cursos.columns:
        fechas_ini_raw = df_cursos[col_ini]
    else:
        fechas_ini_raw = pd.Series("2026-03-01", index=df_cursos.index)

    if col_fin and col_fin in df_cursos.columns:
        fechas_fin_raw = df_cursos[col_fin]
    else:
        fechas_fin_raw = pd.Series("2026-12-31", index=df_cursos.index)

    df_cursos["FECHA_INI_CONV"] = pd.to_datetime(fechas_ini_raw, errors='coerce').dt.date.fillna(pd.to_datetime("2026-03-01").date())
    df_cursos["FECHA_FIN_CONV"] = pd.to_datetime(fechas_fin_raw, errors='coerce').dt.date.fillna(pd.to_datetime("2026-12-31").date())
    # -----------------------------------------------------------------------------------------------------
    
    df_cursos["CUPOS"] = df_cursos["CUPOS"].fillna(0).astype(int)
    df_cursos["DIA"] = df_cursos["DIA"].fillna("S/D").astype(str).str.strip().str.upper()
    df_cursos["HORARIO"] = df_cursos["HORARIO"].fillna("S/H").astype(str).str.strip().str.upper()
    df_cursos["TIPO_REUNION"] = df_cursos["TIPO_REUNION"].fillna("CLAS").astype(str).str.strip().str.upper()

    # 3. MANEJO DE LISTAS CRUZADAS
    col_cruzada = next((c for c in df_cursos.columns if "CRUZ" in str(c).upper() or "COMPART" in str(c).upper()), None)
    dict_cupos_cruzados = {}
    if col_cruzada and modo_lista_cruzada:
        df_cursos[col_cruzada] = df_cursos[col_cruzada].fillna("").astype(str).str.strip()
        df_valid_cruz = df_cursos[df_cursos[col_cruzada] != ""]
        for name, group in df_valid_cruz.groupby([col_cruzada, "DIA", "HORARIO"]):
            if modo_lista_cruzada == "SUMAR":
                val = group["CUPOS"].sum()
            elif modo_lista_cruzada == "MAXIMO":
                val = group["CUPOS"].max()
            elif modo_lista_cruzada == "PROMEDIO":
                val = int(group["CUPOS"].mean())
            else:
                val = group["CUPOS"].max()
            dict_cupos_cruzados[name] = val

    # Cola de prioridades
    def calc_prioridad_programa(row):
        if row["ORIGEN_BASE"] == "POSTGRADO": return 1
        mat = str(row["MATERIA"]).strip().upper()
        
        INGENIERIAS = ["ICA", "ICC", "ICE", "ICI", "ING", "INM", "IOC"]
        ADMINISTRACION = ["ADM", "DEM", "DER", "EAD", "EAI", "EAM", "ECN", "MAD"]
        
        if any(cod in mat for cod in INGENIERIAS): return 2
        if any(cod in mat for cod in ADMINISTRACION): return 3
        return 4

    def calc_prioridad_clase(tipo_r):
        if "HIBR" in tipo_r: return 1
        if "CLAS" in tipo_r: return 2
        if "EXAM" in tipo_r or "PBRA" in tipo_r: return 3
        if "AYUD" in tipo_r: return 4
        return 5

    df_cursos["PRIORIDAD_PROG"] = df_cursos.apply(calc_prioridad_programa, axis=1)
    df_cursos["PRIORIDAD_CLAS"] = df_cursos["TIPO_REUNION"].apply(calc_prioridad_clase)
    df_cursos = df_cursos.sort_values(by=["PRIORIDAD_PROG", "PRIORIDAD_CLAS", "CUPOS"], ascending=[True, True, False])
    
    lista_cursos = df_cursos.to_dict("records")

    # 4. MATRIZ DE OCUPACIÓN
    matriz_ocupacion = {} 
    if ocupacion_previa and isinstance(ocupacion_previa, dict):
        for k, v in ocupacion_previa.items():
            if isinstance(k, tuple) and len(k) == 2:
                matriz_ocupacion[k] = list(v)

    resultados_asignacion = []
    conteo_asignados, conteo_rechazados = 0, 0
    salas_asignadas_cruzadas = {}

    # 5. BUCLE CENTRAL ASIGNADOR (CON EXCLUSIÓN ESTRICTA)
    for curso in lista_cursos:
        cupos_originales = curso["CUPOS"]
        dia = curso["DIA"]
        horario = curso["HORARIO"]
        materia = curso["MATERIA"]
        tipo_r = curso["TIPO_REUNION"]
        seccion = curso.get("SECCION", "UNICA")
        orig_base = curso["ORIGEN_BASE"]
        
        start_min, end_min = parse_horario_range(horario)
        start_date = curso["FECHA_INI_CONV"]
        end_date = curso["FECHA_FIN_CONV"]
        
        cruz_key = (curso[col_cruzada], dia, horario) if col_cruzada and curso[col_cruzada] != "" else None
        cupos_efectivos = dict_cupos_cruzados.get(cruz_key, cupos_originales) if cruz_key else cupos_originales
        
        # --- FILTRO DE EXCLUSIÓN DE TIPOS ---
        TIPOS_REQUERIDOS = ["HIBR", "CLAS", "EXAM", "PBRA", "AYUD"]
        if not any(keyword in tipo_r for keyword in TIPOS_REQUERIDOS):
            resultados_asignacion.append({
                "CARRERA": materia, "NOMBRE SECCIÓN": f"{materia} SECC {seccion}",
                "CUPOS_CONSOLIDADOS": cupos_efectivos, "DIA": dia, "HORARIO": horario,
                "SALA": "SIN SALA", "EDIFICIO": "NINGUNO",
                "ESTADO": "NO REQUIERE", "MOTIVO_RECHAZO": f"Excluido: Tipo '{tipo_r}' no utiliza sala física", "TIPO_REUNION": tipo_r,
                "EFICIENCIA_ESPACIAL": 0.0
            })
            continue 
            
        sala_asignada = None
        motivo_rechazo = "No hay salas del tipo requerido o aforo disponible en este bloque"
        
        if cruz_key and cruz_key in salas_asignadas_cruzadas:
            sala_asignada = salas_asignadas_cruzadas[cruz_key]
        else:
            if modo_estricto:
                umbrales_eficiencia = [eficiencia_minima]
            else:
                base_relax = [0.75, 0.50, 0.30, 0.10, 0.00]
                umbrales_eficiencia = [eficiencia_minima] + [u for u in base_relax if u < eficiencia_minima]
                umbrales_eficiencia = list(dict.fromkeys(umbrales_eficiencia))
                
            salas_candidatas = sorted(salas_universo, key=lambda s: calcular_score_sala(s, orig_base, tipo_r, materia, cupos_efectivos))
            
            flag_encontrado = False
            for umbral in umbrales_eficiencia:
                for sala in salas_candidatas:
                    if sala["CAPACIDAD"] < cupos_efectivos:
                        continue
                        
                    eficiencia_calc = cupos_efectivos / sala["CAPACIDAD"] if sala["CAPACIDAD"] > 0 else 0
                    if eficiencia_calc < umbral:
                        continue
                        
                    asigs_actuales = matriz_ocupacion.get((sala["SALA"], dia), [])
                    if verificar_colision(start_min, end_min, start_date, end_date, asigs_actuales):
                        motivo_rechazo = "Conflicto de horario parcial o cruce de semanas calendario"
                        continue
                        
                    sala_asignada = sala
                    flag_encontrado = True
                    if cruz_key:
                        salas_asignadas_cruzadas[cruz_key] = sala
                    break
                if flag_encontrado:
                    break

        if sala_asignada:
            llave_matriz = (sala_asignada["SALA"], dia)
            if llave_matriz not in matriz_ocupacion:
                matriz_ocupacion[llave_matriz] = []
            matriz_ocupacion[llave_matriz].append((start_min, end_min, start_date, end_date, f"{materia}-{seccion}"))
            
            conteo_asignados += 1
            resultados_asignacion.append({
                "CARRERA": materia, "NOMBRE SECCIÓN": f"{materia} SECC {seccion}",
                "CUPOS_CONSOLIDADOS": cupos_efectivos, "DIA": dia, "HORARIO": horario,
                "SALA": sala_asignada["SALA"], "EDIFICIO": sala_asignada["EDIFICIO"],
                "ESTADO": "ASIGNADO", "MOTIVO_RECHAZO": "N/A", "TIPO_REUNION": tipo_r,
                "EFICIENCIA_ESPACIAL": cupos_efectivos / sala_asignada["CAPACIDAD"] if sala_asignada["CAPACIDAD"] > 0 else 0
            })
        else:
            conteo_rechazados += 1
            resultados_asignacion.append({
                "CARRERA": materia, "NOMBRE SECCIÓN": f"{materia} SECC {seccion}",
                "CUPOS_CONSOLIDADOS": cupos_efectivos, "DIA": dia, "HORARIO": horario,
                "SALA": "SIN SALA", "EDIFICIO": "NINGUNO",
                "ESTADO": "SIN SALA", "MOTIVO_RECHAZO": motivo_rechazo, "TIPO_REUNION": tipo_r,
                "EFICIENCIA_ESPACIAL": 0.0
            })

    # 6. RETORNO Y MÉTRICAS COMPATIBLES
    df_res = pd.DataFrame(resultados_asignacion)
    df_malla = df_res[df_res["ESTADO"] == "ASIGNADO"].copy()
    
    bloques_totales = [("08:30", "10:00"), ("10:15", "11:45"), ("12:00", "13:30"), ("14:30", "16:00"), ("16:15", "17:45")]
    dias_totales = ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES"]
    capacidad_bloques_semana = len(bloques_totales) * len(dias_totales)

    metricas_salas = []
    for sala in salas_universo:
        df_sala_asig = df_malla[df_malla["SALA"] == sala["SALA"]] if not df_malla.empty else pd.DataFrame()
        h_ocupadas = len(df_sala_asig)
        h_libres = max(0, capacidad_bloques_semana - h_ocupadas)
        ef_promedio = df_sala_asig["EFICIENCIA_ESPACIAL"].mean() if h_ocupadas > 0 else 0.0
        
        metricas_salas.append({
            "SALA": sala["SALA"], "EDIFICIO": sala["EDIFICIO"], "CAPACIDAD": sala["CAPACIDAD"],
            "HORAS_OCUPADAS": h_ocupadas, "HORAS_LIBRES": h_libres, "EFICIENCIA_PROMEDIO": ef_promedio
        })
    df_s = pd.DataFrame(metricas_salas)

    if not df_malla.empty:
        df_malla["HORA_INICIO"] = df_malla["HORARIO"].apply(lambda x: x.split("-")[0].strip() if "-" in x else "08:00")
        df_malla["CURSO_OCUPANTE"] = df_malla["NOMBRE SECCIÓN"]
        df_e = df_s.groupby("EDIFICIO")["HORAS_OCUPADAS"].sum().reset_index()
        df_e["% UTILIZACIÓN SEMANAL HORARIA"] = (df_e["HORAS_OCUPADAS"] / (df_s.groupby("EDIFICIO")["SALA"].count().values * capacidad_bloques_semana)) * 100
        df_car = df_malla.groupby("CARRERA").size().reset_index(name="HORAS_OCUPADAS")
        df_tip = df_malla.groupby("TIPO_REUNION").size().reset_index(name="HORAS_CONSUMIDAS")
    else:
        df_malla = pd.DataFrame(columns=["SALA", "HORA_INICIO", "DIA", "CURSO_OCUPANTE", "HORARIO"])
        df_e = pd.DataFrame(columns=["EDIFICIO", "HORAS_OCUPADAS", "% UTILIZACIÓN SEMANAL HORARIA"])
        df_car = pd.DataFrame(columns=["CARRERA", "HORAS_OCUPADAS"])
        df_tip = pd.DataFrame(columns=["TIPO_REUNION", "HORAS_CONSUMIDAS"])

    # Filtrado estricto de demandantes reales para no diluir los KPIs
    df_demandantes = df_res[df_res["ESTADO"].isin(["ASIGNADO", "SIN SALA"])]
    total_cursos_demandantes = len(df_demandantes)
    
    resumen_metadata = {
        "escenario": escenario_id, "asignados": conteo_asignados, "rechazados": conteo_rechazados,
        "porcentaje_asignacion": round((conteo_asignados / total_cursos_demandantes) * 100, 1) if total_cursos_demandantes > 0 else 0,
        "salas_utilizadas": int(df_malla["SALA"].nunique())
    }

    if not df_demandantes.empty:
        df_dem = df_demandantes.groupby(["DIA", "HORARIO"]).size().reset_index(name="BLOQUES_ACTIVOS")
        df_dem["MOMENTO_OPERATIVO"] = df_dem["DIA"] + " " + df_dem["HORARIO"]
        df_dem["HORA_STR"] = df_dem["HORARIO"]
        
        df_rech = df_demandantes.groupby("CARRERA").agg(
            total_cursos=("ESTADO", "count"), 
            sin_sala=("ESTADO", lambda x: (x == "SIN SALA").sum())
        ).reset_index()
        df_rech["TASA_RECHAZO_PCT"] = (df_rech["sin_sala"] / df_rech["total_cursos"]) * 100
    else:
        df_dem = pd.DataFrame(columns=["MOMENTO_OPERATIVO", "BLOQUES_ACTIVOS", "DIA", "HORA_STR"])
        df_rech = pd.DataFrame(columns=["CARRERA", "TASA_RECHAZO_PCT"])

    # Inventario dinámico de ventanas temporales libres
    lista_libres = []
    fecha_base_ini = pd.to_datetime("2026-03-01").date()
    fecha_base_fin = pd.to_datetime("2026-12-31").date()
    
    for sala in salas_universo:
        for d in dias_totales:
            for b_ini, b_fin in bloques_totales:
                s_min = parse_time_to_minutes(b_ini)
                e_min = parse_time_to_minutes(b_fin)
                asigs_actuales = matriz_ocupacion.get((sala["SALA"], d), [])
                
                asigs_bloque = []
                for a_start, a_end, a_sdate, a_edate, _ in asigs_actuales:
                    if max(s_min, a_start) < min(e_min, a_end):
                        asigs_bloque.append((a_sdate, a_edate))
                
                if not asigs_bloque:
                    lista_libres.append({
                        "SALA": sala["SALA"], "EDIFICIO": sala["EDIFICIO"], "CAPACIDAD": sala["CAPACIDAD"],
                        "DIA": d, "INICIO": b_ini, "FIN": b_fin, "FECHA_DISP_INI": fecha_base_ini, "FECHA_DISP_FIN": fecha_base_fin
                    })
                else:
                    asigs_bloque.sort(key=lambda x: x[0])
                    curr_start = fecha_base_ini
                    for s_date, e_date in asigs_bloque:
                        if s_date > curr_start:
                            lista_libres.append({
                                "SALA": sala["SALA"], "EDIFICIO": sala["EDIFICIO"], "CAPACIDAD": sala["CAPACIDAD"],
                                "DIA": d, "INICIO": b_ini, "FIN": b_fin, "FECHA_DISP_INI": curr_start, "FECHA_DISP_FIN": s_date - pd.Timedelta(days=1)
                            })
                        curr_start = max(curr_start, e_date + pd.Timedelta(days=1))
                    if curr_start <= fecha_base_fin:
                        lista_libres.append({
                            "SALA": sala["SALA"], "EDIFICIO": sala["EDIFICIO"], "CAPACIDAD": sala["CAPACIDAD"],
                            "DIA": d, "INICIO": b_ini, "FIN": b_fin, "FECHA_DISP_INI": curr_start, "FECHA_DISP_FIN": fecha_base_fin
                        })
                        
    df_lib = pd.DataFrame(lista_libres) if lista_libres else pd.DataFrame(columns=["SALA", "EDIFICIO", "CAPACIDAD", "DIA", "INICIO", "FIN", "FECHA_DISP_INI", "FECHA_DISP_FIN"])

    return df_res, matriz_ocupacion, df_malla, resumen_metadata, df_s, df_e, df_car, df_tip, df_dem, df_lib, df_rech
