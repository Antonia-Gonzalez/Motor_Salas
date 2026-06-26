# app.py
import streamlit as st
import pandas as pd
import io
import os

# Importación unificada del cerebro lógico
from motor import ejecutar_asignacion_escenario

st.set_page_config(layout="wide", page_title="🏛️ Sistema de Planificación", page_icon="🏛️")
st.title("🏛️ Sistema Profesional de Asignación de Salas")

if "planificacion" not in st.session_state:
    st.session_state["planificacion"] = None

# =========================================================
# CONFIGURACIÓN Y PARÁMETROS INTERACTIVOS (SIDEBAR)
# =========================================================
st.sidebar.header("⚙️ Parámetros del Motor")
id_config = st.sidebar.text_input("ID de Planificación", value="ESC-2026")

tasa_relax = st.sidebar.slider("Nivel de Relajación de Reglas (%)", min_value=60, max_value=100, value=90, step=5)
st.sidebar.caption("💡 100%: Filtro estricto de cercanía. 60%: Permite ubicar en cualquier edificio secundario disponible.")

# --- AQUÍ VA EL CAMBIO INTELIGENTE DE RUTA ABSOLUTA ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ruta_infra = os.path.join(BASE_DIR, "data", "infraestructura_constante.xlsx")

if os.path.exists(ruta_infra):
    df_infra = pd.read_excel(ruta_infra)
    salas_seleccionadas = df_infra.to_dict("records")
    st.sidebar.success(f"✅ {len(salas_seleccionadas)} salas cargadas desde la base de datos.")
else:
    st.sidebar.error(f"❌ Falta el archivo crítico de infraestructura.")
    st.sidebar.info(f"Ruta buscada por el sistema: `{ruta_infra}`")
    salas_seleccionadas = []

# =========================================================
# FLUJO DE ENTRADA DE DATOS Y PROCESAMIENTO
# =========================================================
archivo_mem = st.file_uploader("📂 Subir Programación Académica Semanal (.xlsx)", type=["xlsx"])

if archivo_mem and salas_seleccionadas:
    if st.button("🚀 Inicializar Optimización Global"):
        with st.spinner("El motor de asignación está analizando las restricciones y penalizaciones temporales..."):
            try:
                # LLAMADA LIMPIA BAJO EL CONTRATO DE 11 VARIABLES
                df_res, nueva_oc, df_malla, resumen, df_s, df_e, df_car, df_tip, df_dem, df_lib, df_rech = ejecutar_asignacion_escenario(
                    archivo_cursos_excel=archivo_mem,
                    escenario_id=id_config,
                    lista_salas=salas_seleccionadas,
                    relax_level=tasa_relax
                )
                
                # Almacenamiento seguro e inmutable en persistencia de sesión
                st.session_state["planificacion"] = {
                    "malla": df_res, "metadata": resumen, "salas": df_s, "rechazos": df_rech
                }
                st.success("¡Asignación calculada óptimamente!")
            except Exception as e:
                st.error(f"Error crítico en el acoplamiento de datos: {str(e)}")

