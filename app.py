# app.py
import streamlit as st
import pandas as pd
import io
import os

# Importación unificada del cerebro lógico
from motor import ejecutar_asignacion_escenario

st.set_page_config(layout="wide", page_title="🏛️ Sistema de Planificación", page_icon="🏛️")
st.title("🏛️ Sistema de Asignación de Salas UAndes")

if "planificacion" not in st.session_state:
    st.session_state["planificacion"] = None

# =========================================================
# CONFIGURACIÓN Y PARÁMETROS INTERACTIVOS (SIDEBAR)
# =========================================================
st.sidebar.header("⚙️ Parámetros de la asignación")
id_config = st.sidebar.text_input("ID de Planificación", value="ESC-2026")

tasa_relax = st.sidebar.slider("Nivel de Relajación de Reglas (%)", min_value=60, max_value=100, value=90, step=5)
st.sidebar.caption("💡 100%: Filtro estricto de cercanía. 60%: Permite ubicar en cualquier edificio secundario disponible.")

# --- CARGA AUTOMÁTICA DE INFRAESTRUCTURA ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ruta_infra = os.path.join(BASE_DIR, "infraestructura_constante.xlsx")

df_infra_raw = pd.DataFrame()

if os.path.exists(ruta_infra):
    df_infra_raw = pd.read_excel(ruta_infra)
    if "TIPO DE SALA" not in df_infra_raw.columns and "TIPO_SALA" in df_infra_raw.columns:
        df_infra_raw = df_infra_raw.rename(columns={"TIPO_SALA": "TIPO DE SALA"})
    
    salas_seleccionadas_base = df_infra_raw.to_dict("records")
    st.sidebar.success(f"✅ {len(salas_seleccionadas_base)} salas base disponibles.")
else:
    st.sidebar.error(f"❌ Falta el archivo crítico de infraestructura.")
    salas_seleccionadas_base = []

# =========================================================
# 📥 PASO 1: SUBIR EL ARCHIVO (Para poder leer los universos de filtros)
# =========================================================
st.markdown("### 📥 1. Cargar Programación Académica")
archivo_mem = st.file_uploader("📂 Subir archivo de 'Programación académica (.xlsx)'", type=["xlsx"])

# Inicializamos variables de control
df_cursos_prefiltrados = pd.DataFrame()
salas_prefiltradas = salas_seleccionadas_base

# =========================================================
# 🔍 PASO 2: FILTROS DINÁMICOS DE ENTRADA (PRE-ASIGNACIÓN)
# =========================================================
st.sidebar.markdown("---")
st.sidebar.header("Filtros para la asignación de salas")
st.sidebar.caption("Selecciona aquí para limitar qué cursos y salas entrarán al motor de asignación.")

filtro_carrera = []
filtro_edificio = []
filtro_sala = []

# Si el usuario ya subió el archivo, leemos las carreras reales ANTES de procesar
if archivo_mem:
    try:
        # Inspección rápida en memoria de las hojas del Excel
        excel_inspeccion = pd.ExcelFile(archivo_mem)
        dfs_hojas = []
        if "BASE PREGRADO" in excel_inspeccion.sheet_names:
            dfs_hojas.append(pd.read_excel(excel_inspeccion, sheet_name="BASE PREGRADO"))
        if "BASE POSTGRADO" in excel_inspeccion.sheet_names:
            dfs_hojas.append(pd.read_excel(excel_inspeccion, sheet_name="BASE POSTGRADO"))
        
        if dfs_hojas:
            df_cursos_prefiltrados = pd.concat(dfs_hojas, ignore_index=True)
            
            # Extraer universos únicos de Entrada
            carreras_disponibles = sorted(df_cursos_prefiltrados["MATERIA"].dropna().unique()) if "MATERIA" in df_cursos_prefiltrados.columns else []
            edificios_disponibles = sorted(df_infra_raw["EDIFICIO"].dropna().unique()) if "EDIFICIO" in df_infra_raw.columns else []
            salas_disponibles = sorted(df_infra_raw["SALA"].dropna().unique()) if "SALA" in df_infra_raw.columns else []
            
            # Renderizar los selectores multiselect en el sidebar
            filtro_carrera = st.sidebar.multiselect("Filtrar por Materia (Ej: ICA, ICI):", carreras_disponibles)
            filtro_edificio = st.sidebar.multiselect("Limitar a Edificios:", edificios_disponibles)
            filtro_sala = st.sidebar.multiselect("Limitar a Salas Específicas:", salas_disponibles)
            
            # --- APLICACIÓN EN CALIENTE DEL FILTRO ANTES DE EJECUTAR ---
            if filtro_carrera:
                df_cursos_prefiltrados = df_cursos_prefiltrados[df_cursos_prefiltrados["MATERIA"].isin(filtro_carrera)]
            
            # Filtrar la infraestructura que se le enviará al motor
            df_infra_filtrada = df_infra_raw.copy()
            if filtro_edificio:
                df_infra_filtrada = df_infra_filtrada[df_infra_filtrada["EDIFICIO"].isin(filtro_edificio)]
            if filtro_sala:
                df_infra_filtrada = df_infra_filtrada[df_infra_filtrada["SALA"].isin(filtro_sala)]
                
            salas_prefiltradas = df_infra_filtrada.to_dict("records")
            
            # Mostrar al usuario cuántos datos pasarán el colador
            st.info(f"📊 **Filtro activo de entrada:** Se enviarán al motor **{len(df_cursos_prefiltrados)} secciones** y **{len(salas_prefiltradas)} salas** físicas.")
    except Exception as e:
        st.error(f"Error leyendo el archivo para filtros: {e}")
