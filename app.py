# app.py
import streamlit as st
import pandas as pd
import io
import os

from motor import ejecutar_asignacion_escenario

st.set_page_config(layout="wide", page_title="🏛️ Sistema de Planificación", page_icon="🏛️")
st.title("🏛️ Sistema de Asignación de Salas UAndes")

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
    esc_state["malla_consolidada"] = pd.concat(mallas_acumuladas, ignore_index=True) if mallas_acumuladas else pd.DataFrame()
    
    ult_salas = esc_state["corridas_historicas"][-1]["salas_infra"]
    metricas_infra = []
    for s in ult_salas:
        s_id = f"{s['EDIFICIO']}_{s['SALA']}".replace(" ", "_")
        occ = sum(1 for k in nueva_ocupacion if k[0] == s_id)
        metricas_infra.append({
            "SALA": s["SALA"], "EDIFICIO": s["EDIFICIO"], "CAPACIDAD": s["CAPACIDAD"], 
            "BLOQUES_OCUPADOS": occ, "% Utilización": round((occ / 50 * 100), 1)
        })
    esc_state["metricas_infra"] = pd.DataFrame(metricas_infra)
    
    df_sin = esc_state["malla_consolidada"][esc_state["malla_consolidada"]["ESTADO"] == "SIN SALA"] if ("ESTADO" in esc_state["malla_consolidada"].columns and not esc_state["malla_consolidada"].empty) else pd.DataFrame()
    esc_state["rechazos_consolidados"] = df_sin.groupby("MATERIA").size().reset_index(name="sin_sala") if (not df_sin.empty and "MATERIA" in df_sin.columns) else pd.DataFrame(columns=["MATERIA", "sin_sala"])

# =========================================================
# CONFIGURACIÓN Y PARÁMETROS INTERACTIVOS (SIDEBAR)
# =========================================================
st.sidebar.header("⚙️ Parámetros de la Asignación")
id_config = st.sidebar.text_input("Identificador de la corrida", value="TANDA-A")
tasa_relax = st.sidebar.slider("Nivel de Relajación de Reglas (%)", min_value=60, max_value=100, value=90, step=5)

min_eficiencia = st.sidebar.slider("Eficiencia Mínima de Ocupación Sala (%)", min_value=0, max_value=100, value=20, step=5)
st.sidebar.caption("💡 Evita que cursos pequeños (ej: 10 alumnos) utilicen auditorios gigantescos (ej: capacidad 80).")

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
            
            df_cursos_prefiltrados = df_total_cursos
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
# 🚀 INYECCIÓN AL ESCENARIO INCREMENTAL
# =========================================================
if archivo_mem and not df_cursos_prefiltrados.empty:
    st.markdown("### ⚙️ 2. Procesar condiciones")
    if st.button("🚀 Confirmar e inciar asignación"):
        if any(r["id"] == id_config for r in esc_state["corridas_historicas"]):
            st.error(f"El ID '{id_config}' ya existe en el escenario.")
        else:
            with st.spinner("Consolidando asignaciones incrementales con control de eficiencia..."):
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
    st.sidebar.subheader("🗂️Escenarios")
    for idx, run in enumerate(esc_state["corridas_historicas"]):
        col_run_name, col_run_del = st.sidebar.columns([3, 1])
        col_run_name.caption(f"**{run['id']}** ({len(run['df_cursos'])} curs. | {run.get('min_eficiencia',0)}% ef.)")
        if col_run_del.button("🗑️", key=f"del_{run['id']}_{idx}"):
            esc_state["corridas_historicas"].pop(idx)
            reconstruir_escenario_completo()
            st.rerun()

