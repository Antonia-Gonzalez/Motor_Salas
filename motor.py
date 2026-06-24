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
    Motor de asignación jerárquica con Fase 0 de Pre-reserva/Bloqueo de salas
    y filtros activos desde la UI de Streamlit.
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

    # Diccionario maestro global (sirve para validar la Fase 0 aunque la sala haya sido filtrada en la UI)
    salas_dict_global = {}
    for _, fila in salas_PROV.iterrows():
        s_nombre = str(fila["SALA"]).strip().upper()
        salas_dict_global[s_nombre] = {
            "SALA": s_nombre,
            "EDIFICIO": str(fila["EDIFICIO"]),
            "CAPACIDAD": int(fila["CAPACIDAD"]),
            "TIPO DE SALA": str(fila["TIPO DE SALA"]),
            "FORMATO": str(fila["FORMATO"]),
            "TIPO RESTRICCION": str(fila.get("TIPO RESTRICCION", "NORMAL")).strip().upper()
        }

    # APLICAR FILTROS DE LA UI A LAS SALAS DISPONIBLES PARA OPTIMIZAR
    if lista_edificios is not None:
        salas_PROV = salas_PROV[salas_PROV["EDIFICIO"].isin(lista_edificios)]
    if lista_tipos_sala is not None:
        salas_PROV = salas_PROV[salas_PROV["TIPO DE SALA"].isin(lista_tipos_sala)]
    if lista_formatos is not None:
        salas_PROV = salas_PROV[salas_PROV["FORMATO"].isin(lista_formatos)]
    if lista_salas is not None:
        salas_PROV = salas_PROV[salas_PROV["SALA"].isin(lista_salas)]

    if salas_PROV.empty:
        raise ValueError("Los filtros de infraestructura redujeron las salas disponibles a cero.")

    # Agrupación de salas útiles para el motor de optimización
    salas_por_edificio = {}
    for _, fila in salas_PROV.iterrows():
        s_nombre = fila["SALA"]
        s_info = salas_dict_global[s_nombre]
        salas_por_edificio.setdefault(s_info["EDIFICIO"], []).append(s_info)

    # =============================================================================
    # [MEJORA 1] OPTIMIZACIÓN: ORDENAR SALAS POR CAPACIDAD ASCENDENTE
    # =============================================================================
    for edificio in salas_por_edificio:
        salas_por_edificio[edificio] = sorted(
            salas_por_edificio[edificio],
            key=lambda x: x["CAPACIDAD"]
        )


    # =============================================================================
    # 2. CARGA Y CONCATENACIÓN DE HOJAS DE CURSOS (PRE / POST)
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
        raise ValueError("No hay datos de cursos para procesar con la combinación de grado elegida.")
        
    base_raw = pd.concat(dfs_a_concatenar, ignore_index=True)


    # =============================================================================
    # 3. PROCESAMIENTO Y TRANSFORMACIÓN PLANA (UNPIVOT DE HORARIOS)
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


    # =============================================================================
    # 4. CRITERIOS DE FILTRADO UI, ORDENAMIENTO Y RESTRICCIONES
    # =============================================================================
    # Aplicar filtros multiselección de la UI a los cursos normalizados
    if lista_carreras is not None:
        base = base[base["CARRERA"].isin(lista_carreras)]
    if lista_reuniones is not None:
        base = base[base["TIPO DE REUNION"].isin(lista_reuniones)]

    if base.empty:
        raise ValueError("Los filtros de carreras/reuniones redujeron la lista de cursos a cero registros.")

    def prioridad_reunion(row):
        r = row["TIPO DE REUNION"]
        if r == "HIBR": return 1
        if r == "CLAS": return 2
        if r in ["EXAM", "PRBA"]: return 3
        if r == "AYUD": return 4
        return 5

    base["PRIORIDAD"] = base.apply(prioridad_reunion, axis=1)
    # [POLÍTICA ORIGINAL CONSERVED] Ordenamos el DataFrame base global
    base = base.sort_values(by=["POSTGRADO_FLAG", "PRIORIDAD", "MAX ALUMNOS"], ascending=[False, True, False]).reset_index(drop=True)

    # Inicialización de columnas finales de control
    base["CAPACIDAD SALA"] = np.nan
    base["% OCUPACION SALA"] = ""
    base["ESTADO"] = "PENDIENTE"
    base["MOTIVO_RECHAZO"] = ""
    
    # Asegurar limpieza de la columna SALA original (peticiones especiales)
    if "SALA" not in base.columns:
        base["SALA"] = ""
    else:
        base["SALA"] = base["SALA"].fillna("").astype(str).str.strip().str.upper()

    # Diccionarios de reglas de negocio heredados
    grupo_dict = {
        "INGENIERIA": ["ICA", "ICC", "ICE", "ICI", "ING", "INM", "IOC"],
        "ADMINISTRACION": ["ADM", "DEM", "DER", "EAD", "EAI", "EAM", "ECN", "MAD"],
        "SALUD": ["KIN", "MED", "ENF", "NUT", "ODON"]
    }

    restricciones_dict = {
        "LAB-ING1": [{"CARRERA": "INGENIERIA"}], 
        "SALA-MED5": [{"CARRERA": "MED"}],       
        "AUDITORIO-A": [{"CARRERA": "TODOS"}]
    }

    carreras_ing = set(grupo_dict["INGENIERIA"])
    carreras_adm = set(grupo_dict["ADMINISTRACION"])


    # =============================================================================
    # 🔒 FASE 0: PROCESAR PETICIONES ESPECIALES (PRE-RESERVAS / BLOQUEOS)
    # =============================================================================
    ocupacion = {}  # Matriz / Diccionario de colisiones horarias

    cursos_preasignados = base[base["SALA"] != ""]

    for idx, curso in cursos_preasignados.iterrows():
        sala_fija = curso["SALA"]
        dia_fijo = curso["DIAS_STD"]
        hi = curso["HORA INICIO"]
        hf = curso["HORA TERMINO"]
        fi = curso["FECHA INICIO"]
        ff = curso["FECHA TERMINO"]
        alumnos = curso["MAX ALUMNOS"]
        carrera = curso["CARRERA"]
        sec = str(curso["NOMBRE SECCIÓN"]).upper()

        # Validamos si la sala escrita por la escuela existe en el maestro de infraestructura
        if sala_fija in salas_dict_global:
            cap_sala = salas_dict_global[sala_fija]["CAPACIDAD"]
            
            base.loc[idx, "CAPACIDAD SALA"] = cap_sala
            base.loc[idx, "% OCUPACION SALA"] = f"{(alumnos / cap_sala * 100):.1f}%"
            base.loc[idx, "ESTADO"] = "ASIGNACIÓN ESPECIAL"
            base.loc[idx, "MOTIVO_RECHAZO"] = "Respetado por petición especial de la escuela"
            
            # 🛡️ BLOQUEO EFECTIVO EN LA MATRIZ: Añadir a ocupación para que la Fase 1 lo esquive
            ocupacion.setdefault(sala_fija, []).append(
                (dia_fijo, hi, hf, fi, ff, f"{carrera} - {sec}", alumnos, cap_sala)
            )
        else:
            # Si la escuela cometió una errata al escribir el código de la sala
            base.loc[idx, "SALA"] = ""
            base.loc[idx, "ESTADO"] = "ERROR_PREASIGNACION"
            base.loc[idx, "MOTIVO_RECHAZO"] = f"La sala asignada manual '{sala_fija}' no existe en infraestructura_constante.xlsx."


    # =============================================================================
    # 🛠️ FUNCIONES AUXILIARES DEL MOTOR INTERNO
    # =============================================================================
    def edificios_preferidos(carrera):
        if carrera in carreras_ing: return ["ING", "CIEN", "REL", "BIB", "HUM"]
        if carrera in carreras_adm: return ["REL", "BIB", "CIEN", "HUM", "ING"]
        return ["CIEN", "REL", "BIB", "CEN", "HUM", "ING"]

    def edificios_por_fase(carrera, fase):
        base_ed = edificios_preferidos(carrera)
        if fase == 1: return base_ed
        return list(set(base_ed + ["CEN", "HUM", "BIB", "REL", "CIEN", "ING"]))

    def sala_compatible_fase(curso, sala, fase):
        nombre_sala = str(sala["SALA"]).upper()
        if nombre_sala in ["DOCT", "DOCTII"]: return True

        carrera = curso["CARRERA"]
        reunion = curso["TIPO DE REUNION"]
        tipo_sala = sala["TIPO DE SALA"]
        formato = sala["FORMATO"]
        is_post = curso["POSTGRADO_FLAG"]

        if fase in [1, 2]:
            if is_post:
                if reunion == "HIBR" and not (tipo_sala == "HYFLEX" or formato == "AUDITORIO"): return False
                if reunion == "CLAS" and not (tipo_sala == "STREAMING" or sala["EDIFICIO"] == "REL"): return False
                if reunion in ["EXAM", "PRBA"] and not (formato == "PLANA" or tipo_sala == "STREAMING"): return False
                if reunion == "AYUD" and not (tipo_sala == "SALA NORMAL"): return False
            else:
                if reunion == "CLAS" and not (tipo_sala in ["STREAMING", "SALA NORMAL"]): return False
                if reunion in ["EXAM", "PRBA"] and not (formato == "PLANA" or tipo_sala == "STREAMING"): return False
                if reunion == "AYUD" and not (tipo_sala == "SALA NORMAL"): return False
        return True

    def belongs_to_group(carrera, destino):
        if destino == "TODOS": return True
        if destino == "POSTGRADO": return len(carrera) == 4 and carrera != "BACH"
        if destino in grupo_dict: return carrera in grupo_dict[destino]
        return carrera == destino

    def cumple_restriccion_base(carrera, sala_nombre):
        sala_info = salas_dict_global.get(sala_nombre)
        if not sala_info: return False
        if sala_info["TIPO RESTRICCION"] == "EXCLUSIVO":
            rules = restricciones_dict.get(sala_nombre, [])
            return any(belongs_to_group(carrera, r["CARRERA"]) for r in rules)
        return True

    # [MEJORA 3] BÚSQUEDA DE CONFLICTOS OPTIMIZADA O(1) ANTES DEL BUCLE
    def sala_disponible_info(sala_nombre, dia, hi, hf, fi, ff):
        if sala_nombre not in ocupacion:
            return True

        for b in ocupacion[sala_nombre]:
            b_dia, b_hi, b_hf, b_fi, b_ff, _, _, _ = b
            if b_dia == dia:
                if (hi < b_hf and hf > b_hi) and (fi <= b_ff and ff >= b_fi):
                    return False
        return True


    # =============================================================================
    # 🚀 FASE 1: OPTIMIZACIÓN DE CURSOS ORDINARIOS (PENDIENTES)
    # =============================================================================
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
                    
                    # [MEJORA 2] USO DE SET PARA ACUMULAR MOTIVOS DE RECHAZO REALES
                    motivos = set()

                    for sala in salas_candidatas:
                        nombre = sala["SALA"]
                        cap = sala["CAPACIDAD"]

                        if alumnos > cap:
                            motivos.add("Capacidad insuficiente")
                            continue

                        ratio = alumnos / cap
                        if ratio < umbral:
                            motivos.add(f"Eficiencia menor al {int(umbral*100)}%")
                            continue

                        if not cumple_restriccion_base(carrera, nombre):
                            motivos.add("Restricción de carrera")
                            continue

                        if not sala_compatible_fase(curso, sala, fase):
                            motivos.add("Tipo de sala incompatible")
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
                        
                        base.loc[idx, "SALA"] = nombre_sala
                        base.loc[idx, "CAPACIDAD SALA"] = cap_final
                        base.loc[idx, "% OCUPACION SALA"] = f"{(alumnos / cap_final * 100):.1f}%"
                        base.loc[idx, "ESTADO"] = f"ASIGNADO F{fase}"
                        base.loc[idx, "MOTIVO_RECHAZO"] = ""
                        
                        ocupacion.setdefault(nombre_sala, []).append(
                            (dia, inicio, fin, fi, ff, f"{carrera} - {sec}", alumnos, cap_final)
                        )
                        removidos.add(idx)
                    else:
                        # Si pasa por todos los intentos de fases y umbrales sin éxito
                        if base.loc[idx, "ESTADO"] == "PENDIENTE":
                            base.loc[idx, "ESTADO"] = "SIN SALA"
                            
                            # [MEJORA 2] Muestra una auditoría limpia separada por comas y ordenada
                            if len(motivos) > 0:
                                base.loc[idx, "MOTIVO_RECHAZO"] = "; ".join(sorted(motivos))
                            else:
                                base.loc[idx, "MOTIVO_RECHAZO"] = "No se encontró sala compatible"

                no_asignados = [i for i in no_asignados if i not in removidos]

    # SEPARAMOS LOS ÍNDICES EXCLUSIVAMENTE DE AQUELLOS QUE COMPITEN (ESTADO == PENDIENTE)
    postgrado_idx = base[(base["POSTGRADO_FLAG"] == True) & (base["ESTADO"] == "PENDIENTE")].index.tolist()
    pregrado_idx = base[(base["POSTGRADO_FLAG"] == False) & (base["ESTADO"] == "PENDIENTE")].index.tolist()

    procesar_bloques(postgrado_idx, True)
    procesar_bloques(pregrado_idx, False)


    # =============================================================================
    # 6. CONSTRUCCIÓN DE REPORTES FINALES DE AUDITORÍA
    # =============================================================================
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
                "INICIO": b[3].strftime('%d-%m-%Y'), 
                "FIN": b[4].strftime('%d-%m-%Y'),    
                "CURSO_OCUPANTE": b[5],
                "CUPOS_ALUMNOS": alums,
                "CAPACIDAD SALA": cap,
                "% OCUPACION SALA": f"{pct:.1f}%"
            })
            
    df_malla = pd.DataFrame(registros_malla)
    if not df_malla.empty:
        df_malla = df_malla.sort_values(by=["SALA", "DIA", "HORARIO"]).reset_index(drop=True)

    return base_entrega, df_malla
