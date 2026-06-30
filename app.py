import streamlit as st
import pandas as pd
import io
import os
import numpy as np
import plotly.express as px

from motor import ejecutar_asignacion_escenario

st.set_page_config(layout="wide", page_title="🏛️ Sistema de Planificación", page_icon="🏛️")
st.title("🏛️ Sistema de Asignación de Salas UAndes")

# Inicialización del estado de la sesión
if "escenario" not in st.session_state:
    st.session_state["escenario"] = {
        "corridas_historicas": [],      
        "ocupacion_consolidada": {},    
        "malla_consolidada": pd.DataFrame(),
        "metricas_infra": pd.DataFrame(),
        "rechazos_consolidados": pd.DataFrame(),
        "filtros_ui": {"materia": [], "edificio": [], "sala": []}
    }

esc_state = st.session_state["escenario"]

def reconstruir_escenario_completo():
    nueva_ocupacion = {}
    mallas_acumuladas = []
    
    if not esc_state["corridas_historicas"]:
        esc_state["ocupacion_consolidada"] = {}
        esc_state["malla_consolidada"] = pd.DataFrame()
        esc_state["metricas_infra"] = pd.DataFrame()
        esc_state["rechazos_consolidados"] = pd.DataFrame()
        return

    # Ejecutar secuencialmente cada tanda inyectada
    for run in esc_state["corridas_historicas"]:
        res_run = ejecutar_asignacion_escenario(
            df_cursos=run["df_cursos"],
            lista_salas_origen=run["salas_infra"],
            relax_level=run["relax"],
            min_eficiencia=run.get("min_eficiencia", 0),
            ocupacion_previa=nueva_ocupacion,
            id_corrida=run["id"]
        )
        nueva_ocupacion = res_run["ocupacion"]
        mallas_acumuladas.append(res_run["malla"])
    
    esc_state["ocupacion_consolidada"] = nueva_ocupacion
    df_temp = pd.concat(mallas_acumuladas, ignore_index=True) if mallas_acumuladas else pd.DataFrame()
    
    # --- CORRECCIÓN CRÍTICA: Homologación y Parseo Seguro de Fechas ---
    if not df_temp.empty:
        col_inicio = next((c for c in ["FECHA INICIO", "FECHA_INICIO"] if c in df_temp.columns), None)
        col_fin = next((c for c in ["FECHA FIN", "FECHA_FIN"] if c in df_temp.columns), None)
        
        if col_inicio and col_fin:
            df_temp["_F_INI_INTERNAL"] = pd.to_datetime(df_temp[col_inicio], errors='coerce')
            df_temp["_F_FIN_INTERNAL"] = pd.to_datetime(df_temp[col_fin], errors='coerce')
        else:
            df_temp["_F_INI_INTERNAL"] = pd.NaT
            df_temp["_F_FIN_INTERNAL"] = pd.NaT
    
    esc_state["malla_consolidada"] = df_temp

    df_sin = df_temp[df_temp["ESTADO"] == "SIN SALA"] if ("ESTADO" in df_temp.columns and not df_temp.empty) else pd.DataFrame()
    esc_state["rechazos_consolidados"] = df_sin.groupby("MATERIA").size().reset_index(name="sin_sala") if (not df_sin.empty and "MATERIA" in df_sin.columns) else pd.DataFrame(columns=["MATERIA", "sin_sala"])

# =========================================================
# CONFIGURACIÓN Y PARÁMETROS INTERACTIVOS (SIDEBAR)
# =========================================================
st.sidebar.header("⚙️ Parámetros de la Asignación")
id_config = st.sidebar.text_input("Identificador de la corrida", value="TANDA-A")

st.sidebar.markdown("**Nivel de Relajación y Criterios:**")
tasa_relax = st.sidebar.select_slider(
    "Seleccione el comportamiento del motor:",
    options=[60, 75, 85, 90, 100],
    value=90,
    format_func=lambda x: {
        100: "100% - Exclusivo (Máxima restricción por Edificio y Tipo)",
        90: "90% - Priorizado (Escape a otros edificios si hay colisión)",
        85: "85% - Libre (Tecnología, tipo y formato de sala 100% abiertos)",
        75: "75% - Flexible (Minimiza distancias de campus)",
        60: "60% - Asignación Total (Ignora preferencias geográficas)"
    }[x]
)

