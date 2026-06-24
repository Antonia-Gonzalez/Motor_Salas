# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np

def ejecutar_asignacion_incremental(
    archivo_cursos_excel,
    eficiencia_minima=0.50,  # Recibido directamente desde el slider de la UI (0.0 a 1.0)
    ocupacion_previa=None,   # Memoria de asignaciones pasadas (st.session_state)
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
    Motor de asignación de estado persistente.
    Permite ejecuciones secuenciales acumulando la ocupación en una matriz global.
    """
    ruta_infraestructura = "infraestructura_constante.xlsx"
    
    # =============================================================================
    # 1. CARGA Y FILTRADO DE INFRAESTRUCTURA
    # =============================================================================
    try:
        salas_PROV = pd.read_excel(ruta_infraestructura, sheet_name="SALAS")
    except Exception as e:
        raise FileNotFoundError(f"No se encontró el archivo maestro '{ruta_infraestructura}'. Error: {e}")

    salas_PROV["TIPO DE SALA"] = salas_PROV["TIPO DE SALA"].fillna("").astype(str).str.strip().str.upper()
    salas_PROV["FORMATO"] = salas_PROV["FORMATO"].fillna("").astype(str).str.strip().str.upper()
    salas_PROV["EDIFICIO"] = salas_PROV["EDIFICIO"].fillna("").astype(str).str.strip().str.upper()
    salas_PROV["SALA"] = salas_PROV["SALA"].fillna("").astype(str).str.strip().str.upper()

    salas_duplicadas = salas_PROV[salas_PROV.duplicated(subset=["SALA"], keep=False)]["SALA"].unique()

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
            "FORMATO": str(fila["FORMATO"])
        }

    # Aplicar filtros dinámicos de infraestructura de la corrida actual
    if lista_edificios:
        salas_PROV = salas_PROV[salas_PROV["EDIFICIO"].isin([str(e).upper().strip() for e in lista_edificios])]
    if lista_tipos_sala:
        salas_PROV = salas_PROV[salas_PROV["TIPO DE SALA"].isin([str(t).upper().strip() for t in lista_tipos_sala])]
    if lista_formatos:
        salas_PROV = salas_PROV[salas_PROV["FORMATO"].isin([str(f).upper().strip() for f in lista_formatos])]
    if lista_salas:
        salas_PROV = salas_PROV[salas_PROV["SALA"].isin([str(s).upper().strip() for s in lista_salas])]

    if salas_PROV.empty:
        raise ValueError("Los filtros de infraestructura redujeron las salas disponibles a cero.")

    salas_por_edificio = {}
    for _, fila in salas_PROV.iterrows():
        s_info = salas_dict_global[fila["SALA"]]
        salas_por_edificio.setdefault(s_info["EDIFICIO"], []).append(s_info)

    for ed in salas_por_edificio:
        salas_por_edificio[ed] = sorted(salas_por_edificio[ed], key=lambda x: x["CAPACIDAD"])

    # =============================================================================
    # 2. PERSISTENCIA DE CONTROL HORARIO (EL NÚCLEO DEL CAMBIO)
    # =============================================================================
    # Si viene memoria de corridas anteriores se respeta, si no, se inicializa vacía.
    ocupacion = ocupacion_previa.copy() if ocupacion_previa is not None else {}

    # =============================================================================
    # 3. PROCESAMIENTO DE CURSOS SUBIDOS (FILTRADO POR ESCENARIO CARRERA)
    # =============================================================================
    dfs_a_concatenar = []
    if not solo_postgrado:
        try:
            df_pre = pd.read_excel(archivo_cursos_excel, sheet_name="BASE PREGRADO")
            df_pre["POSTGRADO_FLAG"] = False
            dfs_a_concatenar.append(df_pre)
        except: pass
    if not solo_pregrado:
        try:
            df_post = pd.read_excel(archivo_cursos_excel, sheet_name="BASE POSTGRADO")
            df_post["POSTGRADO_FLAG"] = True
            dfs_a_concatenar.append(df_post)
        except: pass
            
    if not dfs_a_concatenar:
        raise ValueError("No se encontraron pestañas válidas de cursos.")
        
    base_raw = pd.concat(dfs_a_concatenar, ignore_index=True)

    # Transformación a renglones planos por día/hora
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
                    except: continue 
                    
                    nueva_fila = row.to_dict()
                    nueva_fila["DIA"] = dia
                    nueva_fila["HORARIO"] = f"{hi.strftime('%H:%M')} - {hf.strftime('%H:%M')}"
                    nueva_fila["HORA INICIO"] = hi
                    nueva_fila["HORA TERMINO"] = hf
                    nueva_fila["FECHA INICIO"] = pd.to_datetime(row["INICIO"])
                    nueva_fila["FECHA TERMINO"] = pd.to_datetime(row["FIN"])
                    nueva_fila["CARRERA"] = str(row["MATERIA"]).strip().upper()
                    nueva_fila["NOMBRE SECCIÓN"] = str(row["TITULO"]).strip().upper()
                    nueva_fila["MAX ALUMNOS"] = int(row["CUPOS"])
                    nueva_fila["TIPO DE REUNION"] = str(row["TIPO"]).strip().upper()
                    
                    filas_normalizadas.append(nueva_fila)

    if not filas_normalizadas:
        raise ValueError("No hay bloques horarios procesables.")

    base = pd.DataFrame(filas_normalizadas)
    base["LISTA CRUZADA"] = base["LISTA CRUZADA"].fillna("").astype(str).str.strip().str.upper()
    
    # Identificadores de grupo unificados para listas cruzadas
    base["GRUPO_ID"] = base.index.astype(str)
    mask_cruzada = base["LISTA CRUZADA"] != ""
    if mask_cruzada.any():
        base.loc[mask_cruzada, "GRUPO_ID"] = "CRUZ_" + base.loc[mask_cruzada, "LISTA CRUZADA"] + "_" + base.loc[mask_cruzada, "DIA"] + "_" + base.loc[mask_cruzada, "HORARIO"]

    base["CUPOS_CONSOLIDADOS"] = base.groupby("GRUPO_ID")["MAX ALUMNOS"].transform("sum")

    # RESTRECCIÓN CLAVE: El motor de esta corrida solo opera sobre las carreras del escenario seleccionado
    if lista_carreras:
        base = base[base["CARRERA"].isin([str(c).upper().strip() for c in lista_carreras])]
    if lista_reuniones:
        base = base[base["TIPO DE REUNION"].isin([str(r).upper().strip() for r in lista_reuniones])]

    if base.empty:
        return pd.DataFrame(), {}, pd.DataFrame() # Corrida vacía para este escenario

    # Ordenamiento académico de la cola de procesamiento
    base["PRIORIDAD"] = base["TIPO DE REUNION"].map(lambda r: 1 if r=="HIBR" else (2 if r=="CLAS" else 3))
    base = base.sort_values(by=["POSTGRADO_FLAG", "PRIORIDAD", "CUPOS_CONSOLIDADOS"], ascending=[False, True, False]).reset_index(drop=True)

    base["CAPACIDAD SALA"] = np.nan
    base["% OCUPACION SALA"] = ""
    base["ESTADO"] = "PENDIENTE"
    base["MOTIVO_RECHAZO"] = ""

    # =============================================================================
    # 🛠️ FUNCIONES DE VALIDACIÓN INTERNA
    # =============================================================================
    def edificios_preferidos(carrera):
        if carrera in ["ICA", "ICC", "ICE", "ICI", "ING"]: return ["ING", "CIEN", "HUM"]
        return ["HUM", "REL", "BIB"]

    def sala_disponible_info(sala_nombre, dia, hi, hf, fi, ff):
        if sala_nombre not in ocupacion: return True
        for b in ocupacion[sala_nombre]:
            b_dia, b_hi, b_hf, b_fi, b_ff, _, _, _ = b
            if b_dia == dia:
                # Intersección horaria e intersección de calendario de semanas
                if (hi < b_hf and hf > b_hi) and (fi <= b_ff and ff >= b_fi):
                    return False
        return True

    # =============================================================================
    # 🚀 EJECUCIÓN DEL ESCENARIO (UNA SOLA PASADA ESTRICTA)
    # =============================================================================
    niveles_fase = [1, 2, 3, 4, 5]
    indices_pendientes = base.index.tolist()

    for fase in niveles_fase:
        removidos = set()
        for idx in indices_pendientes:
            if base.loc[idx, "ESTADO"] != "PENDIENTE":
                removidos.add(idx)
                continue

            curso = base.loc[idx]
            carrera = curso["CARRERA"]
            alumnos_grupo = int(curso["CUPOS_CONSOLIDADOS"])
            dia = curso["DIA"]
            inicio = curso["HORA INICIO"]
            fin = curso["HORA TERMINO"]
            fi = curso["FECHA INICIO"]
            ff = curso["FECHA TERMINO"]
            gid = curso["GRUPO_ID"]
            sec = str(curso["NOMBRE SECCIÓN"])

            todas_las_salas = [sala for e in salas_por_edificio for sala in salas_por_edificio[e]]
            mejor_sala = None
            mejor_score = -1e15
            motivos = set()

            for sala in todas_las_salas:
                nombre = sala["SALA"]
                cap = sala["CAPACIDAD"]

                if alumnos_grupo > cap:
                    motivos.add("Capacidad insuficiente")
                    continue

                # CONTROL DEL PARAMETRO CONFIGURADO POR EL USUARIO
                ratio = alumnos_grupo / cap
                if ratio < eficiencia_minima:
                    motivos.add(f"Eficiencia menor al umbral del escenario ({int(eficiencia_minima*100)}%)")
                    continue

                if not sala_disponible_info(nombre, dia, inicio, fin, fi, ff):
                    motivos.add("Espacio reservado en escenario previo / Choque horario")
                    continue

                # Sistema de peso puro de selección
                score = ratio * 600
                if sala["EDIFICIO"] in edificios_preferidos(carrera): score += 300
                
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
                    base.loc[g_idx, "ESTADO"] = f"ASIGNADO ESCENARIO"
                
                nombre_ocupante = f"CRUZADA: {curso['LISTA CRUZADA']}" if gid.startswith("CRUZ_") else f"{carrera}-{sec}"
                ocupacion.setdefault(nombre_sala, []).append((dia, inicio, fin, fi, ff, nombre_ocupante, alumnos_grupo, cap_final))
                removidos.add(idx)
            else:
                if motivos:
                    base.loc[base["GRUPO_ID"] == gid, "MOTIVO_RECHAZO"] = "; ".join(sorted(motivos))

        indices_pendientes = [i for i in indices_pendientes if i not in removidos]

    # Marcar los caídos de esta tanda como SIN SALA
    base.loc[base["ESTADO"] == "PENDIENTE", "ESTADO"] = "SIN SALA"
    
    # Formatear salidas de fechas
    base["INICIO"] = base["FECHA INICIO"].dt.strftime('%d-%m-%Y')
    base["FIN"] = base["FECHA TERMINO"].dt.strftime('%d-%m-%Y')

    # Reconstrucción de la visualización temporal de salas ocupadas
    registros_malla = []
    for sala, bloques in ocupacion.items():
        for b in bloques:
            registros_malla.append({
                "SALA": sala, "DIA": b[0], "HORARIO": f"{b[1].strftime('%H:%M')} - {b[2].strftime('%H:%M')}",
                "INICIO": b[3].strftime('%d-%m-%Y'), "FIN": b[4].strftime('%d-%m-%Y'),
                "CURSO_OCUPANTE": b[5], "CUPOS": b[6], "CAPACIDAD": b[7],
                "EDIFICIO": salas_dict_global[sala]["EDIFICIO"]
            })
    df_malla_consolidada = pd.DataFrame(registros_malla)

    return base, ocupacion, df_malla_consolidada
