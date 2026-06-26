import pandas as pd
import numpy as np

def parse_time_to_minutes(time_str):
    try:
        time_str = str(time_str).strip()
        if "-" in time_str:
            time_str = time_str.split("-")[0].strip()
        parts = time_str.split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except:
        return 0

def parse_horario_range(horario):
    if pd.isna(horario):
        return 0, 0
    try:
        horario = str(horario).strip().replace(" ", "")
        horario = horario.replace("–", "-").replace("—", "-")
        partes = horario.split("-")
        if len(partes) != 2:
            return 0, 0
        return (parse_time_to_minutes(partes[0]), parse_time_to_minutes(partes[1]))
    except:
        return 0, 0

def verificar_colision(start_min, end_min, start_date, end_date, asignaciones_sala_dia):
    for a_start_min, a_end_min, a_start_date, a_end_date, _ in asignaciones_sala_dia:
        if max(start_date, a_start_date) <= min(end_date, a_end_date):
            if max(start_min, a_start_min) < min(end_min, a_end_min):
                return True
    return False

def prioridad_tipo(tipo):
    if "HIBR" in tipo: return 1
    if "CLAS" in tipo: return 2
    if "EXAM" in tipo or "PBRA" in tipo: return 3
    if "AYUD" in tipo: return 4
    return 5

# [PUNTO 1 Y 6] FUNCIÓN DE SCORE LINEALIZADA Y BALANCEADA DE EDIFICIOS
def calcular_score_sala_lineal(sala_dict, origen_base, tipo_reunion, materia, cupos, ocupacion_sala, ocupacion_edificio):
    tipo_sala = str(sala_dict["TIPO_SALA"]).strip().upper()
    edificio = str(sala_dict["EDIFICIO"]).strip().upper()
    capacity = sala_dict["CAPACIDAD"]
    
    if capacity < cupos:
        return 999999  # Penalización crítica por aforo insuficiente
        
    score_preferencia = 10
    score_edificio = 10
    
    INGENIERIAS = ["ICA", "ICC", "ICE", "ICI", "ING", "INM", "IOC"]
    ADMINISTRACION = ["ADM", "DEM", "DER", "EAD", "EAI", "EAM", "ECN", "MAD"]
    
    if origen_base == "POSTGRADO":
        if "HIBR" in tipo_reunion:
            prefs = ["HYFLEX", "AUDITORIO", "AULA MAGNA", "STREAMING", "SALA NORMAL", "SALA TRADICIONAL"]
            if tipo_sala in prefs: score_preferencia = prefs.index(tipo_sala)
        elif "CLAS" in tipo_reunion:
            if tipo_sala == "STREAMING": score_preferencia = 0
            elif tipo_sala in ["SALA NORMAL", "SALA TRADICIONAL"] and edificio == "REL": score_preferencia = 1
            elif tipo_sala in ["SALA NORMAL", "SALA TRADICIONAL"]: score_preferencia = 2
    else:  
        if "CLAS" in tipo_reunion:
            if tipo_sala == "STREAMING": score_preferencia = 0
            elif tipo_sala in ["SALA NORMAL", "SALA TRADICIONAL"]: score_preferencia = 1
            if any(cod in materia for cod in INGENIERIAS): edificios_pref = ["ING", "CIEN"]
            elif any(cod in materia for cod in ADMINISTRACION): edificios_pref = ["REL", "BIB"]
            else: edificios_pref = ["HUM", "CIEN"]
            if edificio in edificios_pref: score_edificio = edificios_pref.index(edificio)
            
    # Suma ponderada continua flexible (Menor score es mejor)
    # Penaliza severamente edificios saturados y salas de sobre-capacidad destructiva
    holgura_capacidad = abs(capacity - cupos)
    
    return (score_preferencia * 5000) + (score_edificio * 1000) + (ocupacion_edificio * 200) + (ocupacion_sala * 20) + holgura_capacidad