min_eficiencia = st.sidebar.slider("Eficiencia Mínima de Ocupación Sala (%)", min_value=0, max_value=100, value=20, step=5)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ruta_infra = os.path.join(BASE_DIR, "infraestructura_constante.xlsx")

df_infra_raw = pd.DataFrame()
if os.path.exists(ruta_infra):
    df_infra_raw = pd.read_excel(ruta_infra)
    if "TIPO DE SALA" not in df_infra_raw.columns and "TIPO_SALA" in df_infra_raw.columns:
        df_infra_raw = df_infra_raw.rename(columns={"TIPO_SALA": "TIPO DE SALA"})
    salas_seleccionadas_base = df_infra_raw.to_dict("records")
    st.sidebar.success(f"✅ Infraestructura cargada: {len(salas_seleccionadas_base)} salas.")
else:
    st.sidebar.error(f"❌ Falta el archivo crítico de infraestructura.")
    salas_seleccionadas_base = []

# =========================================================
# 📥 CARGA Y CACHEO DE DATOS
# =========================================================
st.markdown("### 📥 1. Cargar Programación Académica")
archivo_mem = st.file_uploader("📂 Subir archivo de 'Programación académica (.xlsx)'", type=["xlsx"])

df_cursos_prefiltrados = pd.DataFrame()
salas_prefiltradas = salas_seleccionadas_base

# =========================================================
# 🔍 FILTROS PERSISTENTES ULTRA-VELOCES
# =========================================================
st.sidebar.markdown("---")
st.sidebar.header("Filtros de asignación")

if archivo_mem:
    try:
        if "df_total_cursos_cache" not in st.session_state:
            excel_inspeccion = pd.ExcelFile(archivo_mem)
            dfs_hojas = []
            if "BASE PREGRADO" in excel_inspeccion.sheet_names:
                df_p = pd.read_excel(excel_inspeccion, sheet_name="BASE PREGRADO")
                df_p["ORIGEN_BASE"] = "PREGRADO"
                dfs_hojas.append(df_p)
            if "BASE POSTGRADO" in excel_inspeccion.sheet_names:
                df_g = pd.read_excel(excel_inspeccion, sheet_name="BASE POSTGRADO")
                df_g["ORIGEN_BASE"] = "POSTGRADO"
                dfs_hojas.append(df_g)
            st.session_state["df_total_cursos_cache"] = pd.concat(dfs_hojas, ignore_index=True) if dfs_hojas else pd.DataFrame()

        df_total_cursos = st.session_state["df_total_cursos_cache"]
        
        if not df_total_cursos.empty:
            materias_disponibles = sorted(df_total_cursos["MATERIA"].dropna().unique())
            edificios_disponibles = sorted(df_infra_raw["EDIFICIO"].dropna().unique()) if not df_infra_raw.empty else []
            salas_disponibles = sorted(df_infra_raw["SALA"].dropna().unique()) if not df_infra_raw.empty else []
            
            all_materias = st.sidebar.checkbox("Seleccionar todas las Materias", value=True)
            f_mat = [] if all_materias else st.sidebar.multiselect("Filtrar por Materia:", materias_disponibles, default=esc_state["filtros_ui"]["materia"])
            
            all_edificios = st.sidebar.checkbox("Seleccionar todos los Edificios", value=True)
            f_edif = [] if all_edificios else st.sidebar.multiselect("Limitar a Edificios:", edificios_disponibles, default=esc_state["filtros_ui"]["edificio"])
            
            all_salas = st.sidebar.checkbox("Seleccionar todas las Salas", value=True)
            f_sala = [] if all_salas else st.sidebar.multiselect("Limitar a Salas:", salas_disponibles, default=esc_state["filtros_ui"]["sala"])
            
            esc_state["filtros_ui"]["materia"] = f_mat
            esc_state["filtros_ui"]["edificio"] = f_edif
            esc_state["filtros_ui"]["sala"] = f_sala
            
            df_cursos_prefiltrados = df_total_cursos.copy()
            if not all_materias and f_mat: 
                df_cursos_prefiltrados = df_cursos_prefiltrados[df_cursos_prefiltrados["MATERIA"].isin(f_mat)]
            
            df_infra_filtrada = df_infra_raw.copy()
            if not all_edificios and f_edif: df_infra_filtrada = df_infra_filtrada[df_infra_filtrada["EDIFICIO"].isin(f_edif)]
            if not all_salas and f_sala: df_infra_filtrada = df_infra_filtrada[df_infra_filtrada["SALA"].isin(f_sala)]
            
            salas_prefiltradas = df_infra_filtrada.to_dict("records")
            st.info(f"📊 **Bloque activo prefiltrado:** {len(df_cursos_prefiltrados)} registros listos para la asignación.")
    except Exception as e:
        st.error(f"Error optimizando filtros: {e}")
