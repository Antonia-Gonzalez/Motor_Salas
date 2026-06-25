# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np
import copy

def ejecutar_asignacion_escenario(
    archivo_cursos_excel,
    escenario_id,
    eficiencia_minima=0.75,
    modo_estricto=False,
    modo_lista_cruzada="MAXIMO",
    ocupacion_previa=None,
    solo_postgrado=False,
    solo_pregrado=False,
    lista_carreras=None,
    lista_reuniones=None,
    lista_edificios=None,
    lista_tipos_sala=None,
    lista_formatos=None,
    lista_salas=None
):
    ruta_infraestructura = "infraestructura_constante.xlsx"
    dias_semana = ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES", "SABADO"]
    dias_orden = {d: i for i, d in enumerate(dias_semana, 1)}
    
    try:
        salas_PROV = pd.read_excel(ruta_infraestructura, sheet_name="SALAS")
    except Exception as e:
        raise FileNotFoundError(f"Error crítico: No se puede acceder a '{ruta_infraestructura}'. {e}")

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
            "SALA": s_nombre, "EDIFICIO": str(fila["EDIFICIO"]),
            "CAPACIDAD": int(fila["CAPACIDAD"]), "TIPO DE SALA": str(fila["TIPO DE SALA"]),
            "FORMATO": str(fila["FORMATO"])
        }

    if lista_edificios:
        salas_PROV = salas_PROV[salas_PROV["EDIFICIO"].isin([str(e).upper().strip() for e in lista_edificios])]
    if lista_tipos_sala:
        salas_PROV = salas_PROV[salas_PROV["TIPO DE SALA"].isin([str(t).upper().strip() for t in lista_tipos_sala])]
    if lista_formatos:
        salas_PROV = salas_PROV[salas_PROV["FORMATO"].isin([str(f).upper().strip() for f in lista_formatos])]
    if lista_salas:
        salas_PROV = salas_PROV[salas_PROV["SALA"].isin([str(s).upper().strip() for s in lista_salas])]

    if salas_PROV.empty:
        return (pd.DataFrame(), {}, pd.DataFrame(), {}, pd.DataFrame(), 
                pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame())

    salas_utiles = [salas_dict_global[s] for s in salas_PROV["SALA"].unique()]

    if ocupacion_previa is not None:
        ocupacion = copy.deepcopy(ocupacion_previa)
    else:
        ocupacion = {}

    for sala in salas_dict_global.keys():
        if sala not in ocupacion:
            ocupacion[sala] = {d: [] for d in dias_semana}
        else:
            for d in dias_semana:
                ocupacion[sala][d] = [b for b in ocupacion[sala][d] if b[8] != escenario_id]

    dfs = []
    if not solo_postgrado:
        try:
            df_pre = pd.read_excel(archivo_cursos_excel, sheet_name="BASE PREGRADO")
            df_pre["POSTGRADO_FLAG"] = False
            dfs.append(df_pre)
        except: pass
    if not solo_pregrado:
        try:
            # 🛠️ CORRECCIÓN ERROR 1: Eliminado error tipográfico "POSTDRADO" -> "POSTGRADO"
            df_post = pd.read_excel(archivo_cursos_excel, sheet_name="BASE POSTGRADO")
            df_post["POSTGRADO_FLAG"] = True
            dfs.append(df_post)
        except: pass
            
    if not dfs:
        return (pd.DataFrame(), ocupacion, pd.DataFrame(), {}, pd.DataFrame(), 
                pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
        
    base_raw = pd.concat(dfs, ignore_index=True)
    base_raw["LISTA CRUZADA"] = base_raw["LISTA CRUZADA"].fillna("").astype(str).str.strip().str.upper() if "LISTA CRUZADA" in base_raw.columns else ""

    filas_normalizadas = []
    for idx_original, row in base_raw.iterrows():
        if pd.isna(row["MATERIA"]) or pd.isna(row["CUPOS"]):
            continue
        for dia in dias_semana:
            val_hora = row[dia]
            if pd.notna(val_hora) and str(val_hora).strip() != "":
                partes = str(val_hora).split("-")
                if len(partes) == 2:
                    try:
                        hi = pd.to_datetime(partes[0].strip()).time()
                        hf = pd.to_datetime(partes[1].strip()).time()
                        duracion_hrs = ((hf.hour * 60 + hf.minute) - (hi.hour * 60 + hi.minute)) / 60.0
                    except: continue 
                    
                    nueva_fila = row.to_dict()
                    nueva_fila["ORIGINAL_IDX"] = idx_original
                    nueva_fila["DIA"] = dia
                    nueva_fila["HORARIO"] = f"{hi.strftime('%H:%M')} - {hf.strftime('%H:%M')}"
                    nueva_fila["HORA INICIO"] = hi
                    nueva_fila["HORA TERMINO"] = hf
                    nueva_fila["DURACION_HORAS"] = duracion_hrs
                    nueva_fila["FECHA INICIO"] = pd.to_datetime(row["INICIO"])
                    nueva_fila["FECHA TERMINO"] = pd.to_datetime(row["FIN"])
                    nueva_fila["CARRERA"] = str(row["MATERIA"]).strip().upper()
                    nueva_fila["NOMBRE SECCIÓN"] = str(row["TITULO"]).strip().upper()
                    nueva_fila["MAX ALUMNOS"] = int(row["CUPOS"])
                    nueva_fila["TIPO DE REUNION"] = str(row["TIPO"]).strip().upper()
                    filas_normalizadas.append(nueva_fila)

    if not filas_normalizadas:
        return (pd.DataFrame(), ocupacion, pd.DataFrame(), {}, pd.DataFrame(), 
                pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame())

    base = pd.DataFrame(filas_normalizadas)
    base["GRUPO_ID"] = "CURSO_" + base["ORIGINAL_IDX"].astype(str)
    mask_cruzada = base["LISTA CRUZADA"] != ""
    if mask_cruzada.any():
        base.loc[mask_cruzada, "GRUPO_ID"] = (
            "CRUZ_" + base.loc[mask_cruzada, "LISTA CRUZADA"] + "_" + 
            base.loc[mask_cruzada, "FECHA INICIO"].dt.strftime('%Y%m%d') + "_" +
            base.loc[mask_cruzada, "FECHA TERMINO"].dt.strftime('%Y%m%d')
        )

    df_caps_unicas = base.groupby(["GRUPO_ID", "ORIGINAL_IDX"])["MAX ALUMNOS"].first().reset_index()
    if modo_lista_cruzada == "SUMAR":
        df_cap_grupo = df_caps_unicas.groupby("GRUPO_ID")["MAX ALUMNOS"].sum()
    elif modo_lista_cruzada == "PROMEDIO":
        df_cap_grupo = df_caps_unicas.groupby("GRUPO_ID")["MAX ALUMNOS"].mean().round(0).astype(int)
    else:
        df_cap_grupo = df_caps_unicas.groupby("GRUPO_ID")["MAX ALUMNOS"].max()
        
    base["CUPOS_CONSOLIDADOS"] = base["GRUPO_ID"].map(df_cap_grupo)

    if lista_carreras:
        base = base[base["CARRERA"].isin([str(c).upper().strip() for c in lista_carreras])]
    if lista_reuniones:
        base = base[base["TIPO DE REUNION"].isin([str(r).upper().strip() for r in lista_reuniones])]

    if base.empty:
        return (pd.DataFrame(), ocupacion, pd.DataFrame(), {}, pd.DataFrame(), 
                pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame())

    HORAS_MAX_SEMANAL = 90.0 
    base["PRIORIDAD_NUM"] = base["TIPO DE REUNION"].map(lambda r: 1 if r=="HIBR" else (2 if r=="CLAS" else 3))
    dict_lineas_grupo = {gid: grp for gid, grp in base.groupby("GRUPO_ID")}

    df_grupos_unicos = base.groupby("GRUPO_ID").agg({
        "POSTGRADO_FLAG": "max", "PRIORIDAD_NUM": "min",
        "CUPOS_CONSOLIDADOS": "first", "CARRERA": "first"
    }).reset_index().sort_values(by=["CUPOS_CONSOLIDADOS", "POSTGRADO_FLAG", "PRIORIDAD_NUM"], ascending=[False, False, True]).reset_index(drop=True)

    base["SALA"] = ""
    base["CAPACIDAD SALA"] = np.nan
    base["% OCUPACION SALA"] = ""
    base["ESTADO"] = "PENDIENTE"
    base["MOTIVO_RECHAZO"] = ""
    base["ESCENARIO_ORIGEN"] = escenario_id

    def edificios_preferidos(carrera):
        if carrera in ["ICA", "ICC", "ING"]: return ["ING", "CIEN"]
        if carrera in ["ADM", "DEM"]: return ["REL", "BIB"]
        return ["HUM", "CIEN"]

    def sala_disponible(sala_nombre, dia, hi, hf, fi, ff):
        for b in ocupacion[sala_nombre][dia]:
            if (hi < b[2] and hf > b[1]):
                if not (ff < b[3] or fi > b[4]):
                    return False
        return True

    # ASIGNACIÓN MULTI-FASE
    for _, g_row in df_grupos_unicos.iterrows():
        gid = g_row["GRUPO_ID"]
        carrera = g_row["CARRERA"]
        alumnos_grupo = int(g_row["CUPOS_CONSOLIDADOS"])
        filas_clase = dict_lineas_grupo[gid]
        idx_filas = filas_clase.index
        
        mejor_sala = None
        mejor_score = -1e15
        motivos_sala = set()

        for sala in salas_utiles:
            nombre = sala["SALA"]
            cap = sala["CAPACIDAD"]

            if alumnos_grupo > cap:
                motivos_sala.add("Capacidad insuficiente")
                continue

            ratio = alumnos_grupo / cap
            if ratio < eficiencia_minima:
                motivos_sala.add("Eficiencia menor al optimo")
                continue

            choque_detectado = False
            for _, fila in filas_clase.iterrows():
                if not sala_disponible(nombre, fila["DIA"], fila["HORA INICIO"], fila["HORA TERMINO"], fila["FECHA INICIO"], fila["FECHA TERMINO"]):
                    choque_detectado = True
                    break
            
            if choque_detectado:
                motivos_sala.add("Bloque horario ocupado")
                continue

            score = ratio * 1000
            if sala["EDIFICIO"] in edificios_preferidos(carrera): score += 300

            if score > mejor_score:
                mejor_score = score
                mejor_sala = sala

        if mejor_sala is not None:
            nombre_sala = mejor_sala["SALA"]
            cap_final = mejor_sala["CAPACIDAD"]
            base.loc[idx_filas, "SALA"] = nombre_sala
            base.loc[idx_filas, "CAPACIDAD SALA"] = cap_final
            base.loc[idx_filas, "% OCUPACION SALA"] = f"{(alumnos_grupo / cap_final * 100):.1f}%"
            base.loc[idx_filas, "ESTADO"] = "ASIGNADO"
            
            for _, fila in filas_clase.iterrows():
                nombre_ocupante = f"CRUZADA: {fila['LISTA CRUZADA']}" if gid.startswith("CRUZ_") else f"{carrera}-{fila['NOMBRE SECCIÓN']}"
                ocupacion[nombre_sala][fila["DIA"]].append((
                    fila["DIA"], fila["HORA INICIO"], fila["HORA TERMINO"],
                    fila["FECHA INICIO"], fila["FECHA TERMINO"],
                    nombre_ocupante, alumnos_grupo, cap_final, escenario_id,
                    fila["DURACION_HORAS"], sala["EDIFICIO"], fila["CARRERA"], fila["TIPO DE REUNION"]
                ))
        else:
            base.loc[idx_filas, "ESTADO"] = "SIN SALA"
            if motivos_sala:
                base.loc[idx_filas, "MOTIVO_RECHAZO"] = "; ".join(sorted(motivos_sala))

    # FASE 2: Descompresión de Rezagados
    if not modo_estricto:
        escalones_degradados = [0.75, 0.50, 0.30, 0.10, 0.0]
        escalones_degradados = [nivel for nivel in escalones_degradados if nivel < eficiencia_minima]
        
        gids_sin_sala = base[base["ESTADO"] == "SIN SALA"]["GRUPO_ID"].unique()
        df_grupos_fase2 = df_grupos_unicos[df_grupos_unicos["GRUPO_ID"].isin(gids_sin_sala)]

        for _, g_row in df_grupos_fase2.iterrows():
            gid = g_row["GRUPO_ID"]
            carrera = g_row["CARRERA"]
            alumnos_grupo = int(g_row["CUPOS_CONSOLIDADOS"])
            filas_clase = dict_lineas_grupo[gid]
            idx_filas = filas_clase.index
            mejor_sala = None
            mejor_score = -1e15

            for umbral_activo in escalones_degradados:
                for sala in salas_utiles:
                    nombre = sala["SALA"]
                    cap = sala["CAPACIDAD"]

                    if alumnos_grupo > cap: continue
                    ratio = alumnos_grupo / cap
                    if ratio < umbral_activo: continue

                    choque_detectado = False
                    for _, fila in filas_clase.iterrows():
                        if not sala_disponible(nombre, fila["DIA"], fila["HORA INICIO"], fila["HORA TERMINO"], fila["FECHA INICIO"], fila["FECHA TERMINO"]):
                            choque_detectado = True
                            break
                    
                    if choque_detectado: continue

                    score = ratio * 1000
                    if sala["EDIFICIO"] in edificios_preferidos(carrera): score += 300

                    if score > mejor_score:
                        mejor_score = score
                        mejor_sala = sala
                if mejor_sala is not None: break

            if mejor_sala is not None:
                nombre_sala = mejor_sala["SALA"]
                cap_final = mejor_sala["CAPACIDAD"]
                base.loc[idx_filas, "SALA"] = nombre_sala
                base.loc[idx_filas, "CAPACIDAD SALA"] = cap_final
                base.loc[idx_filas, "% OCUPACION SALA"] = f"{(alumnos_grupo / cap_final * 100):.1f}%"
                base.loc[idx_filas, "ESTADO"] = "ASIGNADO"
                base.loc[idx_filas, "MOTIVO_RECHAZO"] = ""
                
                for _, fila in filas_clase.iterrows():
                    nombre_ocupante = f"CRUZADA: {fila['LISTA CRUZADA']}" if gid.startswith("CRUZ_") else f"{carrera}-{fila['NOMBRE SECCIÓN']}"
                    ocupacion[nombre_sala][fila["DIA"]].append((
                        fila["DIA"], fila["HORA INICIO"], fila["HORA TERMINO"],
                        fila["FECHA INICIO"], fila["FECHA TERMINO"],
                        nombre_ocupante, alumnos_grupo, cap_final, escenario_id,
                        fila["DURACION_HORAS"], sala["EDIFICIO"], fila["CARRERA"], fila["TIPO DE REUNION"]
                    ))

    base["INICIO"] = base["FECHA INICIO"].dt.strftime('%d-%m-%Y')
    base["FIN"] = base["FECHA TERMINO"].dt.strftime('%d-%m-%Y')

    registros_malla = []
    salas_activas_set = set()
    eficiencias_totales = []
    horas_totales_ocupadas = 0.0

    for sala, dias in ocupacion.items():
        for d, bloques in dias.items():
            for b in bloques:
                momento_key = f"{b[0]}_{b[1].strftime('%H:%M')}"
                registros_malla.append({
                    "SALA": sala, "DIA": b[0], "HORA_INICIO": b[1].strftime('%H:%M'),
                    "HORA_INICIO_OBJ": b[1], # 🛠️ CORRECCIÓN ERROR 4: Inyección del objeto time nativo para la app
                    "HORARIO": f"{b[1].strftime('%H:%M')} - {b[2].strftime('%H:%M')}",
                    "CURSO_OCUPANTE": b[5], "CUPOS_REALES": b[6], "CAPACIDAD_SALA": b[7], 
                    "ESCENARIO_ID": b[8], "DURACION_HORAS": b[9], "EDIFICIO": b[10],
                    "CARRERA": b[11], "TIPO_REUNION": b[12], "MOMENTO": momento_key
                })
                salas_activas_set.add(sala)
                horas_totales_ocupadas += b[9]
                eficiencias_totales.append((b[6] / b[7]) * 100)

    df_malla_consolidada = pd.DataFrame(registros_malla)

    metricas_salas_lista = []
    for s_nom, s_inf in salas_dict_global.items():
        h_ocupadas = 0.0
        efs_sala = []
        if s_nom in ocupacion:
            for d in dias_semana:
                for b in ocupacion[s_nom][d]:
                    h_ocupadas += b[9]
                    efs_sala.append((b[6]/b[7])*100)
        
        metricas_salas_lista.append({
            "SALA": s_nom, "EDIFICIO": s_inf["EDIFICIO"], "CAPACIDAD": s_inf["CAPACIDAD"],
            "HORAS_OCUPADAS": round(h_ocupadas, 1), "HORAS_LIBRES": round(max(0.0, HORAS_MAX_SEMANAL - h_ocupadas), 1),
            "EFICIENCIA_PROMEDIO": round(np.mean(efs_sala), 1) if efs_sala else 0.0
        })
    df_metricas_salas = pd.DataFrame(metricas_salas_lista)

    df_metricas_edificios = df_metricas_salas.groupby("EDIFICIO").agg(horas_ocupadas=("HORAS_OCUPADAS", "sum"), conteo_salas=("SALA", "count")).reset_index()
    df_metricas_edificios["% UTILIZACIÓN SEMANAL HORARIA"] = round((df_metricas_edificios["horas_ocupadas"] / (df_metricas_edificios["conteo_salas"] * HORAS_MAX_SEMANAL)) * 100, 1)

    if df_malla_consolidada.empty:
        df_met_carreras = pd.DataFrame(columns=["CARRERA", "HORAS_CONSUMIDAS"])
    else:
        df_met_carreras = df_malla_consolidada.groupby("CARRERA")["DURACION_HORAS"].sum().reset_index().rename(columns={"DURACION_HORAS": "HORAS_CONSUMIDAS"})

    df_demanda_horaria = base.groupby(["DIA", "HORA INICIO"])["GRUPO_ID"].nunique().reset_index()
    df_demanda_horaria.columns = ["DIA", "HORA_INICIO", "BLOQUES_ACTIVOS"]
    df_demanda_horaria["HORA_STR"] = df_demanda_horaria["HORA_INICIO"].apply(lambda x: x.strftime("%H:%M"))
    df_demanda_horaria["MOMENTO_OPERATIVO"] = df_demanda_horaria["DIA"] + " " + df_demanda_horaria["HORA_STR"]
    df_demanda_horaria["DIA_NUM"] = df_demanda_horaria["DIA"].map(dias_orden)
    df_demanda_horaria = df_demanda_horaria.sort_values(by=["DIA_NUM", "HORA_INICIO"]).reset_index(drop=True)

    # GENERACIÓN DE INVENTARIO DISPONIBLE INVERSO
    grilla_maestra_teorica = ["07:30", "08:30", "09:30", "10:30", "11:30", "12:30", "13:30", "14:30", "15:30", "16:30", "17:30", "18:30", "19:30", "20:30"]
    registros_libres = []
    salas_activas_ids = [s["SALA"] for s in salas_utiles]
    
    for s_nom, s_inf in salas_dict_global.items():
        if s_nom not in salas_activas_ids: continue
        for d_inst in dias_semana:
            for i in range(len(grilla_maestra_teorica) - 1):
                h_ini_str = grilla_maestra_teorica[i]
                h_fin_str = grilla_maestra_teorica[i+1]
                hi = pd.to_datetime(h_ini_str).time()
                hf = pd.to_datetime(h_fin_str).time()
                
                # 🛠️ CORRECCIÓN ERROR 3: Removido el cortocircuito erróneo `b[4] < b[3]`. Bloqueo directo y limpio.
                bloque_ocupado = False
                for b in ocupacion[s_nom][d_inst]:
                    if (hi < b[2] and hf > b[1]):
                        bloque_ocupado = True
                        break
                
                if not bloque_ocupado:
                    registros_libres.append({
                        "SALA": s_nom, "EDIFICIO": s_inf["EDIFICIO"], "CAPACIDAD": s_inf["CAPACIDAD"],
                        "DIA": d_inst, "INICIO": h_ini_str, "FIN": h_fin_str,
                        "HORARIO": f"{h_ini_str} - {h_fin_str}", "HORAS_LIBRES": 1.0
                    })
    df_salas_libres = pd.DataFrame(registros_libres).drop_duplicates().reset_index(drop=True)

    df_grupos_estado = base.groupby(["CARRERA", "GRUPO_ID"])["ESTADO"].first().reset_index()
    df_rechazos = df_grupos_estado.groupby("CARRERA").agg(total_cursos=("GRUPO_ID", "nunique"), sin_sala=("ESTADO", lambda x: (x == "SIN SALA").sum())).reset_index()
    df_rechazos["TASA_RECHAZO_PCT"] = round((df_rechazos["sin_sala"] / df_rechazos["total_cursos"]) * 100, 1)

    total_cursos = int(df_grupos_unicos["GRUPO_ID"].nunique())
    cursos_asignados = int(base.loc[base["ESTADO"] == "ASIGNADO", "GRUPO_ID"].nunique())
    cursos_sin_sala = int(base.loc[base["ESTADO"] == "SIN SALA", "GRUPO_ID"].nunique())

    resumen_escenario = {
        "escenario": escenario_id, "eficiencia_target": f"{int(eficiencia_minima * 100)}%",
        "modo": "Estricto" if modo_estricto else "Cascada",
        "asignados": cursos_asignados, "sin_sala": cursos_sin_sala,
        "porcentaje_asignacion": round((cursos_asignados / total_cursos * 100), 1) if total_cursos > 0 else 0.0,
        "eficiencia_promedio_real": round(np.mean(eficiencias_totales), 1) if eficiencias_totales else 0.0,
        "salas_utilizadas": len(salas_activas_set), "horas_ocupadas": round(horas_totales_ocupadas, 1)
    }

    return (base, ocupacion, df_malla_consolidada, resumen_escenario, df_metricas_salas, 
            df_metricas_edificios, df_met_carreras, df_demanda_horaria, df_salas_libres, df_rechazos)
