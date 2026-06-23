# -*- coding: utf-8 -*-
"""
Motor de Asignación Académica - Módulo de Cómputo Central (Optimizado para UDS 201)
"""

import pandas as pd
import datetime
import numpy as np

def ejecutar_asignacion_global(
    archivo_excel,
    solo_postgrado=False,
    solo_pregrado=False,
    ing_solo_ing=False,
    adm_solo_rel=False,
    lista_carreras=None,
    lista_edificios=None,
    lista_tipos_sala=None,
    lista_formatos=None,
    lista_reuniones=None  
):
    base = pd.read_excel(archivo_excel, sheet_name="BASE")
    restricciones = pd.read_excel(archivo_excel, sheet_name="RESTRICCIONES")
    salas = pd.read_excel(archivo_excel, sheet_name="SALAS")
    grupos = pd.read_excel(archivo_excel, sheet_name="GRUPOS")

    columnas_criticas = ["MAX ALUMNOS", "CARRERA", "DIAS", "HORA INICIO", "HORA TERMINO",
                         "FECHA INICIO", "FECHA TERMINO"]
    
    base = base.dropna(subset=columnas_criticas).copy()

    base["FECHA INICIO"] = pd.to_datetime(base["FECHA INICIO"])
    base["FECHA TERMINO"] = pd.to_datetime(base["FECHA TERMINO"])
    base["CARRERA"] = base["CARRERA"].astype(str).str.strip().str.upper()
    base["TIPO DE REUNION"] = base["TIPO DE REUNION"].astype(str).str.strip().str.upper()
    base["TIPO DE REUNION"] = base["TIPO DE REUNION"].replace({"HYBR": "HIBR"})
    base["NOMBRE SECCIÓN"] = base["NOMBRE SECCIÓN"].fillna("").astype(str).str.strip().str.upper()

    salas["TIPO DE SALA"] = salas["TIPO DE SALA"].fillna("").astype(str).str.strip().str.upper()
    salas["FORMATO"] = salas["FORMATO"].fillna("").astype(str).str.strip().str.upper()
    salas["EDIFICIO"] = salas["EDIFICIO"].fillna("").astype(str).str.strip().str.upper()
    salas["SALA"] = salas["SALA"].fillna("").astype(str).str.strip().str.upper()

    if lista_edificios is not None:
        salas = salas[salas["EDIFICIO"].isin(lista_edificios)].copy()
        
    if lista_tipos_sala is not None:
        salas = salas[salas["TIPO DE SALA"].isin(lista_tipos_sala)].copy()
        
    if lista_formatos is not None:
        salas = salas[salas["FORMATO"].isin(lista_formatos)].copy()

    if lista_carreras is not None:
        base = base[base["CARRERA"].isin(lista_carreras)].copy()

    if lista_reuniones is not None:
        base = base[base["TIPO DE REUNION"].isin(lista_reuniones)].copy()

    reuniones_validas = ["AYUD", "CLAS", "HIBR", "PRBA", "EXAM"]
    base = base[base["TIPO DE REUNION"].isin(reuniones_validas)].copy()

    map_dias = {"M":"LUNES","T":"MARTES","W":"MIERCOLES","R":"JUEVES","F":"VIERNES","S":"SABADO","U":"DOMINGO"}
    base["DIAS_STD"] = base["DIAS"].astype(str).str.strip().map(map_dias)

    def limpiar_hora(val):
        if pd.isna(val): return None
        if isinstance(val, datetime.time): return val
        if isinstance(val, datetime.datetime): return val.time()
        try:
            return pd.to_datetime(str(val)).time()
        except:
            return None

    base["HORA INICIO"] = base["HORA INICIO"].apply(limpiar_hora)
    base["HORA TERMINO"] = base["HORA TERMINO"].apply(limpiar_hora)

    def es_postgrado(c):
        return len(c) == 4 and c != "BACH"

    def prioridad_reunion(row):
        r = row["TIPO DE REUNION"]
        if r == "HIBR": return 1
        if r == "CLAS": return 2
        if r in ["EXAM","PRBA"]: return 3
        if r == "AYUD": return 4
        return 5

    base["POSTGRADO_FLAG"] = base["CARRERA"].apply(es_postgrado)

    if solo_postgrado:
        base = base[base["POSTGRADO_FLAG"] == True].copy()

    if solo_pregrado:
        base = base[base["POSTGRADO_FLAG"] == False].copy()

    base["PRIORIDAD"] = base.apply(prioridad_reunion, axis=1)

    base = base.sort_values(
        by=["POSTGRADO_FLAG","PRIORIDAD","MAX ALUMNOS"],
        ascending=[False,True,False]
    ).reset_index(drop=True)

    grupos["GRUPO"] = grupos["GRUPO"].astype(str).str.strip().str.upper()
    grupos["CARRERA"] = grupos["CARRERA"].astype(str).str.strip().str.upper()
    grupo_dict = grupos.groupby("GRUPO")["CARRERA"].apply(list).to_dict()

    restricciones_dict = {}
    for _, fila in restricciones.iterrows():
        s_nom = str(fila["SALA"]).strip().upper()
        restricciones_dict.setdefault(s_nom, []).append({"CARRERA": str(fila["CARRERA"]).strip().upper()})

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

    carreras_ing = {"ICA","ICC","ICE","ICI","ING","INM","IOC"}
    carreras_adm = {"ADM","DEM","DER","EAD","EAI","EAM","ECN","MAD"}
    carreras_salud = {"KIN", "MED", "ENF", "NUT", "ODON"}  # Conjunto de Salud establecido

    def belongs_to_group(carrera, destino):
        if destino == "TODOS": return True
        if destino == "POSTGRADO": return es_postgrado(carrera)
        if destino in grupo_dict: return carrera in grupo_dict[destino]
        return carrera == destino

    def cumple_restriccion_base(carrera, sala_nombre):
        sala_info = salas_dict.get(sala_nombre)
        if not sala_info: return False
        if sala_info["TIPO RESTRICCION"] == "EXCLUSIVO":
            rules = restricciones_dict.get(sala_nombre, [])
            return any(belongs_to_group(carrera, r["CARRERA"]) for r in rules)
        return True

    def edificios_preferidos(carrera):
        if carrera in carreras_ing:
            if ing_solo_ing:
                return ["ING"]
            return ["ING", "CIEN", "REL", "BIB", "HUM"]

        if carrera in carreras_adm:
            if adm_solo_rel:
                return ["REL", "BIB"]
            return ["REL", "BIB", "CIEN", "HUM", "ING"]

        return ["CIEN", "REL", "BIB", "CEN", "HUM", "ING"]

    def edificios_por_fase(carrera, fase):
        base_ed = edificios_preferidos(carrera)
        if fase == 1: return base_ed
        return list(set(base_ed + ["CEN", "HUM", "BIB", "REL", "CIEN", "ING"]))

    def sala_compatible_fase(curso, sala, fase):
        nombre_sala = str(sala.get("SALA_NAME", sala.get("SALA"))).upper()
        
        if nombre_sala in ["DOCT", "DOCTII"]:
            return True

        carrera = curso["CARRERA"]
        reunion = curso["TIPO DE REUNION"]
        tipo_sala = sala["TIPO DE SALA"]
        formato = sala["FORMATO"]
        is_post = es_postgrado(carrera)

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

        if fase in [3, 4]:
            if reunion == "CLAS": return tipo_sala in ["STREAMING", "SALA NORMAL"]
            elif reunion in ["EXAM", "PRBA"]: return tipo_sala == "STREAMING"
            elif reunion == "AYUD": return tipo_sala == "SALA NORMAL"
            elif reunion == "HIBR": return tipo_sala == "HYFLEX"
            return False

        if fase == 5:
            if reunion == "HIBR": return tipo_sala in ["HYFLEX", "STREAMING"]
            if reunion == "CLAS": return tipo_sala in ["STREAMING", "SALA NORMAL", "HYFLEX"]
            if reunion in ["EXAM", "PRBA"]: return True
            if reunion == "AYUD": return tipo_sala in ["SALA NORMAL", "STREAMING"]
            return False

    def prioridad_escasez(curso):
        reunion = curso["TIPO DE REUNION"]
        if reunion == "HIBR": return 100
        if reunion in ["EXAM", "PRBA"]: return 60
        if reunion == "AYUD": return 30
        return 0

    def score_sala(curso, sala):
        alumnos = curso["MAX ALUMNOS"]
        capacidad = sala["CAPACIDAD"]
        carrera = curso["CARRERA"]
        ratio = alumnos / capacidad
        score = ratio * 200

        if sala["EDIFICIO"] in edificios_preferidos(carrera):
            score += 300
        if carrera in carreras_ing:
            score += 5000
        if carrera in carreras_adm:
            score += 4000
        score += prioridad_escasez(curso)
        return score

    ocupacion = {}  
    asignados_por_carrera = {}
    uso_salas = {}

    def ocupar_sala(sala_nombre, dia, hi, hf, fi, ff, curso_desc, alumnos, cap):
        ocupacion.setdefault(sala_nombre, []).append((dia, hi, hf, fi, ff, curso_desc, alumnos, cap))

    def sala_disponible_info(sala_nombre, dia, hi, hf, fi, ff):
        for b in ocupacion.get(sala_nombre, []):
            b_dia, b_hi, b_hf, b_fi, b_ff, _, _, _ = b
            if b_dia == dia:
                horas_solapan = (hi < b_hf and hf > b_hi)
                fechas_solapan = (fi <= b_ff and ff >= b_fi)
                if horas_solapan and fechas_solapan:
                    return False, "Conflicto horario detectado"
        return True, "Disponible"

    base["SALA"] = ""
    base["EDIFICIO"] = ""
    base["ESTADO"] = "PENDIENTE"
    base["MOTIVO_RECHAZO"] = ""

    niveles_fase = [1, 2, 3, 4, 5]
    niveles_eficiencia = [1]

    postgrado_idx = base[base["POSTGRADO_FLAG"] == True].index.tolist()
    pregrado_idx = base[base["POSTGRADO_FLAG"] == False].index.tolist()

    def procesar(indices_subconjunto, es_post):
        no_asignados = indices_subconjunto.copy()

        for fase in niveles_fase:
            for eficiencia in niveles_eficiencia:
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

                    if pd.isna(inicio) or pd.isna(fin) or pd.isna(dia):
                        base.loc[idx, "ESTADO"] = "HORARIO INVALIDO"
                        continue

                    edificios = edificios_por_fase(carrera, fase)
                    salas_candidatas = [sala for e in edificios for sala in salas_por_edificio.get(e, [])]

                    mejor_sala = None
                    mejor_score = -1e15
                    razon_actual = "Sin salas disponibles tras filtros"

                    for sala in salas_candidatas:
                        nombre = sala.get("SALA_NAME", sala.get("SALA"))
                        cap = sala["CAPACIDAD"]
                        nombre_norm = str(nombre).upper().replace(" ", "").replace("-", "")

                        if alumnos > cap:
                            razon_actual = "Capacidad insuficiente"
                            continue
                        if not cumple_restriccion_base(carrera, nombre):
                            razon_actual = "Restricción de carrera"
                            continue
                        if not sala_compatible_fase(curso, sala, fase):
                            razon_actual = f"Incompatibilidad F{fase}"
                            continue

                        disponible, _ = sala_disponible_info(nombre, dia, inicio, fin, fi, ff)
                        if not disponible:
                            razon_actual = "Conflicto horario"
                            continue

                        # 🔴 Restricción EXCLUSIVA absoluta para SIMU KIN
                        if nombre_norm == "SIMUKINE" and carrera != "KIN":
                            razon_actual = "Sala SIMU KIN exclusiva para KIN"
                            continue

                        # 🔒 REGLAS ESTRICTAS DE SEGURIDAD PARA UDS 201
                        if nombre_norm == "UDS201":
                            es_morfo = any(p in sec for p in ["MORF", "MORFO", "ANAT", "MORFOLOGIA"])
                            es_salud = carrera in carreras_salud
                            
                            # A) Si es Postgrado, obligatoriamente debe ser clase de Morfología
                            if es_post and not es_morfo:
                                razon_actual = "UDS 201 reservada en Postgrado solo para clases de Morfología"
                                continue
                                
                            # B) Filtro Radical: Si no es Morfo ni carrera de Salud, se deniega completamente
                            if not (es_morfo or es_salud):
                                razon_actual = "UDS 201 exclusiva para clases de Morfología o carreras de Salud"
                                continue

                        score = score_sala(curso, sala)
                        if es_post:
                            score += 6_000_000
                        else:
                            score -= 300_000

                        # 🎯 JERARQUÍA DE PUNTAJES DINÁMICOS PARA UDS 201 Y SIMUKINE
                        if nombre_norm == "UDS201":
                            es_morfo = any(p in sec for p in ["MORF", "MORFO", "ANAT", "MORFOLOGIA"])
                            if es_morfo:
                                score += 10_000_000  # Prioridad Absoluta N°1 (Le gana a postgrados estándar)
                            else:
                                score += 500_000     # Prioridad N°2 para carreras de salud comunes

                        if nombre_norm == "SIMUKINE" and carrera == "KIN":
                            score += 500_000

                        if score > mejor_score:
                            mejor_score = score
                            mejor_sala = sala

                    if mejor_sala is not None:
                        nombre_sala = mejor_sala.get("SALA_NAME", mejor_sala.get("SALA"))
                        cap_final = mejor_sala["CAPACIDAD"]
                        
                        base.loc[idx, "SALA"] = nombre_sala
                        base.loc[idx, "EDIFICIO"] = mejor_sala["EDIFICIO"]
                        base.loc[idx, "ESTADO"] = f"ASIGNADO F{fase}"
                        
                        ocupar_sala(nombre_sala, dia, inicio, fin, fi, ff, f"{carrera} - {curso['NOMBRE SECCIÓN']}", alumnos, cap_final)
                        
                        asignados_por_carrera[carrera] = asignados_por_carrera.get(carrera, 0) + 1
                        uso_salas[nombre_norm] = uso_salas.get(nombre_norm, 0) + 1
                        removidos.add(idx)
                    else:
                        base.loc[idx, "ESTADO"] = "SIN SALA"
                        base.loc[idx, "MOTIVO_RECHAZO"] = razon_actual

                no_asignados = [i for i in no_asignados if i not in removidos]

    procesar(postgrado_idx, True)
    procesar(pregrado_idx, False)

    base["HORA INICIO"] = base["HORA INICIO"].astype(str)
    base["HORA TERMINO"] = base["HORA TERMINO"].astype(str)
    
    base["FECHA INICIO"] = base["FECHA INICIO"].dt.strftime('%Y-%m-%d')
    base["FECHA TERMINO"] = base["FECHA TERMINO"].dt.strftime('%Y-%m-%d')

    registros = []
    for sala, bloques in ocupacion.items():
        for b in bloques:
            registros.append({
                "SALA": sala,
                "DIA": b[0],
                "HORA_INICIO": str(b[1]),
                "HORA_TERMINO": str(b[2]),
                "FECHA_INICIO": b[3].strftime('%Y-%m-%d') if pd.notnull(b[3]) else "",
                "FECHA_TERMINO": b[4].strftime('%Y-%m-%d') if pd.notnull(b[4]) else "",
                "CURSO_OCUPANTE": b[5],
                "MAX_ALUMNOS": b[6],
                "CAPACIDAD_SALA": b[7]
            })
            
    df_malla = pd.DataFrame(registros)
    if not df_malla.empty:
        df_malla = df_malla.sort_values(by=["SALA", "DIA", "HORA_INICIO"])

    return base, df_malla