else:
    if "df_total_cursos_cache" in st.session_state:
        del st.session_state["df_total_cursos_cache"]
    st.sidebar.info("ℹ️ Sube un archivo para inicializar los universos de control.")

# =========================================================
# 🚀 PROCESAR E INYECTAR
# =========================================================
if archivo_mem and not df_cursos_prefiltrados.empty:
    st.markdown("### ⚙️ 2. Procesar condiciones")
    if st.button("🚀 Confirmar e iniciar asignación"):
        if any(r["id"] == id_config for r in esc_state["corridas_historicas"]):
            st.error(f"El ID '{id_config}' ya existe en el escenario.")
        else:
            with st.spinner("Consolidando asignaciones incrementales con control de fechas..."):
                esc_state["corridas_historicas"].append({
                    "id": id_config,
                    "df_cursos": df_cursos_prefiltrados.copy(),
                    "salas_infra": salas_prefiltradas,
                    "relax": tasa_relax,
                    "min_eficiencia": min_eficiencia
                })
                reconstruir_escenario_completo()
                st.success(f"Tanda '{id_config}' consolidada exitosamente.")

if esc_state["corridas_historicas"]:
    st.sidebar.markdown("---")
    st.sidebar.subheader("🗂️ Escenarios")
    for idx, run in enumerate(list(esc_state["corridas_historicas"])):
        col_run_name, col_run_del = st.sidebar.columns([3, 1])
        col_run_name.caption(f"**{run['id']}** ({len(run['df_cursos'])} curs. | {run['relax']}% rel.)")
        if col_run_del.button("🗑️", key=f"del_{run['id']}_{idx}"):
            esc_state["corridas_historicas"].pop(idx)
            reconstruir_escenario_completo()
            st.rerun()