else:
    st.sidebar.info("ℹ️ Sube un archivo de cursos para activar los filtros previos.")

# =========================================================
# 🚀 PASO 3: EJECUCIÓN DEL MOTOR SOBRE LOS DATOS FILTRADOS
# =========================================================
if archivo_mem and not df_cursos_prefiltrados.empty:
    st.markdown("### ⚙️ 2. Ejecutar asignación")
    if st.button("🚀 Inicializar Asignación de Salas (Solo Selección)"):
        with st.spinner("Procesando exclusivamente los cursos y espacios seleccionados..."):
            try:
                # Creamos un archivo Excel temporal en memoria que contiene SOLO los datos filtrados
                buffer_filtrado = io.BytesIO()
                with pd.ExcelWriter(buffer_filtrado, engine='openpyxl') as writer:
                    # El motor espera encontrar estas hojas, así que se las enviamos pre-filtradas
                    excel_inspeccion = pd.ExcelFile(archivo_mem)
                    
                    if "BASE PREGRADO" in excel_inspeccion.sheet_names:
                        df_pre_ori = pd.read_excel(excel_inspeccion, sheet_name="BASE PREGRADO")
                        if filtro_carrera:
                            df_pre_ori = df_pre_ori[df_pre_ori["MATERIA"].isin(filtro_carrera)]
                        df_pre_ori.to_excel(writer, sheet_name="BASE PREGRADO", index=False)
                        
                    if "BASE POSTGRADO" in excel_inspeccion.sheet_names:
                        df_post_ori = pd.read_excel(excel_inspeccion, sheet_name="BASE POSTGRADO")
                        if filtro_carrera:
                            df_post_ori = df_post_ori[df_post_ori["MATERIA"].isin(filtro_carrera)]
                        df_post_ori.to_excel(writer, sheet_name="BASE POSTGRADO", index=False)
                
                buffer_filtrado.seek(0)
                
                # Ejecutamos el motor pasándole el Excel filtrado y la lista de salas filtrada
                df_res, nueva_oc, df_malla, resumen, df_s, df_e, df_car, df_tip, df_dem, df_lib, df_rech = ejecutar_asignacion_escenario(
                    archivo_cursos_excel=buffer_filtrado,
                    escenario_id=id_config,
                    lista_salas=salas_prefiltradas,
                    relax_level=tasa_relax
                )
                
                st.session_state["planificacion"] = {
                    "malla": df_res, "metadata": resumen, "salas": df_s, "rechazos": df_rech
                }
                st.success("¡Asignación calculada exitosamente para la selección!")
                st.rerun()
            except Exception as e:
                st.error(f"Error crítico en el acoplamiento: {str(e)}")

# =========================================================
# CAPA DE RENDERS / VISTA DE RESULTADOS
# =========================================================
if st.session_state["planificacion"] is not None:
    st.markdown("### 📊 3. Resultados del Escenario")
    plan = st.session_state["planificacion"]
    meta = plan["metadata"]
    df_visual = plan["malla"]
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Cursos Filtrados Procesados", meta.get("total_cursos", 0))
    col2.metric("Asignaciones Exitosas", meta.get("total_asignadas", 0))
    col3.metric("Efectividad en esta selección", f"{meta.get('porcentaje_asignacion', 0)}%")
    col4.metric("Secciones sin sala", meta.get("sin_sala", 0), delta_color="inverse")
    
    tab_malla, tab_calendario, tab_criticos, tab_exportar = st.tabs([
        "📋 Malla Consolidada", "📅 Agenda por Sala", "🚨Cursos no asignados", "📥 Descargas"
    ])
    
    with tab_malla:
        st.dataframe(df_visual, use_container_width=True, hide_index=True)
        
    with tab_calendario:
        aulas_disponibles = sorted([str(s) for s in df_visual["SALA"].unique() if str(s) != "SIN SALA"])
        if aulas_disponibles:
            sala_sel = st.selectbox("Seleccione el espacio físico a auditar:", aulas_disponibles)
            df_sala_filtrado = df_visual[df_visual["SALA"] == sala_sel]
            
            if not df_sala_filtrado.empty:
                col_texto = "TITULO" if "TITULO" in df_sala_filtrado.columns else "MATERIA"
                try:
                    df_pivot = pd.pivot_table(
                        df_sala_filtrado, index="HORARIO", columns="DIA", values=col_texto,
                        aggfunc=lambda x: " / ".join(sorted(list(map(str, x.unique()))))
                    )
                    st.dataframe(df_pivot, use_container_width=True)
                except Exception:
                    st.dataframe(df_sala_filtrado[["DIA", "HORARIO", col_texto]], use_container_width=True, hide_index=True)
        else:
            st.info("No hay salas asignadas en este subgrupo.")

    with tab_criticos:
        df_sin_sala = df_visual[df_visual["ESTADO"] == "SIN SALA"]
        if not df_sin_sala.empty:
            st.dataframe(df_sin_sala[["MATERIA", "TITULO", "CUPOS", "DIA", "HORARIO", "MOTIVO_RECHAZO"]], use_container_width=True, hide_index=True)
        else:
            st.success("🎉 ¡Ningún curso del grupo filtrado se quedó sin sala!")

    with tab_exportar:
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            df_visual.to_excel(writer, sheet_name="Malla_Asignacion", index=False)
            plan["salas"].to_excel(writer, sheet_name="Ocupacion_Salas", index=False)
            
        st.download_button(
            label="💾 Descargar Excel de este subgrupo (.xlsx)",
            data=excel_buffer.getvalue(),
            file_name=f"Reporte_{id_config}_Filtrado.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

if st.sidebar.button("Limpiar Memoria del Modelo"):
    st.session_state["planificacion"] = None
    st.rerun()