# =========================================================
# CAPA 5: INTERFAZ GRÁFICA EXCLUSIVA DE USUARIO (RENDERS)
# =========================================================
if st.session_state["planificacion"] is not None:
    plan = st.session_state["planificacion"]
    meta = plan["metadata"]
    df_res_main = plan["malla"]
    
    # 1. Indicadores de Desempeño Superiores (KPIs)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Cursos Procesados", meta.get("total_cursos", 0))
    col2.metric("Asignaciones Exitosas", meta.get("total_asignadas", 0))
    col3.metric("Tasa de Efectividad del Escenario", f"{meta.get('porcentaje_asignacion', 0)}%")
    col4.metric("Secciones Rechazadas", meta.get("sin_sala", 0), delta_color="inverse")
    
    # 2. Pestañas de Visualización Organizada
    tab_malla, tab_calendario, tab_criticos, tab_exportar = st.tabs([
        "📋 Malla Consolidada", "📅 Agenda por Sala Física", "🚨 Auditoría de Rechazos", "📥 Descargas"
    ])
    
    with tab_malla:
        st.markdown("##### Vista de Auditoría General de Planificación")
        st.dataframe(df_res_main, use_container_width=True, hide_index=True)
        
    with tab_calendario:
        st.markdown("##### Agenda Horaria por Aula")
        salas_disponibles = sorted([str(s) for s in df_res_main["SALA"].unique() if str(s) != "SIN SALA"])
        sala_sel = st.selectbox("Seleccione el espacio físico a auditar:", salas_disponibles)
        
        df_sala_filtrado = df_res_main[df_res_main["SALA"] == sala_sel] if sala_sel else pd.DataFrame()
        
        if not df_sala_filtrado.empty:
            # Extractor dinámico robusto para evitar KeyErrors accidentales
            if "NOMBRE SECCIÓN" in df_sala_filtrado.columns: col_texto = "NOMBRE SECCIÓN"
            elif "CARRERA" in df_sala_filtrado.columns: col_texto = "CARRERA"
            else: col_texto = "SALA"

            try:
                # Pivote de calendario nativo
                df_pivot = pd.pivot_table(
                    df_sala_filtrado, index="HORARIO", columns="DIA", values=col_texto,
                    aggfunc=lambda x: " / ".join(sorted(list(map(str, x.unique())))) if len(x.unique()) > 1 else str(x.unique()[0])
                )
                
                # Ordenamiento cronológico seguro aislando el inicio del bloque de texto "08:30-10:00"
                indice_cronologico = sorted(df_pivot.index, key=lambda x: pd.to_datetime(str(x).split("-")[0].strip(), format="%H:%M", errors='coerce').time())
                dias_columnas = [d for d in ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES", "SABADO"] if d in df_pivot.columns]
                
                st.dataframe(df_pivot.reindex(index=indice_cronologico, columns=dias_columnas).fillna("— (Disponible)"), use_container_width=True)
            except Exception:
                st.info("Estructurando los bloques cronológicos de la sala...")
                st.dataframe(df_sala_filtrado[["DIA", "HORARIO", col_texto]], use_container_width=True, hide_index=True)

    with tab_criticos:
        df_rech_carrera = plan["rechazos"]
        st.markdown("##### Distribución General de Cursos Excluidos por Carrera")
        
        if df_rech_carrera is not None and not df_rech_carrera.empty:
            st.bar_chart(df_rech_carrera.set_index("CARRERA")["sin_sala"])
            st.dataframe(df_rech_carrera, use_container_width=True, hide_index=True)
            
            st.markdown("---")
            st.markdown("##### Desglose Detallado de Secciones Afectadas")
            
            df_sin_sala = df_res_main[df_res_main["ESTADO"] == "SIN SALA"]
            cols_utiles = [c for c in ["CARRERA", "NOMBRE SECCIÓN", "CUPOS", "DIA", "HORARIO", "MOTIVO_RECHAZO"] if c in df_sin_sala.columns]
            st.dataframe(df_sin_sala[cols_utiles].drop_duplicates(), use_container_width=True, hide_index=True)
        else:
            st.success("🎉 ¡Excelente noticia! El 100% de las secciones consiguieron un aula física óptima en este escenario.")

    with tab_exportar:
        st.markdown("##### Generar Paquete de Descarga Oficial")
        excel_buffer = io.BytesIO()
        
        # openpyxl nativo estándar compatible con ambientes Linux de Streamlit Cloud
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            df_res_main.to_excel(writer, sheet_name="Malla_Asignacion", index=False)
            plan["salas"].to_excel(writer, sheet_name="Uso_Ocupacion_Salas", index=False)
            
        st.download_button(
            label="💾 Descargar Reporte en Excel (.xlsx)",
            data=excel_buffer.getvalue(),
            file_name=f"Reporte_Salas_{id_config}_{tasa_relax}pct.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

# --- REFRESH / CONTROL DE CACHÉ DE SIMULACIÓN ---
if st.sidebar.button("Limpiar Memoria del Modelo"):
    st.session_state["planificacion"] = None
    if hasattr(st, "rerun"): st.rerun()
    else: st.experimental_rerun()