# =========================================================
# Dashboard del Escenario (Resultados y Vistas)
# =========================================================
if not esc_state["malla_consolidada"].empty:
    st.markdown("### 📊 3. Dashboard de Planificación Temporal")
    
    df_malla_completa = esc_state["malla_consolidada"].copy()

    COL_FECHA_INICIO = next((c for c in ["FECHA INICIO", "FECHA_INICIO"] if c in df_malla_completa.columns), None)
    COL_FECHA_FIN = next((c for c in ["FECHA FIN", "FECHA_FIN"] if c in df_malla_completa.columns), None)
    
    st.markdown("#### 📆 Seleccionar Ventana de Tiempo para Auditoría en Pantalla")
    col_v1, col_v2 = st.columns([1, 2])
    
    tipo_ventana = col_v1.selectbox(
        "Ver utilización por:",
        options=["Periodo Completo", "Por Mes", "Por Semana Específica", "Por Día Específico"]
    )
    
    min_date = df_malla_completa["_F_INI_INTERNAL"].min()
    max_date = df_malla_completa["_F_FIN_INTERNAL"].max()
    
    if pd.isna(min_date): min_date = pd.Timestamp("2026-01-01")
    if pd.isna(max_date): max_date = pd.Timestamp("2026-12-31")
    
    df_malla_filtrada_tiempo = df_malla_completa.copy()
    max_bloques_disponibles_en_ventana = 50 

    if tipo_ventana == "Por Mes":
        MESES = {1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
                 7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"}

        # Generar lista de meses válidos basados en el rango real del DataFrame
        meses_disponibles = sorted(list(set(range(int(min_date.month), int(max_date.month) + 1))))
        
        mes_sel = col_v2.selectbox(
            "Seleccione Mes:",
            options=meses_disponibles,
            format_func=lambda x: MESES[x]
        )
        
        # --- CORRECCIÓN: Filtro de traslape correcto por rango de fecha ---
        primer_dia_mes = pd.Timestamp(year=2026, month=mes_sel, day=1)
        ultimo_dia_mes = primer_dia_mes + pd.offsets.MonthEnd(0)
        
        df_malla_filtrada_tiempo = df_malla_completa[
            (df_malla_completa["_F_INI_INTERNAL"] <= ultimo_dia_mes) &
            (df_malla_completa["_F_FIN_INTERNAL"] >= primer_dia_mes)
        ]
        max_bloques_disponibles_en_ventana = 50 * 4.35
        
    elif tipo_ventana == "Por Semana Específica":
        fecha_sem = col_v2.date_input("Seleccione un día de la semana a consultar:", value=min_date.date())
        ts_sem = pd.Timestamp(fecha_sem)
        
        # Filtrar cursos cuya vigencia cruce la semana seleccionada
        df_malla_filtrada_tiempo = df_malla_completa[
            (df_malla_completa["_F_INI_INTERNAL"] <= ts_sem + pd.Timedelta(days=6)) & 
            (df_malla_completa["_F_FIN_INTERNAL"] >= ts_sem)
        ]
        max_bloques_disponibles_en_ventana = 50

    elif tipo_ventana == "Por Día Específico":
        fecha_dia = col_v2.date_input("Seleccione el día exacto:", value=min_date.date())
        ts_dia = pd.Timestamp(fecha_dia)
        nombre_dia_en = ts_dia.day_name().upper()
        dict_dias = {"MONDAY": "LUNES", "TUESDAY": "MARTES", "WEDNESDAY": "MIERCOLES", "THURSDAY": "JUEVES", "FRIDAY": "VIERNES", "SATURDAY": "SABADO"}
        dia_traducido = dict_dias.get(nombre_dia_en, "DOMINGO")
        
        df_malla_filtrada_tiempo = df_malla_completa[
            (df_malla_completa["_F_INI_INTERNAL"] <= ts_dia) & 
            (df_malla_completa["_F_FIN_INTERNAL"] >= ts_dia) &
            (df_malla_completa["DIA"].astype(str).str.upper() == dia_traducido)
        ]
        max_bloques_disponibles_en_ventana = 10 

    # Recálculo de métricas dinámicas
    ult_salas = esc_state["corridas_historicas"][-1]["salas_infra"] if esc_state["corridas_historicas"] else []
    metricas_infra_dinamicas = []
    
    for s in ult_salas:
        if not df_malla_filtrada_tiempo.empty:
            occ = len(df_malla_filtrada_tiempo[(df_malla_filtrada_tiempo["SALA"] == s["SALA"]) & (df_malla_filtrada_tiempo["EDIFICIO"] == s["EDIFICIO"])])
        else:
            occ = 0
        
        utilizacion_pct = round((occ / max(1, max_bloques_disponibles_en_ventana) * 100), 1)
        metricas_infra_dinamicas.append({
            "SALA": s["SALA"], "EDIFICIO": s["EDIFICIO"], "CAPACIDAD": s["CAPACIDAD"], 
            "BLOQUES_OCUPADOS": occ, "% Utilización": min(100.0, utilizacion_pct)
        })
    df_salas_dinamicas = pd.DataFrame(metricas_infra_dinamicas) if metricas_infra_dinamicas else pd.DataFrame()

    # Indicadores Clave en Pantalla
    tot_c = len(df_malla_completa)
    tot_a = sum(df_malla_completa["ESTADO"].isin(["ASIGNADO", "ASIGNADO_MANUAL"]))
    df_asignados_validos = df_malla_completa[df_malla_completa["ESTADO"].isin(["ASIGNADO", "ASIGNADO_MANUAL"])]
    eficiencia_promedio = round(df_asignados_validos["EFICIENCIA_%"].mean(), 1) if not df_asignados_validos.empty else 0.0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Secciones Totales (Periodo)", tot_c)
    col2.metric(f"Asignadas Activas ({tipo_ventana})", len(df_malla_filtrada_tiempo[df_malla_filtrada_tiempo["ESTADO"].isin(["ASIGNADO", "ASIGNADO_MANUAL"])]))
    col3.metric("Eficiencia Ocupación Aula", f"{eficiencia_promedio}%")
    col4.metric("Sin Aula Física (Historial)", tot_c - tot_a, delta_color="inverse")

    # Pestañas principales
    tab_malla, tab_calendario, tab_salas, tab_heatmap, tab_criticos, tab_exportar = st.tabs([
        "📋 Malla Filtrada", "📅 Agenda por Sala (Rango)", "🏫 Utilización de Infraestructura", "🔥 Mapa de Calor", "🚨 Cursos No Asignados", "📥 Descarga del Libro"
    ])

    with tab_malla:
        st.caption(f"Mostrando cursos activos detectados en la ventana: **{tipo_ventana}**")
        st.dataframe(df_malla_filtrada_tiempo, use_container_width=True, hide_index=True)

    with tab_calendario:
        st.subheader("Cronograma de Espacios con Vigencia de Fechas")
        aulas_ocupadas = sorted([str(s) for s in df_malla_filtrada_tiempo["SALA"].unique() if str(s) != "SIN SALA" and pd.notna(s)])
        
        if aulas_ocupadas:
            sala_sel = st.selectbox("Seleccione el espacio físico a auditar:", aulas_ocupadas)
            df_sala_filtrado = df_malla_filtrada_tiempo[df_malla_filtrada_tiempo["SALA"] == sala_sel].copy()
            
            if not df_sala_filtrado.empty:
                # Formatear fechas explícitas para evitar errores visuales
                f_ini_str = df_sala_filtrado["_F_INI_INTERNAL"].dt.strftime("%d/%m") if "_F_INI_INTERNAL" in df_sala_filtrado.columns else ""
                f_fin_str = df_sala_filtrado["_F_FIN_INTERNAL"].dt.strftime("%d/%m") if "_F_FIN_INTERNAL" in df_sala_filtrado.columns else ""
                
                df_sala_filtrado["DISPLAY"] = (
                    df_sala_filtrado["MATERIA"].astype(str) + 
                    " [" + f_ini_str + " al " + f_fin_str + "]" +
                    " (Ef: " + df_sala_filtrado["EFICIENCIA_%"].astype(str) + "%)"
                )
                try:
                    df_pivot = pd.pivot_table(
                        df_sala_filtrado, index="HORARIO", columns="DIA", values="DISPLAY",
                        aggfunc=lambda x: " / \n ".join(sorted(list(map(str, x.unique()))))
                    )
                    dias_ordenados = [d for d in ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES", "SABADO"] if d in df_pivot.columns]
                    df_pivot = df_pivot.reindex(columns=dias_ordenados).sort_index()
                    st.dataframe(df_pivot, use_container_width=True)
                except Exception:
                    st.dataframe(df_sala_filtrado[["DIA", "HORARIO", "DISPLAY"]], use_container_width=True, hide_index=True)
        else:
            st.info("No se registran salas ocupadas en la combinación temporal seleccionada.")

    with tab_salas:
        st.subheader(f"📊 Analíticas de Ocupación Real para: {tipo_ventana}")
        if not df_salas_dinamicas.empty:
            m1, m2 = st.columns(2)
            m1.metric("Promedio de Utilización Campus en esta Ventana", f"{round(df_salas_dinamicas['% Utilización'].mean(), 1)}%")
            max_row = df_salas_dinamicas.loc[df_salas_dinamicas["BLOQUES_OCUPADOS"].idxmax()]
            m2.metric("Aula Más Solicitada", f"{max_row['EDIFICIO']}-{max_row['SALA']}", f"{max_row['% Utilización']}% Uso")
            
            st.bar_chart(df_salas_dinamicas, x="SALA", y="% Utilización", color="EDIFICIO", use_container_width=True)
            st.dataframe(df_salas_dinamicas, use_container_width=True, hide_index=True)

    with tab_heatmap:
        st.subheader("🔥 Mapa de Calor de Ocupación por Edificio y Horario")
        if not df_malla_filtrada_tiempo.empty and "EDIFICIO" in df_malla_filtrada_tiempo.columns:
            df_heat_raw = df_malla_filtrada_tiempo[df_malla_filtrada_tiempo["ESTADO"].isin(["ASIGNADO", "ASIGNADO_MANUAL"]) & (df_malla_filtrada_tiempo["EDIFICIO"] != "N/A")]
            
            if not df_heat_raw.empty:
                df_pivot_heat = pd.crosstab(index=df_heat_raw["HORARIO"], columns=df_heat_raw["EDIFICIO"])
                fig = px.imshow(df_pivot_heat, color_continuous_scale="Reds", aspect="auto", labels=dict(x="Edificio", y="Horario", color="Cursos"))
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Sin asignaciones activas en este periodo de tiempo.")

    with tab_criticos:
        df_sin_sala = df_malla_completa[df_malla_completa["ESTADO"] == "SIN SALA"].copy()
        if not df_sin_sala.empty:
            c_izq, c_der = st.columns([2, 1])
            with c_izq:
                df_sin_sala["INICIO"] = df_sin_sala["_F_INI_INTERNAL"].dt.strftime("%Y-%m-%d").fillna("Sin fecha")
                df_sin_sala["FIN"] = df_sin_sala["_F_FIN_INTERNAL"].dt.strftime("%Y-%m-%d").fillna("Sin fecha")
                columnas_seguras = [col for col in ["MATERIA", "CUPOS", "INICIO", "FIN", "DIA", "HORARIO", "MOTIVO_RECHAZO"] if col in df_sin_sala.columns]
                st.dataframe(df_sin_sala[columnas_seguras], use_container_width=True, hide_index=True)
            with c_der:
                st.markdown("**Frenos de Asignación acumulados**")
                st.dataframe(esc_state["rechazos_consolidados"], use_container_width=True, hide_index=True)
        else:
            st.success("🎉 ¡Excelente! Cero rechazos históricos.")

    with tab_exportar:
        st.subheader("Auditoría de Configuración e Historial")
        df_exportable = df_malla_completa.copy()
        df_exportable = df_exportable.rename(columns={"CAPACIDAD_SALA": "CAPACIDAD DE LA SALA", "EFICIENCIA_%": "% OCUPACIÓN SALA"})
        columnas_ordenadas = [c for c in df_exportable.columns if c not in ["ESTADO", "MOTIVO_RECHAZO", "CORRIDA_ID", "_F_INI_INTERNAL", "_F_FIN_INTERNAL"]]
        df_exportable = df_exportable[columnas_ordenadas]

        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            df_exportable.to_excel(writer, sheet_name="Malla_Asignacion", index=False)
            if not df_salas_dinamicas.empty:
                df_salas_dinamicas.to_excel(writer, sheet_name="Uso_Salas_Analitico", index=False)
            esc_state["rechazos_consolidados"].to_excel(writer, sheet_name="Rechazos_Por_Materia", index=False)
            
        st.download_button(
            label="📥 Descargar Libro de Planificación Certificado (.xlsx)",
            data=excel_buffer.getvalue(),
            file_name="Reporte_Consolidado_UAndes.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

if st.sidebar.button("Limpiar Todo y Reiniciar Sistema"):
    if "df_total_cursos_cache" in st.session_state:
        del st.session_state["df_total_cursos_cache"]
    st.session_state["escenario"] = {
        "corridas_historicas": [], "ocupacion_consolidada": {}, "malla_consolidada": pd.DataFrame(),
        "metricas_infra": pd.DataFrame(), "rechazos_consolidados": pd.DataFrame(),
        "filtros_ui": {"materia": [], "edificio": [], "sala": []}
    }
    st.rerun()
