# -*- coding: utf-8 -*-
"""
Motor de Asignación Académica - Infraestructura 100% en Código (Solo lee SALAS de Excel)
"""

import pandas as pd
import datetime
import numpy as np

def ejecutar_asignacion_global(archivo_cursos_excel):
    # =============================================================================
    # 1. CARGA DE INFRAESTRUCTURA CONSTANTE (¡Solo la pestaña SALAS!)
    # =============================================================================
    ruta_infraestructura = "infraestructura_constante.xlsx" 
    try:
        # Ahora solo leemos la pestaña de SALAS. Ya no se necesitan RESTRICCIONES ni GRUPOS en Excel.
        salas = pd.read_excel(ruta_infraestructura, sheet_name="SALAS")
    except Exception as e:
        raise FileNotFoundError(f"No se encontró el archivo maestro '{ruta_infraestructura}' o falta la pestaña SALAS. Error: {e}")

    # =============================================================================
    # 2. CARGA Y CONCATENACIÓN DE HOJAS DE CURSOS
    # =============================================================================
    df_pre = pd.read_excel(archivo_cursos_excel, sheet_name="BASE PREGRADO")
    df_pre["POSTGRADO_FLAG"] = False

    df_post = pd.read_excel(archivo_cursos_excel, sheet_name="BASE POSTGRADO")
    df_post["POSTGRADO_FLAG"] = True

    base_raw = pd.concat([df_pre, df_post], ignore_index=True)

    # =============================================================================
    # 3. PROCESAMIENTO Y TRANSFORMACIÓN PLANA (UNPIVOT)
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
        raise ValueError("No se encontraron bloques de horarios válidos en las columnas de LUNES a SABADO.")

    base = pd.DataFrame(filas_normalizadas)

    salas["TIPO DE SALA"] = salas["TIPO DE SALA"].fillna("").astype(str).str.strip().str.upper()
    salas["FORMATO"] = salas["FORMATO"].fillna("").astype(str).str.strip().str.upper()
    salas["EDIFICIO"] = salas["EDIFICIO"].fillna("").astype(str).str.strip().str.upper()
    salas["SALA"] = salas["SALA"].fillna("").astype(str).str.strip().str.upper()

    # =============================================================================
    # 4. CRITERIOS DE ORDENAMIENTO Y RESTRICCIONES INTERNAS (DEFINIDAS AQUÍ)
    # =============================================================================
    def prioridad_reunion(row):
        r = row["TIPO DE REUNION"]
        if r == "HIBR": return 1
        if r == "CLAS": return 2
        if r in ["EXAM", "PRBA"]: return 3
        if r == "AYUD": return 4
        return 5

    base["PRIORIDAD"] = base.apply(prioridad_reunion, axis=1)
    base = base.sort_values(by=["POSTGRADO_FLAG", "PRIORIDAD", "MAX ALUMNOS"], ascending=[False, True, False]).reset_index(drop=True)

    # 🔹 1. AQUÍ DEFINES LOS GRUPOS DIRECTAMENTE EN PYTHON
    grupo_dict = {
        "INGENIERIA": ["ICA", "ICC", "ICE", "ICI", "ING", "INM", "IOC"],
        "ADMINISTRACION": ["ADM", "DEM", "DER", "EAD", "EAI", "EAM", "ECN", "MAD"],
        "SALUD": ["KIN", "MED", "ENF", "NUT", "ODON"]
    }

    # 🔹 2. AQUÍ DEFINES QUÉ SALAS SON EXCLUSIVAS Y PARA QUÉ CARRERA O GRUPO
    # (Solo aplica si la sala en la pestaña SALAS tiene 'TIPO RESTRICCION' = 'EXCLUSIVO')
    restricciones_dict = {
        "LAB-ING1": [{"CARRERA": "INGENIERIA"}], # Usa el grupo de arriba
        "SALA-MED5": [{"CARRERA": "MED"}],       # Usa la carrera directa
        "AUDITORIO-A": [{"CARRERA": "TODOS"}]
    }

    # Mapeo del diccionario de salas tradicionales
    salas_dict = {}
    for _, fila in salas.iterrows():
        s_nombre = str(fila["SALA"]).strip().upper()
        salas_dict[s_nombre] = {
            "SALA": s_nombre,
            "EDIFICIO": str(fila["EDIFICIO"]).strip().upper(),
            "CAPACIDAD": int(fila["CAPACIDAD"]),
            "TIPO DE SALA": str(fila["TIPO DE SALA"]).strip().upper(),
            "FORMATO": str(fila["FORMATO"]).strip().upper(),
            "TIPO RESTRICCION": str(fila.get("TIPO RESTRICCION", "NORMAL")).strip().upper()
        }

    salas_por_edificio = {}
    for s_nombre, s_info in salas_dict.items():
        ed = s_info["EDIFICIO"]
        salas_por_edificio.setdefault(ed, []).append(s_info)

    carreras_ing = set(grupo_dict["INGENIERIA"])
    carreras_adm = set(grupo_dict["ADMINISTRACION"])

    def belongs_to_group(carrera, destino):
        if destino == "TODOS": return True
        if destino == "POSTGRADO": return len(carrera) == 4 and carrera != "BACH"
        if destino in grupo_dict: return carrera in grupo_dict[destino]
        return carrera == destino

    def cumple_restriccion_base(carrera, sala_nombre):
        sala_info = salas_dict.get(sala_nombre)
        if not sala_info: return False
        if sala_info["TIPO RESTRICCION"] == "EXCLUSIVO":
            rules = restricciones_dict.get(sala_nombre, [])
            return any(belongs_to_group(carrera, r["CARRERA"]) for r in rules)
        return True

