import pandas as pd
import numpy as np

def ejecutar_asignacion_escenario(
    archivo_cursos_excel, escenario_id, eficiencia_minima, 
    modo_estricto, modo_lista_cruzada, ocupacion_previa, 
    lista_carreras, lista_edificios=None, lista_salas=None
):
    """
    Motor de asignación optimizado para alta carga de datos.
    Usa diccionarios nativos en lugar de iterrows para evitar la degradación de rendimiento.
    """
    # 1. CARGA RÁPIDA DE INFRAESTRUCTURA
    try:
        df_infra = pd.read_excel("infraestructura_constante.xlsx", sheet_name="SALAS")
    except Exception as e:
        # Fallback en caso de error de lectura
        df_infra = pd.DataFrame(columns=["SALA", "EDIFICIO", "CAPACIDAD", "TIPO_SALA"])
    
    # Estandarización y limpieza vectorizada
    df_infra["EDIFICIO"] = df_infra["EDIFICIO"].fillna("").astype(str).str.strip().str.upper()
    df_infra["SALA"] = df_infra["SALA"].fillna("").astype(str).str.strip().str.upper()
    df_infra["CAPACIDAD"] = df_infra["CAPACIDAD"].fillna(0).astype(int)
    
    # Sincronizar nombres de salas duplicadas
    duplicadas = df_infra[df_infra.duplicated(subset=["SALA"], keep=False)]["SALA"].unique()
    if len(duplicadas) > 0:
        df_infra["SALA"] = df_infra.apply(
            lambda r: f"{r['SALA']} {int(r['CAPACIDAD'])}" if r["SALA"] in duplicadas else r["SALA"], axis=1
        )

    # APLICAR FILTROS DE PLANTA FÍSICA DIRECTAMENTE EN EL FILTRADO VECTORIAL (PODA DE ÁRBOL)
    if lista_edificios:
        lista_edificios_caps = [str(e).strip().upper() for e in lista_edificios]
        df_infra = df_infra[df_infra["EDIFICIO"].isin(lista_edificios_caps)]
    if lista_salas:
        lista_salas_caps = [str(s).strip().upper() for s in lista_salas]
        df_infra = df_infra[df_infra["SALA"].isin(lista_salas_caps)]
        
    # Convertir salas a lista de diccionarios (Velocidad pura)
    salas_universo = df_infra.to_dict("records")

    # 2. CARGA Y FILTRADO DE CURSOS DEMANDANTES
     Hojas_cargar = []
    xl = pd.ExcelFile(archivo_cursos_excel)
    for hoja in ["BASE PREGRADO", "BASE POSTGRADO"]:
        if hoja in xl.sheet_names:
            Hojas_cargar.append(xl.parse(hoja))
            
    if not Hojas_cargar:
        return pd.DataFrame(), {}, pd.DataFrame(), {}, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
        
    df_cursos = pd.concat(Hojas_cargar, ignore_index=True)
    df_cursos["MATERIA"] = df_cursos["MATERIA"].fillna("").astype(str).str.strip().str.upper()
    
    # FILTRO DE MATERIAS SELECCIONADAS
    lista_carreras_caps = [str(c).strip().upper() for c in lista_carreras]
    df_cursos = df_cursos[df_cursos["MATERIA"].isin(lista_carreras_caps)]
    
    if df_cursos.empty:
        return pd.DataFrame(), {}, pd.DataFrame(), {}, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    # Formateo de columnas críticas
    df_cursos["CUPOS"] = df_cursos["CUPOS"].fillna(0).astype(int)
    df_cursos["DIA"] = df_cursos["DIA"].fillna("S/D").astype(str).str.strip().str.upper()
    df_cursos["HORARIO"] = df_cursos["HORARIO"].fillna("S/H").astype(str).str.strip().str.upper()
    df_cursos["TIPO_REUNION"] = df_cursos["TIPO_REUNION"].fillna("TEORICA").astype(str).str.strip().str.upper()
    
    # Convertir cursos a registros nativos
    lista_cursos = df_cursos.to_dict("records")

    # 3. MATRIZ DE OCUPACIÓN TRANSACCIONAL (Usa Hash-Maps en lugar de buscar en DataFrames)
    # Copia profunda de ocupación previa
    matriz_ocupacion = dict(ocupacion_previa) if ocupacion_previa else {}
    
    resultados_asignacion = []
    conteo_asignados = 0
    conteo_rechazados = 0

    # 4. BUCLE PRINCIPAL DE ASIGNACIÓN (OPTIMIZADO)
    for curso in lista_cursos:
        cupos = curso["CUPOS"]
        dia = curso["DIA"]
        horario = curso["HORARIO"]
        materia = curso["MATERIA"]
        tipo_r = curso["TIPO_REUNION"]
        seccion = curso.get("SECCION", "ÚNICA")
        
        sala_asignada = None
        motivo_rechazo = "No se encontraron salas que cumplan con la capacidad requerida"
        
        # PODA: Filtrar salas viables por capacidad antes de validar horarios
        salas_viables = [s for s in salas_universo if s["CAPACIDAD"] >= cupos]
        
        # Ordenar salas por capacidad ascendente (Estrategia Best-Fit para optimizar eficiencia)
        salas_viables = sorted(salas_viables, key=lambda x: x["CAPACIDAD"])
        
        for sala in salas_viables:
            id_sala = sala["SALA"]
            cap_sala = sala["CAPACIDAD"]
            
            # Calcular eficiencia de espacio
            eficiencia = cupos / cap_sala if cap_sala > 0 else 0
            
            if eficiencia < eficiencia_minima:
                if modo_estricto:
                    motivo_rechazo = f"Eficiencia ({int(eficiencia*100)}%) inferior al mínimo exigido ({int(eficiencia_minima*100)}%)"
                    continue # Rechazo directo por modo estricto sin cascada
            
            # Validar colisión de horario en la matriz hash
            llave_tiempo = (id_sala, dia, horario)
            if llave_tiempo in matriz_ocupacion:
                motivo_rechazo = "Conflicto horaria: Sala ocupada en este bloque"
                continue
                
            # ¡Sala Encontrada exitosamente!
            sala_asignada = sala
            break
            
        if sala_asignada:
            # Consolidar en la matriz de ocupación
            matriz_ocupacion[(sala_asignada["SALA"], dia, horario)] = f"{materia}-{seccion}"
            conteo_asignados += 1
            
            resultados_asignacion.append({
                "CARRERA": materia, "NOMBRE SECCIÓN": f"{materia} SECC {seccion}",
                "CUPOS_CONSOLIDADOS": cupos, "DIA": dia, "HORARIO": horario,
                "SALA": sala_asignada["SALA"], "EDIFICIO": sala_asignada["EDIFICIO"],
                "ESTADO": "ASIGNADO", "MOTIVO_RECHAZO": "N/A", "TIPO_REUNION": tipo_r,
                "EFICIENCIA_ESPACIAL": cupos / sala_asignada["CAPACIDAD"] if sala_asignada["CAPACIDAD"] > 0 else 0
            })
        else:
            conteo_rechazados += 1
            resultados_asignacion.append({
                "CARRERA": materia, "NOMBRE SECCIÓN": f"{materia} SECC {seccion}",
                "CUPOS_CONSOLIDADOS": cupos, "DIA": dia, "HORARIO": horario,
                "SALA": "SIN SALA", "EDIFICIO": "NINGUNO",
                "ESTADO": "SIN SALA", "MOTIVO_RECHAZO": motivo_rechazo, "TIPO_REUNION": tipo_r,
                "EFICIENCIA_ESPACIAL": 0.0
            })

    # 5. CONSTRUCCIÓN EFICIENTE DE DATAFRAMES DE SALIDA (A PARTIR DE LISTAS)
    df_res = pd.DataFrame(resultados_asignacion)
    
    # Construcción de DF Malla para Calendarios
    df_malla = df_res[df_res["ESTADO"] == "ASIGNADO"].copy()
    if not df_malla.empty:
        df_malla["HORA_INICIO"] = df_malla["HORARIO"].apply(lambda x: x.split("-")[0].strip() if "-" in x else "08:00")
        df_malla["CURSO_OCUPANTE"] = df_malla["NOMBRE SECCIÓN"]
    else:
        df_malla = pd.DataFrame(columns=["SALA", "HORA_INICIO", "DIA", "CURSO_OCUPANTE", "HORARIO"])

    # Generación de Metadatos del Resumen
    total_cursos = len(lista_cursos)
    pct_asig = round((conteo_asignados / total_cursos) * 100, 1) if total_cursos > 0 else 0
    salas_usadas = int(df_res[df_res["ESTADO"] == "ASIGNADO"]["SALA"].nunique())
    
    resumen_metadata = {
        "escenario": escenario_id, "asignados": conteo_asignados, "rechazados": conteo_rechazados,
        "porcentaje_asignacion": pct_asig, "salas_utilizadas": salas_usadas
    }

    # Métricas de salas
    if not df_res[df_res["ESTADO"] == "ASIGNADO"].empty:
        df_s = df_res[df_res["ESTADO"] == "ASIGNADO"].groupby("SALA").size().reset_index(name="HORAS_OCUPADAS")
        df_e = df_res[df_res["ESTADO"] == "ASIGNADO"].groupby("EDIFICIO").size().reset_index(name="HORAS_OCUPADAS")
        df_e["% UTILIZACIÓN SEMANAL HORARIA"] = (df_e["HORAS_OCUPADAS"] / 50) * 100 # Constante supuesta de 50 horas max.
        df_tip = df_res[df_res["ESTADO"] == "ASIGNADO"].groupby("TIPO_REUNION").size().reset_index(name="HORAS_CONSUMIDAS")
    else:
        df_s, df_e, df_tip = pd.DataFrame(columns=["SALA", "HORAS_OCUPADAS"]), pd.DataFrame(columns=["EDIFICIO", "% UTILIZACIÓN SEMANAL HORARIA"]), pd.DataFrame(columns=["TIPO_REUNION", "HORAS_CONSUMIDAS"])

    # Demanda horaria (Saturación Temporal)
    if not df_res.empty:
        df_dem = df_res.groupby(["DIA", "HORARIO"]).size().reset_index(name="BLOQUES_ACTIVOS")
        df_dem["MOMENTO_OPERATIVO"] = df_dem["DIA"] + " " + df_dem["HORARIO"]
        df_dem["HORA_STR"] = df_dem["HORARIO"]
    else:
        df_dem = pd.DataFrame(columns=["MOMENTO_OPERATIVO", "BLOQUES_ACTIVOS", "DIA", "HORA_STR"])

    # Simulación de Bloques Libres Reales
    lista_libres = []
    bloques_totales = ["08:30-10:00", "10:15-11:45", "12:00-13:30", "14:30-16:00", "16:15-17:45"]
    dias_totales = ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES"]
    
    for sala in salas_universo:
        for d in dias_totales:
            for b in bloques_totales:
                if (sala["SALA"], d, b) not in matriz_ocupacion:
                    lista_libres.append({
                        "SALA": sala["SALA"], "EDIFICIO": sala["EDIFICIO"], 
                        "CAPACIDAD": sala["CAPACIDAD"], "DIA": d, "HORARIO_DISPONIBLE": b, "INICIO": b.split("-")[0]
                    })
    df_lib = pd.DataFrame(lista_libres)

    # Diagnóstico de rechazos por carrera
    if not df_res.empty:
        df_rech = df_res.groupby("CARRERA").agg(
            total_cursos=("ESTADO", "count"),
            sin_sala=("ESTADO", lambda x: (x == "SIN SALA").sum())
        ).reset_index()
        df_rech["TASA_RECHAZO_PCT"] = (df_rech["sin_sala"] / df_rech["total_cursos"]) * 100
    else:
        df_rech = pd.DataFrame(columns=["CARRERA", "TASA_RECHAZO_PCT"])

    return df_res, matriz_ocupacion, df_malla, resumen_metadata, df_s, df_e, pd.DataFrame(), df_tip, df_dem, df_lib, df_rech