# =========================================================
# Dashboard del Escenario
# =========================================================
if not esc_state["malla_consolidada"].empty:
    st.markdown("### 📊 3. Dashboard del Escenario")
    df_malla = esc_state["malla_consolidada"]
    df_salas = esc_state["metricas_infra"]
    df_rechazos = esc_state["rechazos_consolidados"]

    tot_c = len(df_malla)
    tot_a = sum(df_malla["ESTADO"].isin(["ASIGNADO", "ASIGNADO_MANUAL"])) if "ESTADO" in df_malla.columns else 0
    
    df_asignados_validos = df_malla[df_malla["ESTADO"].isin(["ASIGNADO", "ASIGNADO_MANUAL"])]
    eficiencia_promedio = round(df_asignados_validos["EFICIENCIA_%"].mean(), 1) if not df_asignados_validos.empty else 0.0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Secciones Evaluadas (Total)", tot_c)
    col2.metric("Asignadas con Éxito", tot_a)
    col3.metric("Eficiencia Ocupación Aula", f"{eficiencia_promedio}%")
    col4.metric("Sin Aula Física", tot_c - tot_a, delta_color="inverse")

    tab_malla, tab_calendario, tab_salas, tab_criticos, tab_exportar = st.tabs([
        "📋 Malla Consolidada Clean", "📅 Agenda por Sala", "🏫 Uso de Infraestructura", "🚨 Cursos No Asignados", "📥 Descarga del Libro"
    ])

    with tab_malla:
        st.dataframe(df_malla, use_container_width=True, hide_index=True)

    with tab_calendario:
        st.subheader("Cronograma Semanal de Espacios")
        aulas_ocupadas = sorted([str(s) for s in df_malla["SALA"].unique() if str(s) != "SIN SALA"])
        if aulas_ocupadas:
            sala_sel = st.selectbox("Seleccione el espacio físico a auditar:", aulas_ocupadas)
            df_sala_filtrado = df_malla[df_malla["SALA"] == sala_sel]
            
            if not df_sala_filtrado.empty:
                df_sala_filtrado["DISPLAY"] = df_sala_filtrado["MATERIA"] + " (Ef: " + df_sala_filtrado["EFICIENCIA_%"].astype(str) + "%)"
                try:
                    df_pivot = pd.pivot_table(
                        df_sala_filtrado, index="HORARIO", columns="DIA", values="DISPLAY",
                        aggfunc=lambda x: " / ".join(sorted(list(map(str, x.unique()))))
                    )
                    dias_ordenados = [d for d in ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES", "SABADO"] if d in df_pivot.columns]
                    df_pivot = df_pivot.reindex(columns=dias_ordenados).sort_index()
                    st.dataframe(df_pivot, use_container_width=True)
                except Exception:
                    st.dataframe(df_sala_filtrado[["DIA", "HORARIO", "DISPLAY"]], use_container_width=True, hide_index=True)

    with tab_salas:
        st.subheader("📊 Analíticas de Ocupación Real")
        if not df_salas.empty:
            m1, m2 = st.columns(2)
            m1.metric("Promedio de Utilización de Horas Campus", f"{round(df_salas['% Utilización'].mean(), 1)}%")
            max_row = df_salas.loc[df_salas["BLOQUES_OCUPADOS"].idxmax()]
            m2.metric("Aula Más Demandada (Bloques)", f"{max_row['EDIFICIO']}-{max_row['SALA']}", f"{max_row['% Utilización']}% Uso")
            
            st.bar_chart(df_salas, x="SALA", y="% Utilización", color="EDIFICIO", use_container_width=True)
            st.dataframe(df_salas, use_container_width=True, hide_index=True)

    with tab_criticos:
        df_sin_sala = df_malla[df_malla["ESTADO"] == "SIN SALA"] if "ESTADO" in df_malla.columns else pd.DataFrame()
        if not df_sin_sala.empty:
            c_izq, c_der = st.columns([2, 1])
            with c_izq:
                st.dataframe(df_sin_sala[["MATERIA", "CUPOS", "DIA", "HORARIO", "MOTIVO_RECHAZO"]], use_container_width=True, hide_index=True)
            with c_der:
                st.markdown("**Frenos de Asignación por Materia**")
                st.dataframe(df_rechazos, use_container_width=True, hide_index=True)
        else:
            st.success("🎉 ¡Excelente! Cero rechazos reportados para esta composición del escenario.")

    with tab_exportar:
        st.subheader("Auditoría de Configuración e Historial")
        
        # 📌 PREPARACIÓN Y CORRECCIÓN DE LA HOJA PRINCIPAL
        df_exportable = df_malla.copy()
        
        # Renombrar columnas internas a las solicitadas para el informe formal
        columnas_renombrar = {
            "CAPACIDAD_SALA": "CAPACIDAD DE LA SALA",
            "EFICIENCIA_%": "% OCUPACIÓN SALA"
        }
        df_exportable = df_exportable.rename(columns=columnas_renombrar)
        
        # Reordenamiento estético: Desplazar columnas de control operacional al final
        columnas_control = ["ESTADO", "MOTIVO_RECHAZO", "CORRIDA_ID"]
        columnas_ordenadas = [c for c in df_exportable.columns if c not in columnas_control]
        columnas_ordenadas += [c for c in columnas_control if c in df_exportable.columns]
        df_exportable = df_exportable[columnas_ordenadas]

        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            df_exportable.to_excel(writer, sheet_name="Malla_Asignacion", index=False)
            df_salas.to_excel(writer, sheet_name="Uso_Salas_Analitico", index=False)
            df_rechazos.to_excel(writer, sheet_name="Rechazos_Por_Materia", index=False)
            
            log_corridas = []
            for r in esc_state["corridas_historicas"]:
                log_corridas.append({
                    "ID Bloque/Tanda": r["id"], 
                    "Configuración Relax": f"{r['relax']}%", 
                    "Filtro Eficiencia Mínima": f"{r.get('min_eficiencia',0)}%",
                    "Secciones Inyectadas": len(r["df_cursos"])
                })
            pd.DataFrame(log_corridas).to_excel(writer, sheet_name="Historial_Pipeline_Capas", index=False)
            
        st.download_button(
            label="📥 Descargar Libro de Planificación Certificado (.xlsx)",
            data=excel_buffer.getvalue(),
            file_name=f"Reporte_Consolidado_Eficiente.xlsx",
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