# =============================================================================
    # 5. CORE ENGINE: PROCESAMIENTO Y RESOLUCIÓN DE COLISIONES
    # =============================================================================
    ocupacion = {}  

    def sala_disponible_info(sala_nombre, dia, hi, hf, fi, ff):
        for b in ocupacion.get(sala_nombre, []):
            b_dia, b_hi, b_hf, b_fi, b_ff, _, _, _ = b
            if b_dia == dia:
                if (hi < b_hf and hf > b_hi) and (fi <= b_ff and ff >= b_fi):
                    return False
        return True

    base["SALA"] = ""
    base["CAPACIDAD SALA"] = np.nan
    base["% OCUPACION SALA"] = ""
    base["ESTADO"] = "PENDIENTE"
    base["MOTIVO_RECHAZO"] = ""

    niveles_fase = [1, 2, 3, 4, 5]
    umbrales_eficiencia = [0.75, 0.50, 0.25, 0.0]

    def procesar_bloques(indices_subconjunto, es_post):
        no_asignados = indices_subconjunto.copy()

        for fase in niveles_fase:
            for umbral in umbrales_eficiencia:
                removidos = set()

                for idx in no_asignados:
                    curso = base.loc[idx]
                    carrera = curso["CARRERA"]
                    alumnos = curso["MAX ALUMNOS"]
                    dia = curso["DIAS_STD"]
                    inicio = curso["HORA INICIO"]
                    fin = curso["HORA TERMINO"]
                    fi = curso["FECHA INICIO"]
                    ff = curso["FECHA TERMINO"]
                    sec = str(curso["NOMBRE SECCIÓN"]).upper()

                    edificios = edificios_por_fase(carrera, fase)
                    salas_candidatas = [sala for e in edificios for sala in salas_por_edificio.get(e, [])]

                    mejor_sala = None
                    mejor_score = -1e15
                    razon_actual = "Sin salas disponibles tras filtros"

                    for sala in salas_candidatas:
                        nombre = sala["SALA"]
                        cap = sala["CAPACIDAD"]

                        if alumnos > cap:
                            razon_actual = "Capacidad insuficiente"
                            continue

                        ratio = alumnos / cap
                        if ratio < umbral:
                            razon_actual = f"Eficiencia baja para corte del {int(umbral*100)}%"
                            continue

                        if not cumple_restriccion_base(carrera, nombre):
                            razon_actual = "Restricción de carrera"
                            continue

                        if not sala_compatible_fase(curso, sala, fase):
                            razon_actual = "Incompatibilidad técnica"
                            continue

                        if not sala_disponible_info(nombre, dia, inicio, fin, fi, ff):
                            razon_actual = "Conflicto horario"
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
                        
                        base.loc[idx, "SALA"] = nombre_sala
                        base.loc[idx, "CAPACIDAD SALA"] = cap_final
                        base.loc[idx, "% OCUPACION SALA"] = f"{(alumnos / cap_final * 100):.1f}%"
                        base.loc[idx, "ESTADO"] = f"ASIGNADO F{fase}"
                        
                        ocupacion.setdefault(nombre_sala, []).append(
                            (dia, inicio, fin, fi, ff, f"{carrera} - {sec}", alumnos, cap_final)
                        )
                        removidos.add(idx)
                    else:
                        base.loc[idx, "ESTADO"] = "SIN SALA"
                        base.loc[idx, "MOTIVO_RECHAZO"] = razon_actual

                no_asignados = [i for i in no_asignados if i not in removidos]

    postgrado_idx = base[base["POSTGRADO_FLAG"] == True].index.tolist()
    pregrado_idx = base[base["POSTGRADO_FLAG"] == False].index.tolist()

    procesar_bloques(postgrado_idx, True)
    procesar_bloques(pregrado_idx, False)

    # =============================================================================
    # 6. CONSTRUCCIÓN DE REPORTES FINALES (FORMATEO DE FECHAS DD-MM-AAAA)
    # =============================================================================
    
    # 🔹 Formateo limpio de fechas a formato DD-MM-AAAA en el dataframe de cursos
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
    base_entrega = base[columnas_entrega].copy()

    # Reporte 2: Malla de Ocupación con fechas homologadas en DD-MM-AAAA
    registros_malla = []
    for sala, bloques in ocupacion.items():
        for b in bloques:
            alums = b[6]
            cap = b[7]
            pct = (alums / cap * 100) if cap > 0 else 0
            registros_malla.append({
                "SALA": sala,
                "DIA": b[0],
                "HORARIO": f"{b[1].strftime('%H:%M')} - {b[2].strftime('%H:%M')}",
                "INICIO": b[3].strftime('%d-%m-%Y'), # 🔹 DD-MM-AAAA aquí también
                "FIN": b[4].strftime('%d-%m-%Y'),    # 🔹 DD-MM-AAAA aquí también
                "CURSO_OCUPANTE": b[5],
                "CUPOS_ALUMNOS": alums,
                "CAPACIDAD SALA": cap,
                "% OCUPACION SALA": f"{pct:.1f}%"
            })
            
    df_malla = pd.DataFrame(registros_malla)
    if not df_malla.empty:
        df_malla = df_malla.sort_values(by=["SALA", "DIA", "HORARIO"])

    return base_entrega, df_malla