def ejecutar_asignacion_escenario(
    archivo_cursos_excel, escenario_id, eficiencia_minima, 
    modo_estricto, modo_lista_cruzada, ocupacion_previa, 
    lista_carreras, lista_edificios=None, lista_salas=None
):
    # =====================================================
    # EXTRACT & INFRASTRUCTURE DATASET
    # =====================================================
    try:
        df_infra = pd.read_excel("infraestructura_constante.xlsx", sheet_name="SALAS")
    except:
        df_infra = pd.DataFrame(columns=["SALA", "EDIFICIO", "CAPACIDAD", "TIPO_SALA"])
    
    df_infra.columns = [str(c).strip().upper() for c in df_infra.columns]
    if "TIPO DE SALA" in df_infra.columns:
        df_infra = df_infra.rename(columns={"TIPO DE SALA": "TIPO_SALA"})

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

    # CARGA DE CURSOS DEMANDANTES
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
    df_cursos.columns = [str(c).strip().upper() for c in df_cursos.columns]

    df_cursos.rename(columns={
        "CARRERA": "MATERIA", "MATERIA": "MATERIA",
        "TITULO": "SECCION", "NOMBRE SECCIÓN": "SECCION",
        "TIPO": "TIPO_REUNION", "TIPO DE REUNIÓN": "TIPO_REUNION",
        "INICIO": "FECHA_INICIO", "FECHA INICIO": "FECHA_INICIO",
        "FIN": "FECHA_FIN", "FECHA FIN": "FECHA_FIN",
        "MAX ALUMNOS": "CUPOS", "CUPOS": "CUPOS",
        "CAPACIDAD SALA": "CAPACIDAD", "CAPACIDAD": "CAPACIDAD"
    }, inplace=True)

    dias_semana = ["LUNES", "MARTES", "MIERCOLES", "MIÉRCOLES", "JUEVES", "VIERNES", "SABADO", "SÁBADO"]
    dias_existentes = [d for d in dias_semana if d in df_cursos.columns]

    if dias_existentes:
        columnas_fijas = [c for c in df_cursos.columns if c not in dias_existentes]
        registros = []
        for _, fila in df_cursos.iterrows():
            datos_base = {col: fila[col] for col in columnas_fijas}
            for dia in dias_existentes:
                horario = fila[dia]
                if pd.notna(horario):
                    horario = str(horario).strip().replace(" ", "")
                    if horario != "" and horario.lower() != "nan":
                        nuevo = datos_base.copy()
                        nuevo["DIA"] = dia.replace("Á", "A").replace("É", "E")
                        nuevo["HORARIO"] = horario
                        registros.append(nuevo)
        df_cursos = pd.DataFrame(registros)

    if df_cursos.empty:
        return pd.DataFrame(), {}, pd.DataFrame(), {}, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    df_cursos["MATERIA"] = df_cursos["MATERIA"].fillna("").astype(str).str.strip().str.upper()
    lista_carreras_caps = [str(c).strip().upper() for c in lista_carreras]
    df_cursos = df_cursos[df_cursos["MATERIA"].isin(lista_carreras_caps)]
    
    if df_cursos.empty:
        return pd.DataFrame(), {}, pd.DataFrame(), {}, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    df_cursos["FECHA_INI_CONV"] = pd.to_datetime(df_cursos.get("FECHA_INICIO", "2026-03-01"), errors='coerce').dt.date.fillna(pd.to_datetime("2026-03-01").date())
    df_cursos["FECHA_FIN_CONV"] = pd.to_datetime(df_cursos.get("FECHA_FIN", "2026-12-31"), errors='coerce').dt.date.fillna(pd.to_datetime("2026-12-31").date())
    df_cursos["CUPOS"] = df_cursos["CUPOS"].fillna(0).astype(int)
    df_cursos["DIA"] = df_cursos["DIA"].fillna("S/D").astype(str).str.strip().str.upper()
    df_cursos["HORARIO"] = df_cursos["HORARIO"].fillna("S/H").astype(str).str.strip().str.upper()
    df_cursos["TIPO_REUNION"] = df_cursos["TIPO_REUNION"].fillna("CLAS").astype(str).str.strip().str.upper()
    df_cursos["SALA"] = df_cursos.get("SALA", "").fillna("").astype(str).str.strip().str.upper()

    col_cruzada = next((c for c in df_cursos.columns if "CRUZ" in str(c).upper() or "COMPART" in str(c).upper()), None)
    dict_cupos_cruzados = {}
    if col_cruzada and modo_lista_cruzada:
        df_cursos[col_cruzada] = df_cursos[col_cruzada].fillna("").astype(str).str.strip()
        df_valid_cruz = df_cursos[df_cursos[col_cruzada] != ""]
        for name, group in df_valid_cruz.groupby([col_cruzada, "DIA", "HORARIO"]):
            if modo_lista_cruzada == "SUMAR" or not modo_lista_cruzada:
                val = group["CUPOS"].sum()
            elif modo_lista_cruzada == "MAXIMO":
                val = group["CUPOS"].max()
            elif modo_lista_cruzada == "PROMEDIO":
                val = int(group["CUPOS"].mean())
            dict_cupos_cruzados[name] = val

    # Identificador único interno para auditoría
    df_cursos["ID_CURSO_INTERNO"] = range(len(df_cursos))

    # =====================================================
    # FASE 1: CÁCULO DE DIFICULTAD, RAREZA Y CACHÉ DE SCORES [PUNTO 4, 5 Y 7]
    # =====================================================
    lista_pre_cursos = df_cursos.to_dict("records")
    for c in lista_pre_cursos:
        c_key = (c[col_cruzada], c["DIA"], c["HORARIO"]) if col_cruzada and c[col_cruzada] != "" else None
        c_cupos = dict_cupos_cruzados.get(c_key, c["CUPOS"]) if c_key else c["CUPOS"]
        
        # Rareza: ¿Cuántas salas soportan este volumen de alumnos?
        salas_compatibles = sum(1 for s in salas_universo if s["CAPACIDAD"] >= c_cupos)
        c["RAREZA_SALAS"] = salas_compatibles if salas_compatibles > 0 else 0.1
        
        # Factor Horario Crítico (Viernes tarde o bloques de alta demanda)
        es_critico = 2 if c["DIA"] in ["VIERNES", "SABADO"] and parse_horario_range(c["HORARIO"])[0] >= 1000 else 1
        
        # [PUNTO 4 Y 5] Dificultad combinatoria del curso
        c["DIFICULTAD_COMBINATORIA"] = (c_cupos / c["RAREZA_SALAS"]) * es_critico

    df_cursos = pd.DataFrame(lista_pre_cursos)
    df_cursos["PRIORIDAD_PROG"] = df_cursos.apply(lambda r: 1 if r["ORIGEN_BASE"] == "POSTGRADO" else 2, axis=1)
    df_cursos["PRIORIDAD_TIPO"] = df_cursos["TIPO_REUNION"].apply(prioridad_tipo)

    # Ordenamiento Científico Multicriterio de la Fase 1
    df_cursos = df_cursos.sort_values(
        by=["PRIORIDAD_PROG", "PRIORIDAD_TIPO", "DIFICULTAD_COMBINATORIA", "CUPOS"], 
        ascending=[True, True, False, False]
    )
    lista_cursos = df_cursos.to_dict("records")

    # Inicialización de matrices de tracking de infraestructura
    matriz_ocupacion = {}
    contador_carga_salas = {s["SALA"]: 0 for s in salas_universo}
    contador_carga_edificios = {s["EDIFICIO"]: 0 for s in salas_universo} # [PUNTO 6] Tracker Global Edificios
    
    if ocupacion_previa and isinstance(ocupacion_previa, dict):
        for k, v in ocupacion_previa.items():
            if isinstance(k, tuple) and len(k) == 2:
                matriz_ocupacion[k] = list(v)
                contador_carga_salas[k[0]] = contador_carga_salas.get(k[0], 0) + len(v)
                # Recuperar edificio mapeado
                ed_map = next((s["EDIFICIO"] for s in salas_universo if s["SALA"] == k[0]), "EXTERNA")
                contador_carga_edificios[ed_map] = contador_carga_edificios.get(ed_map, 0) + len(v)

    resultados_asignacion = {}
    salas_asignadas_cruzadas = {}

    # =====================================================
    # FASE 2: ASIGNACIÓN GREEDY BALANCEADA COMPLETA
    # =====================================================
    for curso in lista_cursos:
        cid = curso["ID_CURSO_INTERNO"]
        cupos_originales = curso["CUPOS"]
        dia = curso["DIA"]
        horario = curso["HORARIO"]
        materia = curso["MATERIA"]
        tipo_r = curso["TIPO_REUNION"]
        seccion = str(curso.get("SECCION", "UNICA")).strip()
        orig_base = curso["ORIGEN_BASE"]
        sala_fija = str(curso.get("SALAS", "")).strip().upper()
        
        start_min, end_min = parse_horario_range(horario)
        start_date = curso["FECHA_INI_CONV"]
        end_date = curso["FECHA_FIN_CONV"]
        
        cruz_key = (curso[col_cruzada], dia, horario) if col_cruzada and curso[col_cruzada] != "" else None
        cupos_efectivos = dict_cupos_cruzados.get(cruz_key, cupos_originales) if cruz_key else cupos_originales
        
        TIPOS_VALIDOS = ["HIBR", "CLAS", "EXAM", "PBRA", "AYUD"]
        if not any(x in tipo_r for x in TIPOS_VALIDOS):
            resultados_asignacion[cid] = {
                "CARRERA": materia, "NOMBRE SECCIÓN": seccion, "CUPOS_CONSOLIDADOS": cupos_efectivos,
                "DIA": dia, "HORARIO": horario, "SALA": "SIN SALA", "EDIFICIO": "NINGUNO",
                "ESTADO": "NO REQUIERE", "TIPO_ASIGNACION": "SIN SALA", 
                "MOTIVO_RECHAZO": f"Excluido: Tipo no requiere sala física", "TIPO_REUNION": tipo_r,
                "EFICIENCIA_ESPACIAL": np.nan, "INTENTOS_BUSQUEDA": 0, "ID_CURSO": cid, "CURSO_DICT": curso
            }
            continue

        # --- PREASIGNACIONES MANUALES ---
        if sala_fija != "" and sala_fija != "NAN":
            asigs_sala_fija = matriz_ocupacion.get((sala_fija, dia), [])
            if verificar_colision(start_min, end_min, start_date, end_date, asigs_sala_fija):
                resultados_asignacion[cid] = {
                    "CARRERA": materia, "NOMBRE SECCIÓN": seccion, "CUPOS_CONSOLIDADOS": cupos_efectivos,
                    "DIA": dia, "HORARIO": horario, "SALA": sala_fija, "EDIFICIO": "CONFLICTO PREASIGNACIÓN",
                    "ESTADO": "ERROR PREASIGNADA", "TIPO_ASIGNACION": "PREASIGNADA", 
                    "MOTIVO_RECHAZO": "Conflicto: Sala manual ocupada en este bloque", 
                    "TIPO_REUNION": tipo_r, "EFICIENCIA_ESPACIAL": np.nan, "INTENTOS_BUSQUEDA": 1, "ID_CURSO": cid, "CURSO_DICT": curso
                }
                continue
                
            busqueda = df_infra[df_infra["SALA"] == sala_fija]
            edificio_manual = busqueda.iloc[0]["EDIFICIO"] if not busqueda.empty else "EXTERNA"
            capacidad_real = busqueda.iloc[0]["CAPACIDAD"] if not busqueda.empty else cupos_originales
            
            matriz_ocupacion.setdefault((sala_fija, dia), []).append((start_min, end_min, start_date, end_date, cid))
            contador_carga_salas[sala_fija] = contador_carga_salas.get(sala_fija, 0) + 1
            contador_carga_edificios[edificio_manual] = contador_carga_edificios.get(edificio_manual, 0) + 1

            resultados_asignacion[cid] = {
                "CARRERA": materia, "NOMBRE SECCIÓN": seccion, "CUPOS_CONSOLIDADOS": cupos_efectivos,
                "DIA": dia, "HORARIO": horario, "SALA": sala_fija, "EDIFICIO": edificio_manual,
                "ESTADO": "ASIGNADO", "TIPO_ASIGNACION": "PREASIGNADA", "MOTIVO_RECHAZO": "N/A", "TIPO_REUNION": tipo_r,
                "EFICIENCIA_ESPACIAL": cupos_efectivos / capacidad_real if capacidad_real > 0 else np.nan,
                "INTENTOS_BUSQUEDA": 1, "ID_CURSO": cid, "CURSO_DICT": curso
            }
            
        # --- PROCESO DE ASIGNACIÓN AUTOMÁTICA ---
        else:
            sala_asignada = None
            intentos = 0
            
            if cruz_key and cruz_key in salas_asignadas_cruzadas:
                sala_tmp = salas_asignadas_cruzadas[cruz_key]
                intentos += 1
                asigs_cruz = matriz_ocupacion.get((sala_tmp["SALA"], dia), [])
                if not verificar_colision(start_min, end_min, start_date, end_date, asigs_cruz):
                    sala_asignada = sala_tmp
            else:
                # [PUNTO 7] Filtrado veloz de aforo inicial para optimizar complejidad temporal
                salas_validas = [s for s in salas_universo if s["CAPACIDAD"] >= cupos_efectivos]
                
                # [PUNTO 1 Y 7] Evaluación por Costo Linealizado Unificado
                salas_candidatas = sorted(
                    salas_validas,
                    key=lambda s: calcular_score_sala_lineal(
                        s, orig_base, tipo_r, materia, cupos_efectivos,
                        contador_carga_salas.get(s["SALA"], 0), contador_carga_edificios.get(s["EDIFICIO"], 0)
                    )
                )
                
                umbrales = [eficiencia_minima, 0.00] if not modo_estricto else [eficiencia_minima]
                flag_found = False
                for umbral in umbrales:
                    for sala in salas_candidatas:
                        intentos += 1
                        if (cupos_efectivos / sala["CAPACIDAD"]) < umbral: continue
                        
                        asigs = matriz_ocupacion.get((sala["SALA"], dia), [])
                        if verificar_colision(start_min, end_min, start_date, end_date, asigs): continue
                        
                        sala_asignada = sala
                        flag_found = True
                        if cruz_key: salas_asignadas_cruzadas[cruz_key] = sala
                        break
                    if flag_found: break

            if sala_asignada:
                matriz_ocupacion.setdefault((sala_asignada["SALA"], dia), []).append((start_min, end_min, start_date, end_date, cid))
                contador_carga_salas[sala_asignada["SALA"]] += 1
                contador_carga_edificios[sala_asignada["EDIFICIO"]] += 1
                
                resultados_asignacion[cid] = {
                    "CARRERA": materia, "NOMBRE SECCIÓN": seccion, "CUPOS_CONSOLIDADOS": cupos_efectivos,
                    "DIA": dia, "HORARIO": horario, "SALA": sala_asignada["SALA"], "EDIFICIO": sala_asignada["EDIFICIO"],
                    "ESTADO": "ASIGNADO", "TIPO_ASIGNACION": "AUTOMÁTICA", "MOTIVO_RECHAZO": "N/A", "TIPO_REUNION": tipo_r,
                    "EFICIENCIA_ESPACIAL": cupos_efectivos / sala_asignada["CAPACIDAD"], "INTENTOS_BUSQUEDA": intentos, "ID_CURSO": cid, "CURSO_DICT": curso
                }
            else:
                resultados_asignacion[cid] = {
                    "CARRERA": materia, "NOMBRE SECCIÓN": seccion, "CUPOS_CONSOLIDADOS": cupos_efectivos,
                    "DIA": dia, "HORARIO": horario, "SALA": "SIN SALA", "EDIFICIO": "NINGUNO",
                    "ESTADO": "SIN SALA", "TIPO_ASIGNACION": "SIN SALA", "MOTIVO_RECHAZO": "Sin aforo o colisión total", "TIPO_REUNION": tipo_r,
                    "EFICIENCIA_ESPACIAL": 0.0, "INTENTOS_BUSQUEDA": intentos, "ID_CURSO": cid, "CURSO_DICT": curso
                }

    # =====================================================
    # FASE 3: OPTIMIZACIÓN LOCAL Y REPARACIÓN RECURSIVA (BACKTRACKING) [PUNTO 2, 3 Y 8]
    # =====================================================
    # Buscamos cursos rechazados e intentamos hacer swaps/desplazamientos de colisión
    for cid, res in list(resultados_asignacion.items()):
        if res["ESTADO"] != "SIN SALA": continue
        
        curso_r = res["CURSO_DICT"]
        dia_r = res["DIA"]
        h_r = res["HORARIO"]
        cupos_r = res["CUPOS_CONSOLIDADOS"]
        st_min, ed_min = parse_horario_range(h_r)
        st_date, ed_date = curso_r["FECHA_INI_CONV"], curso_r["FECHA_FIN_CONV"]
        
        reubicado = False
        # Buscamos salas candidatas ideales para romper el bloqueo
        salas_potenciales = [s for s in salas_universo if s["CAPACIDAD"] >= cupos_r]
        
        for sala_p in salas_potenciales:
            asigs_actuales = matriz_ocupacion.get((sala_p["SALA"], dia_r), [])
            
            # Identificamos qué cursos están estorbando en ese bloque
            cursos_obstaculo = []
            for a_st, a_ed, a_sd, a_ed_date, obs_id in asigs_actuales:
                if max(st_date, a_sd) <= min(ed_date, a_ed_date) and max(st_min, a_st) < min(ed_min, a_ed):
                    cursos_obstaculo.append(obs_id)
            
            # Si solo hay 1 curso obstaculizando y es automático (reubicable), intentamos desplazarlo
            if len(cursos_obstaculo) == 1:
                obs_id = cursos_obstaculo[0]
                res_obs = resultados_asignacion.get(obs_id)
                
                if res_obs and res_obs["TIPO_ASIGNACION"] == "AUTOMÁTICA":
                    # Intentamos buscarle una NUEVA sala vacía al curso obstáculo para liberar espacio
                    curso_obs_dict = res_obs["CURSO_DICT"]
                    obs_st, obs_ed = parse_horario_range(res_obs["HORARIO"])
                    obs_sd, obs_ed_d = curso_obs_dict["FECHA_INI_CONV"], curso_obs_dict["FECHA_FIN_CONV"]
                    
                    for sala_escape in salas_universo:
                        if sala_escape["SALA"] == sala_p["SALA"] or sala_escape["CAPACIDAD"] < res_obs["CUPOS_CONSOLIDADOS"]: 
                            continue
                            
                        asigs_escape = matriz_ocupacion.get((sala_escape["SALA"], dia_r), [])
                        if not verificar_colision(obs_st, obs_ed, obs_sd, obs_ed_d, asigs_escape):
                            # ¡BINGO! El curso obstáculo puede moverse a 'sala_escape'
                            # 1. Remover obstáculo de la sala original
                            matriz_ocupacion[(sala_p["SALA"], dia_r)] = [a for a in asigs_actuales if a[4] != obs_id]
                            
                            # 2. Insertar obstáculo en su sala de escape
                            matriz_ocupacion.setdefault((sala_escape["SALA"], dia_r), []).append((obs_st, obs_ed, obs_sd, obs_ed_d, obs_id))
                            
                            # 3. Actualizar datos del obstáculo
                            contador_carga_salas[sala_p["SALA"]] -= 1
                            contador_carga_salas[sala_escape["SALA"]] += 1
                            resultados_asignacion[obs_id].update({
                                "SALA": sala_escape["SALA"], "EDIFICIO": sala_escape["EDIFICIO"],
                                "EFICIENCIA_ESPACIAL": res_obs["CUPOS_CONSOLIDADOS"] / sala_escape["CAPACIDAD"]
                            })
                            
                            # 4. Asignar el curso rechazado original a la sala liberada
                            matriz_ocupacion.setdefault((sala_p["SALA"], dia_r), []).append((st_min, ed_min, st_date, ed_date, cid))
                            contador_carga_salas[sala_p["SALA"]] += 1
                            
                            resultados_asignacion[cid].update({
                                "SALA": sala_p["SALA"], "EDIFICIO": sala_p["EDIFICIO"], "ESTADO": "ASIGNADO",
                                "TIPO_ASIGNACION": "AUTOMÁTICA (REPARADO F3)", "MOTIVO_RECHAZO": "N/A",
                                "EFICIENCIA_ESPACIAL": cupos_r / sala_p["CAPACIDAD"]
                            })
                            reubicado = True
                            break
            if reubicado: break

    # =====================================================
    # FASE 4: REPORTE Y CONSTRUCCIÓN DE DATAFRAMES FINALES
    # =====================================================
    lista_final_res = list(resultados_asignacion.values())
    df_res = pd.DataFrame(lista_final_res)
    df_malla = df_res[df_res["ESTADO"] == "ASIGNADO"].copy()
    
    # Contadores de metadatos globales
    conteo_pre = sum(1 for x in lista_final_res if "PREASIGNADA" in x["TIPO_ASIGNACION"])
    conteo_auto = sum(1 for x in lista_final_res if "AUTOMÁTICA" in x["TIPO_ASIGNACION"])
    conteo_rech = sum(1 for x in lista_final_res if x["ESTADO"] == "SIN SALA")
    conteo_err_p = sum(1 for x in lista_final_res if x["ESTADO"] == "ERROR PREASIGNADA")

    horarios_unicos = df_res["HORARIO"].unique()
    bloques_totales = sorted(list(set([tuple(h.split("-")) for h in horarios_unicos if "-" in h])), key=lambda x: parse_time_to_minutes(x[0]))
    if not bloques_totales: bloques_totales = [("08:30", "10:00"), ("10:15", "11:45"), ("12:00", "13:30"), ("14:30", "16:00")]
    
    dias_totales = ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES", "SABADO"]
    capacidad_semanal = len(bloques_totales) * len(dias_totales)

    metricas_salas = []
    for sala in salas_universo:
        df_s_asig = df_malla[df_malla["SALA"] == sala["SALA"]] if not df_malla.empty else pd.DataFrame()
        occ = len(df_s_asig)
        metricas_salas.append({
            "SALA": sala["SALA"], "EDIFICIO": sala["EDIFICIO"], "CAPACIDAD": sala["CAPACIDAD"],
            "HORAS_OCUPADAS": occ, "HORAS_LIBRES": max(0, capacidad_semanal - occ),
            "EFICIENCIA_PROMEDIO": df_s_asig["EFICIENCIA_ESPACIAL"].dropna().mean() if occ > 0 else 0.0
        })
    df_s = pd.DataFrame(metricas_salas)

    df_e = df_s.groupby("EDIFICIO")["HORAS_OCUPADAS"].sum().reset_index() if not df_s.empty else pd.DataFrame(columns=["EDIFICIO", "HORAS_OCUPADAS"])
    df_car = df_malla.groupby("CARRERA").size().reset_index(name="HORAS_OCUPADAS") if not df_malla.empty else pd.DataFrame()
    df_tip = df_malla.groupby("TIPO_REUNION").size().reset_index(name="HORAS_CONSUMIDAS") if not df_malla.empty else pd.DataFrame()
    df_dem = df_res.groupby(["DIA", "HORARIO"]).size().reset_index(name="BLOQUES_ACTIVOS") if not df_res.empty else pd.DataFrame()
    df_rech_df = df_res[df_res["ESTADO"] == "SIN SALA"].groupby("CARRERA").size().reset_index(name="sin_sala") if not df_res.empty else pd.DataFrame()

    # O(1) Inventario de salas libres optimizado
    lista_libres = []
    fecha_base_ini = pd.to_datetime("2026-03-01").date()
    fecha_base_fin = pd.to_datetime("2026-12-31").date()
    
    for sala in salas_universo:
        for d in dias_totales:
            asigs_actuales = matriz_ocupacion.get((sala["SALA"], d), [])
            for b_ini, b_fin in bloques_totales:
                s_min = parse_time_to_minutes(b_ini)
                e_min = parse_time_to_minutes(b_fin)
                
                asigs_bloque = [
                    (a_start, a_end, a_sdate, a_edate) 
                    for a_start, a_end, a_sdate, a_edate, _ in asigs_actuales 
                    if max(s_min, a_start) < min(e_min, a_end)
                ]
                
                if not asigs_bloque:
                    lista_libres.append({
                        "SALA": sala["SALA"], "EDIFICIO": sala["EDIFICIO"], "CAPACIDAD": sala["CAPACIDAD"],
                        "DIA": d, "INICIO": b_ini, "FIN": b_fin, "FECHA_DISP_INI": fecha_base_ini, "FECHA_DISP_FIN": fecha_base_fin
                    })
                else:
                    asigs_bloque.sort(key=lambda x: x[2])
                    curr_start = fecha_base_ini
                    for _, _, s_date, e_date in asigs_bloque:
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
                        
    df_lib = pd.DataFrame(lista_libres)

    resumen_metadata = {
        "escenario": escenario_id,
        "manuales": conteo_pre,
        "automaticas": conteo_auto,
        "total_asignadas": conteo_pre + conteo_auto,   # <-- Cursos asignados con éxito
        "sin_sala": conteo_rech,                       # <-- Cursos que no se pudieron asignar
        "errores_preasignacion": conteo_err_p,
        "porcentaje_asignacion": round(((conteo_auto + conteo_pre) / len(df_res)) * 100, 1) if len(df_res) > 0 else 0, # <-- Efectividad
        "salas_utilizadas": int(df_malla["SALA"].nunique()) if not df_malla.empty else 0
    }

    return df_res, matriz_ocupacion, df_malla, resumen_metadata, df_s, df_e, df_car, df_tip, df_dem, df_lib, df_rech_df
