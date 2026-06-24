# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np

def ejecutar_asignacion_global(
    archivo_cursos_excel,
    solo_postgrado=False,
    solo_pregrado=False,
    lista_carreras=None,
    lista_reuniones=None,
    lista_edificios=None,
    lista_tipos_sala=None,
    lista_formatos=None,
    lista_salas=None
):
    """
    Motor de asignación jerárquica corregido. 
    Se añade una Fase de Rescate Absoluto para garantizar que las salas grandes (como Aulas Magnas en HUM)
    absorban los cursos que de otro modo quedarían sin espacio, ignorando penalizaciones de eficiencia.
    """
    ruta_infraestructura = "infraestructura_constante.xlsx"
    
    # =============================================================================
    # 1. CARGA DE INFRAESTRUCTURA CONSTANTE
    # =============================================================================
    try:
        salas_PROV = pd.read_excel(ruta_infraestructura, sheet_name="SALAS")
    except Exception as e:
        raise FileNotFoundError(f"No se encontró el archivo maestro '{ruta_infraestructura}' o falta la pestaña SALAS. Error: {e}")

    # Limpieza inicial de columnas de infraestructura
    salas_PROV["TIPO DE SALA"] = salas_PROV["TIPO DE SALA"].fillna("").astype(str).str.strip().str.upper()
    salas_PROV["FORMATO"] = salas_PROV["FORMATO"].fillna("").astype(str).str.strip().str.upper()
    salas_PROV["EDIFICIO"] = salas_PROV["EDIFICIO"].fillna("").astype(str).str.strip().str.upper()
    salas_PROV["SALA"] = salas_PROV["SALA"].fillna("").astype(str).str.strip().str.upper()

    # Detectar nombres idénticos (ej: AULA MAGNA) y renombrarlos uniendo su aforo directamente
    salas_duplicadas = salas_PROV[salas_PROV.duplicated(subset=["SALA"], keep=False)]["SALA"].unique()

    # Diccionario maestro global
    salas_dict_global = {}
    for idx, fila in salas_PROV.iterrows():
        s_nombre = str(fila["SALA"]).strip().upper()
        
        if s_nombre in salas_duplicadas:
            s_nombre = f"{s_nombre} {int(fila['CAPACIDAD'])}"
            salas_PROV.at[idx, "SALA"] = s_nombre  

        salas_dict_global[s_nombre] = {
            "SALA": s_nombre,
            "EDIFICIO": str(fila["EDIFICIO"]),
            "CAPACIDAD": int(fila["CAPACIDAD"]),
            "TIPO DE SALA": str(fila["TIPO DE SALA"]),
            "FORMATO": str(fila["FORMATO"]),
            "TIPO RESTRICCION": str(fila.get("TIPO RESTRICCION", "NORMAL")).strip().upper()
        }

    # Filtros desde la UI de Streamlit
    if lista_edificios is not None:
        text_edificios = [str(e).upper().strip() for e in lista_edificios]
        salas_PROV = salas_PROV[salas_PROV["EDIFICIO"].isin(text_edificios)]
    if lista_tipos_sala is not None:
        text_tipos = [str(t).upper().strip() for t in lista_tipos_sala]
        salas_PROV = salas_PROV[salas_PROV["TIPO DE SALA"].isin(text_tipos)]
    if lista_formatos is not None:
        text_formatos = [str(f).upper().strip() for f in lista_formatos]
        salas_PROV = salas_PROV[salas_PROV["FORMATO"].isin(text_formatos)]
    if lista_salas is not None:
        text_salas = [str(s).upper().strip() for s in lista_salas]
        salas_PROV = salas_PROV[salas_PROV["SALA"].isin(text_salas)]

    if salas_PROV.empty:
        raise ValueError("Los filtros de infraestructura redujeron las salas disponibles a cero.")

    # Agrupación de salas útiles para el motor
    salas_por_edificio = {}
    for _, fila in salas_PROV.iterrows():
        s_nombre = fila["SALA"]
        s_info = salas_dict_global[s_nombre]
        salas_por_edificio.setdefault(s_info["EDIFICIO"], []).append(s_info)

    # Ordenar salas por capacidad de forma ascendente
    for edificio in salas_por_edificio:
        salas_por_edificio[edificio] = sorted(salas_por_edificio[edificio], key=lambda x: x["CAPACIDAD"])

    # =============================================================================
    # 2. CARGA Y CONCATENACIÓN DE HOJAS DE CURSOS
    # =============================================================================
    dfs_a_concatenar = []
    if not solo_postgrado:
        try:
            df_pre = pd.read_excel(archivo_cursos_excel, sheet_name="BASE PREGRADO")
            df_pre["POSTGRADO_FLAG"] = False
            dfs_a_concatenar.append(df_pre)
        except Exception as e:
            print(f"Aviso: No se pudo leer BASE PREGRADO: {e}")
            
    if not solo_pregrado:
        try:
            df_post = pd.read_excel(archivo_cursos_excel, sheet_name="BASE POSTGRADO")
            df_post["POSTGRADO_FLAG"] = True
            dfs_a_concatenar.append(df_post)
        except Exception as e:
            print(f"Aviso: No se pudo leer BASE POSTGRADO: {e}")
            
    if not dfs_a_concatenar:
        raise ValueError("No hay datos de cursos para procesar.")
        
    base_raw = pd.concat(dfs_a_concatenar, ignore_index=True)

    # =============================================================================
    # 3. TRANSICIÓN A FORMATO PLANO (UNPIVOT)
    # =============================================================================
    dias_columnas = ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES", "SABADO"]
    filas_normalizadas = []

    for idx, row in base_raw.iterrows():
        if pd.isna(row["MATERIA"]) or pd.isna(row["CUPOS"]):
            continue

        for dia in dias_columnas:
            val_hora = row[dia]
            if pd.notna(val_hora) and str(val_hora).strip() != "":
                partes = str(val_hora).split("-")
                if len(partes) == 2:
                    try:
                        hi = pd.to_datetime(partes[0].strip()).time()
                        hf = pd.to_datetime(partes[1].strip()).time()
                    except:
                        continue 
                    
                    nueva_fila = row.to_dict()
                    nueva_fila["DIA"] = dia
                    nueva_fila["HORARIO"] = f"{hi.strftime('%H:%M')} - {hf.strftime('%H:%M')}"
                    nueva_fila["INICIO"] = pd.to_datetime(row["INICIO"])
                    nueva_fila["FIN"] = pd.to_datetime(row["FIN"])
                    
                    nueva_fila["DIAS_STD"] = dia
                    nueva_fila["HORA INICIO"] = hi
                    nueva_fila["HORA TERMINO"] = hf
                    nueva_fila["FECHA INICIO"] = nueva_fila["INICIO"]
                    nueva_fila["FECHA TERMINO"] = nueva_fila["FIN"]
                    nueva_fila["CARRERA"] = str(row["MATERIA"]).strip().upper()
                    nueva_fila["NOMBRE SECCIÓN"] = str(row["TITULO"]).strip().upper()
                    nueva_fila["MAX ALUMNOS"] = int(row["CUPOS"])
                    nueva_fila["TIPO DE REUNION"] = str(row["TIPO"]).strip().upper()
                    if nueva_fila["TIPO DE REUNION"] == "HYBR":
                        nueva_fila["TIPO DE REUNION"] = "HIBR"
                    
                    filas_normalizadas.append(nueva_fila)

    if len(filas_normalizadas) == 0:
        raise ValueError("No se encontraron bloques de horarios válidos.")

    base = pd.DataFrame(filas_normalizadas)

    if "LISTA CRUZADA" in base.columns:
        base["LISTA CRUZADA"] = base["LISTA CRUZADA"].fillna("").astype(str).str.strip().str.upper()
    else:
        base["LISTA CRUZADA"] = ""

    base["GRUPO_ID"] = base.index.astype(str)
    mask_cruzada = base["LISTA CRUZADA"] != ""

    if mask_cruzada.any():
        base.loc[mask_cruzada, "GRUPO_ID"] = (
            "CRUZ_" + 
            base.loc[mask_cruzada, "LISTA CRUZADA"] + "_" +
            base.loc[mask_cruzada, "DIA"] + "_" +
            base.loc[mask_cruzada, "HORARIO"] + "_" +
            base.loc[mask_cruzada, "FECHA INICIO"].dt.strftime('%Y%m%d') + "_" +
            base.loc[mask_cruzada, "FECHA TERMINO"].dt.strftime('%Y%m%d')
        )
    
    base["CUPOS_CONSOLIDADOS"] = base.groupby("GRUPO_ID")["MAX ALUMNOS"].transform("sum")

    if lista_carreras is not None:
        text_carreras = [str(c).upper().strip() for c in lista_carreras]
        base = base[base["CARRERA"].isin(text_carreras)]
    if lista_reuniones is not None:
        text_reuniones = [str(r).upper().strip() for r in lista_reuniones]
        base = base[base["TIPO DE REUNION"].isin(text_reuniones)]

    if base.empty:
        raise ValueError("Los filtros aplicados dejaron la lista de cursos vacía.")

    def prioridad_reunion(row):
        r = row["TIPO DE REUNION"]
        if r == "HIBR": return 1
        if r == "CLAS": return 2
        if r in ["EXAM", "PRBA"]: return 3
        if r == "AYUD": return 4
        return 5

    base["PRIORIDAD"] = base.apply(prioridad_reunion, axis=1)
    base = base.sort_values(by=["POSTGRADO_FLAG", "PRIORIDAD", "MAX ALUMNOS"], ascending=[False, True, False]).reset_index(drop=True)

    base["CAPACIDAD SALA"] = np.nan
    base["% OCUPACION SALA"] = ""
    base["ESTADO"] = "PENDIENTE"
    base["MOTIVO_RECHAZO"] = ""
    
    if "SALA" not in base.columns:
        base["SALA"] = ""
    else:
        base["SALA"] = base["SALA"].fillna("").astype(str).str.strip().str.upper()

    sala_manual_por_grupo = base[base["SALA"] != ""].groupby("GRUPO_ID")["SALA"].first()
    if not sala_manual_por_grupo.empty:
        base["SALA"] = base["GRUPO_ID"].map(sala_manual_por_grupo).fillna(base["SALA"])

    grupo_dict = {
        "INGENIERIA": ["ICA", "ICC", "ICE", "ICI", "ING", "INM", "IOC"],
        "ADMINISTRACION": ["ADM", "DEM", "DER", "EAD", "EAI", "EAM", "ECN", "MAD"],
        "SALUD": ["KIN", "MED", "ENF", "NUT", "ODON"]
    }
    carreras_ing = set(grupo_dict["INGENIERIA"])
    carreras_adm = set(grupo_dict["ADMINISTRACION"])

    # =============================================================================
    # 🔒 FASE 0: PROCESAR ASIGNACIONES MANUALES
    # =============================================================================
    ocupacion = {}  
    cursos_preasignados = base[base["SALA"] != ""]
    grupos_procesados_fase0 = set()

    for idx, curso in cursos_preasignados.iterrows():
        sala_fija = curso["SALA"]
        dia_fijo = curso["DIAS_STD"]
        hi = curso["HORA INICIO"]
        hf = curso["HORA TERMINO"]
        fi = curso["FECHA INICIO"]
        ff = curso["FECHA TERMINO"]
        alumnos_total = int(curso["CUPOS_CONSOLIDADOS"])
        carrera = curso["CARRERA"]
        sec = str(curso["NOMBRE SECCIÓN"]).upper()
        gid = curso["GRUPO_ID"]

        nombre_ocupante = f"LISTA CRUZADA: {curso['LISTA CRUZADA']}" if gid.startswith("CRUZ_") else f"{carrera} - {sec}"

        if sala_fija in salas_dict_global:
            cap_sala = salas_dict_global[sala_fija]["CAPACIDAD"]
            base.loc[idx, "CAPACIDAD SALA"] = cap_sala
            base.loc[idx, "% OCUPACION SALA"] = f"{(alumnos_total / cap_sala * 100):.1f}%"
            base.loc[idx, "ESTADO"] = "ASIGNADO MANUAL"  
            
            if gid not in grupos_procesados_fase0:
                ocupacion.setdefault(sala_fija, []).append((dia_fijo, hi, hf, fi, ff, nombre_ocupante, alumnos_total, cap_sala))
                grupos_procesados_fase0.add(gid)
        else:
            cap_sala = alumnos_total  
            base.loc[idx, "CAPACIDAD SALA"] = cap_sala
            base.loc[idx, "% OCUPACION SALA"] = "100.0% (Excepcional)"
            base.loc[idx, "ESTADO"] = "ASIGNADO MANUAL (EXCEPCIONAL)"  
            
            if gid not in grupos_procesados_fase0:
                ocupacion.setdefault(sala_fija, []).append((dia_fijo, hi, hf, fi, ff, nombre_ocupante, alumnos_total, cap_sala))
                grupos_procesados_fase0.add(gid)

    # =============================================================================
    # 🛠️ REGLAS COMPATIBILIDAD MOTOR
    # =============================================================================
    def edificios_preferidos(carrera):
        if carrera in carreras_ing: return ["ING", "CIEN", "REL", "BIB", "HUM"]
        if carrera in carreras_adm: return ["REL", "BIB", "CIEN", "HUM", "ING"]
        return ["HUM", "CIEN", "REL", "BIB", "CEN", "ING"]

    def sala_compatible_fase(curso, sala, fase):
        nombre_sala = str(sala["SALA"]).upper()
        if "DOCT" in nombre_sala: return True
        reunion = curso["TIPO DE REUNION"]
        tipo_sala = sala["TIPO DE SALA"]
        formato = sala["FORMATO"]
        is_post = curso["POSTGRADO_FLAG"]

        if fase in [1, 2]:
            if is_post:
                if reunion == "HIBR" and not (tipo_sala == "HYFLEX" or formato == "AUDITORIO"): return False
                if reunion == "CLAS" and not (tipo_sala == "STREAMING" or sala["EDIFICIO"] == "REL"): return False
            else:
                if reunion == "CLAS" and not (tipo_sala in ["STREAMING", "SALA NORMAL"]): return False
                if reunion in ["EXAM", "PRBA"] and not (formato == "PLANA" or tipo_sala == "STREAMING"): return False
        return True

    def sala_disponible_info(sala_nombre, dia, hi, hf, fi, ff):
        if sala_nombre not in ocupacion: return True
        for b in ocupacion[sala_nombre]:
            b_dia, b_hi, b_hf, b_fi, b_ff, _, _, _ = b
            if b_dia == dia:
                if (hi < b_hf and hf > b_hi) and (fi <= b_ff and ff >= b_fi):
                    return False
        return True

    # =============================================================================
    # 🚀 FASES ORDINARIAS (1 A 5)
    # =============================================================================
    niveles_fase = [1, 2, 3, 4, 5]
    umbrales_eficiencia = [0.75, 0.50, 0.25, 0.0]

    def procesar_bloques(indices_subconjunto, es_post):
        no_asignados = indices_subconjunto.copy()

        for fase in niveles_fase:
            for umbral in umbrales_eficiencia:
                removidos = set()

                for idx in no_asignados:
                    if base.loc[idx, "ESTADO"] != "PENDIENTE":
                        removidos.add(idx)
                        continue

                    curso = base.loc[idx]
                    carrera = curso["CARRERA"]
                    alumnos_grupo = int(curso["CUPOS_CONSOLIDADOS"])
                    dia = curso["DIAS_STD"]
                    inicio = curso["HORA INICIO"]
                    fin = curso["HORA TERMINO"]
                    fi = curso["FECHA INICIO"]
                    ff = curso["FECHA TERMINO"]
                    sec = str(curso["NOMBRE SECCIÓN"]).upper()
                    gid = curso["GRUPO_ID"]

                    # Buscar en todos los edificios del maestro
                    salas_candidatas = [sala for e in salas_por_edificio for sala in salas_por_edificio[e]]

                    mejor_sala = None
                    mejor_score = -1e15
                    motivos = set()

                    for sala in salas_candidatas:
                        nombre = sala["SALA"]
                        cap = sala["CAPACIDAD"]

                        if alumnos_grupo > cap:
                            motivos.add("Capacidad insuficiente")
                            continue

                        ratio = alumnos_grupo / cap
                        if ratio < umbral:
                            motivos.add(f"Eficiencia menor al {int(umbral*100)}%")
                            continue

                        if not sala_compatible_fase(curso, sala, fase):
                            motivos.add("Tipo de sala/Formato restringido")
                            continue

                        if not sala_disponible_info(nombre, dia, inicio, fin, fi, ff):
                            motivos.add("Choque horario")
                            continue

                        score = ratio * 600
                        if sala["EDIFICIO"] in edificios_preferidos(carrera): score += 300
                        if es_post: score += 6000000
                        
                        if score > mejor_score:
                            mejor_score = score
                            mejor_sala = sala

                    if mejor_sala is not None:
                        nombre_sala = mejor_sala["SALA"]
                        cap_final = mejor_sala["CAPACIDAD"]
                        
                        indices_mismo_grupo = base[base["GRUPO_ID"] == gid].index.tolist()
                        for g_idx in indices_mismo_grupo:
                            base.loc[g_idx, "SALA"] = nombre_sala
                            base.loc[g_idx, "CAPACIDAD SALA"] = cap_final
                            base.loc[g_idx, "% OCUPACION SALA"] = f"{(alumnos_grupo / cap_final * 100):.1f}%"
                            base.loc[g_idx, "ESTADO"] = f"ASIGNADO F{fase}"
                            base.loc[g_idx, "MOTIVO_RECHAZO"] = ""
                        
                        nombre_ocupante = f"LISTA CRUZADA: {curso['LISTA CRUZADA']}" if gid.startswith("CRUZ_") else f"{carrera} - {sec}"
                        ocupacion.setdefault(nombre_sala, []).append((dia, inicio, fin, fi, ff, nombre_ocupante, alumnos_grupo, cap_final))
                        removidos.add(idx)
                    else:
                        if len(motivos) > 0:
                            indices_mismo_grupo = base[base["GRUPO_ID"] == gid].index
                            for g_idx in indices_mismo_grupo:
                                base.loc[g_idx, "MOTIVO_RECHAZO"] = "; ".join(sorted(motivos))

                no_asignados = [i for i in no_asignados if i not in removidos]

        # =============================================================================
        # 🚨 BUCLE DE RESCATE CRÍTICO (FALLBACK ABSOLUTO)
        # =============================================================================
        # Si un curso sigue PENDIENTE, rompemos cualquier filtro de Tipo de Sala o Eficiencia.
        # Prioridad: Ocupar las salas grandes disponibles (como Aulas Magnas en HUM) antes de dejar "SIN SALA".
        if len(no_asignados) > 0:
            removidos = set()
            for idx in no_asignados:
                if base.loc[idx, "ESTADO"] != "PENDIENTE":
                    removidos.add(idx)
                    continue

                curso = base.loc[idx]
                carrera = curso["CARRERA"]
                alumnos_grupo = int(curso["CUPOS_CONSOLIDADOS"])
                dia = curso["DIAS_STD"]
                inicio = curso["HORA INICIO"]
                fin = curso["HORA TERMINO"]
                fi = curso["FECHA INICIO"]
                ff = curso["FECHA TERMINO"]
                gid = curso["GRUPO_ID"]
                sec = str(curso["NOMBRE SECCIÓN"]).upper()

                todas_las_salas = [sala for e in salas_por_edificio for sala in salas_por_edificio[e]]
                
                mejor_sala = None
                mejor_score = -1e15

                for sala in todas_las_salas:
                    nombre = sala["SALA"]
                    cap = sala["CAPACIDAD"]

                    # Las dos únicas condiciones insalvables: Capacidad física y disponibilidad horaria
                    if alumnos_grupo > cap:
                        continue

                    if not sala_disponible_info(nombre, dia, inicio, fin, fi, ff):
                        continue

                    # Priorizar salas según cercanía o de edificio HUM si corresponde, ordenando por mejor ajuste
                    ratio = alumnos_grupo / cap
                    score = ratio * 100
                    if sala["EDIFICIO"] == "HUM": score += 500  # Empuja fuertemente el uso de infraestructura HUM

                    if score > mejor_score:
                        mejor_score = score
                        mejor_sala = sala

                if mejor_sala is not None:
                    nombre_sala = mejor_sala["SALA"]
                    cap_final = mejor_sala["CAPACIDAD"]
                    
                    indices_mismo_grupo = base[base["GRUPO_ID"] == gid].index.tolist()
                    for g_idx in indices_mismo_grupo:
                        base.loc[g_idx, "SALA"] = nombre_sala
                        base.loc[g_idx, "CAPACIDAD SALA"] = cap_final
                        base.loc[g_idx, "% OCUPACION SALA"] = f"{(alumnos_grupo / cap_final * 100):.1f}%"
                        base.loc[g_idx, "ESTADO"] = "ASIGNADO RESCATE"
                        base.loc[g_idx, "MOTIVO_RECHAZO"] = ""
                    
                    nombre_ocupante = f"LISTA CRUZADA: {curso['LISTA CRUZADA']}" if gid.startswith("CRUZ_") else f"{carrera} - {sec}"
                    ocupacion.setdefault(nombre_sala, []).append((dia, inicio, fin, fi, ff, nombre_ocupante, alumnos_grupo, cap_final))
                    removidos.add(idx)

            no_asignados = [i for i in no_asignados if i not in removidos]

    # Ejecutar procesamiento segregado
    base_pendientes = base[base["ESTADO"] == "PENDIENTE"]
    df_representantes = base_pendientes.drop_duplicates(subset=["GRUPO_ID"], keep="first")

    postgrado_idx = df_representantes[df_representantes["POSTGRADO_FLAG"] == True].index.tolist()
    pregrado_idx = df_representantes[df_representantes["POSTGRADO_FLAG"] == False].index.tolist()

    procesar_bloques(postgrado_idx, True)
    procesar_bloques(pregrado_idx, False)

    # Consolidar estados finales "SIN SALA"
    for gid in base["GRUPO_ID"].unique():
        filas_grupo = base[base["GRUPO_ID"] == gid]
        if (filas_grupo["ESTADO"] == "PENDIENTE").all():
            ultimo_motivo = ""
            motivos_validos = filas_grupo[filas_grupo["MOTIVO_RECHAZO"].str.strip() != ""]["MOTIVO_RECHAZO"]
            ultimo_motivo = motivos_validos.iloc[0] if len(motivos_validos) > 0 else "Excede capacidad total de la infraestructura libre"
    
            base.loc[filas_grupo.index, "ESTADO"] = "SIN SALA"
            base.loc[filas_grupo.index, "MOTIVO_RECHAZO"] = ultimo_motivo

    # =============================================================================
    # GENERACIÓN DE REPORTES ANALÍTICOS Y SALAS LIBRES
    # =============================================================================
    resumen_edificios = pd.DataFrame(columns=["EDIFICIO", "cupos_usados", "capacidad_total", "% USO"])
    resumen_carreras = pd.DataFrame(columns=["CARRERA", "cursos", "alumnos"])
    resumen_salas = pd.DataFrame(columns=["SALA", "ocupacion", "capacidad", "% USO"])
    df_salas_libres = pd.DataFrame(columns=["SALA"])

    registros_malla = []
    for sala, bloques in ocupacion.items():
        for b in bloques:
            alums = b[6]
            cap = b[7]
            pct = (alums / cap * 100) if cap > 0 else 0
            registros_malla.append({
                "SALA": sala, "DIA": b[0], "HORARIO": f"{b[1].strftime('%H:%M')} - {b[2].strftime('%H:%M')}",
                "INICIO": b[3].strftime('%d-%m-%Y'), "FIN": b[4].strftime('%d-%m-%Y'),    
                "CURSO_OCUPANTE": b[5], "CUPOS_ALUMNOS": alums, "CAPACIDAD SALA": cap, "% OCUPACION SALA": f"{pct:.1f}%"
            })
            
    df_malla = pd.DataFrame(registros_malla)
    
    if not df_malla.empty:
        df_malla = df_malla.sort_values(by=["SALA", "DIA", "HORARIO"]).reset_index(drop=True)
        df_malla["CAPACIDAD SALA"] = pd.to_numeric(df_malla["CAPACIDAD SALA"], errors="coerce")
        df_malla["CUPOS_ALUMNOS"] = pd.to_numeric(df_malla["CUPOS_ALUMNOS"], errors="coerce")

        sala_a_edificio = {sala: info["EDIFICIO"] for sala, info in salas_dict_global.items()}
        df_malla["EDIFICIO"] = df_malla["SALA"].map(sala_a_edificio)

        resumen_edificios = df_malla.groupby("EDIFICIO").agg(cupos_usados=("CUPOS_ALUMNOS", "sum"), capacidad_total=("CAPACIDAD SALA", "sum")).reset_index()
        resumen_edificios["% USO"] = (resumen_edificios["cupos_usados"] / resumen_edificios["capacidad_total"] * 100).round(2)

        resumen_salas = df_malla.groupby("SALA").agg(ocupacion=("CUPOS_ALUMNOS", "sum"), capacidad=("CAPACIDAD SALA", "max")).reset_index()
        resumen_salas["% USO"] = (resumen_salas["ocupacion"] / resumen_salas["capacidad"] * 100).round(2)

        salas_usadas = set(df_malla["SALA"].unique())
        salas_totales = set(salas_dict_global.keys())
        df_salas_libres = pd.DataFrame({"SALA": list(salas_totales - salas_usadas)})
    else:
        df_salas_libres = pd.DataFrame({"SALA": list(salas_dict_global.keys())})

    if not base.empty:
        resumen_carreras = base.groupby("CARRERA").agg(cursos=("CARRERA", "count"), alumnos=("CUPOS", "sum")).reset_index()

    base["INICIO"] = base["INICIO"].dt.strftime('%d-%m-%Y')
    base["FIN"] = base["FIN"].dt.strftime('%d-%m-%Y')

    columnas_finales = [
        "N°", "PERIODO", "ESCUELA", "NRC", "CONECTOR LIGA", "LISTA CRUZADA", 
        "MATERIA", "CURSO SECC.", "CALIFICABLE", "TITULO", "STATUS", "P/P", 
        "CREDITO", "ESCALA CALIFICACION", "CAMPUS", "DIA", "HORARIO", "INICIO", "FIN", 
        "SALA", "TIPO", "RUT PROFESOR", "PROFESOR", "CUPOS", "INSCRITOS", 
        "% INSCRITOS / CUPOS", "CAPACIDAD SALA", "% OCUPACION SALA", "ESTADO", "MOTIVO_RECHAZO"
    ]
    columnas_entrega = [col for col in columnas_finales if col in base.columns]
    return base[columnas_entrega].copy(), df_malla, resumen_edificios, resumen_carreras, resumen_salas, df_salas_libres
