# app.py
import streamlit as st
import pandas as pd
import io
import os

from motor import ejecutar_asignacion_escenario

st.set_page_config(layout="wide", page_title="🏛️ Sistema de Planificación", page_icon="🏛️")
st.title("🏛️ Sistema de Asignación de Salas UAndes")

# 📌 PUNTO 9: Unificación del Estado Profesional de Sesión ("escenario")
if "escenario" not in st.session_state:
    st.session_state["escenario"] = {
        "resultado": None,              # Almacenará el dict devuelto por el motor
        "ocupacion_maestra": {},        # Mapa acumulado de celdas comprometidas
        "filtros_carrera": [],          # 📌 PUNTO 4: Persistencia estricta de filtros
        "filtros_edificio": [],
        "filtros_sala": []
    }

esc_state = st.session_state["escenario"]

# =========================================================
# CONFIGURACIÓN Y PARÁMETROS INTERACTIVOS (SIDEBAR)
# =========================================================
st.sidebar.header("⚙️ Parámetros de la asignación")
id_config = st.sidebar.text_input("ID del Escenario Actual", value="ESC-2026")

tasa_relax = st.sidebar.slider("Nivel de Relajación de Reglas (%)", min_value=60, max_value=100, value=90, step=5)
st.sidebar.caption("💡 100%: Modo Estricto Geográfico. 90%: Modo Mixto Dinámico. 60%: Campus Abierto Total.")

# 📌 PUNTO 3: Selector de Flujo Explícito e Intuitivo
modo_flujo = st.sidebar.radio(
    "Modo de Operación",
    ["Nuevo escenario (Sobrescribir todo)", "Continuar escenario (Asignación incremental/Heredar)"]
)

# --- CARGA AUTOMÁTICA DE INFRAESTRUCTURA ---
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
# 📥 PASO 1: CARGA DE ARCHIVO DE CURSOS
# =========================================================
st.markdown("### 📥 1. Cargar Programación Académica")
archivo_mem = st.file_uploader("📂 Subir archivo de 'Programación académica (.xlsx)'", type=["xlsx"])

df_cursos_prefiltrados = pd.DataFrame()
salas_prefiltradas = salas_seleccionadas_base

# =========================================================
# 🔍 PASO 2: FILTROS PERSISTENTES (PRE-ASIGNACIÓN)
# =========================================================
st.sidebar.markdown("---")
st.sidebar.header("Filtros de Segmentación")

if archivo_mem:
    try:
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
        
        if dfs_hojas:
            df_total_cursos = pd.concat(dfs_hojas, ignore_index=True)
            
            carreras_disponibles = sorted(df_total_cursos["MATERIA"].dropna().unique()) if "MATERIA" in df_total_cursos.columns else []
            edificios_disponibles = sorted(df_infra_raw["EDIFICIO"].dropna().unique()) if "EDIFICIO" in df_infra_raw.columns else []
            salas_disponibles = sorted(df_infra_raw["SALA"].dropna().unique()) if "SALA" in df_infra_raw.columns else []
            
            # 📌 PUNTO 4: Inyección de estados guardados en el Widget
            f_carr = st.sidebar.multiselect("Filtrar por Materia:", carreras_disponibles, default=esc_state["filtros_carrera"])
            f_edif = st.sidebar.multiselect("Limitar a Edificios:", edificios_disponibles, default=esc_state["filtros_edificio"])
            f_sala = st.sidebar.multiselect("Limitar a Salas:", salas_disponibles, default=esc_state["filtros_sala"])
            
            # Guardamos la selección de inmediato para evitar pérdidas por reactividad
            esc_state["filtros_carrera"] = f_carr
            esc_state["filtros_edificio"] = f_edif
            esc_state["filtros_sala"] = f_sala
            
            # Procesamiento de filtros
            df_cursos_prefiltrados = df_total_cursos.copy()
            if f_carr:
                df_cursos_prefiltrados = df_cursos_prefiltrados[df_cursos_prefiltrados["MATERIA"].isin(f_carr)]
            
            df_infra_filtrada = df_infra_raw.copy()
            if f_edif: df_infra_filtrada = df_infra_filtrada[df_infra_filtrada["EDIFICIO"].isin(f_edif)]
            if f_sala: df_infra_filtrada = df_infra_filtrada[df_infra_filtrada["SALA"].isin(f_sala)]
            
            salas_prefiltradas = df_infra_filtrada.to_dict("records")
            st.info(f"📊 **Datos activos retenidos:** {len(df_cursos_prefiltrados)} secciones | {len(salas_prefiltradas)} salas.")
    except Exception as e:
        st.error(f"Error procesando filtros persistentes: {e}")
else:
    st.sidebar.info("ℹ️ Sube un archivo para inicializar los universos de control.")

# =========================================================
# 🚀 PASO 3: INVOCACIÓN AL MOTOR (DICCIONARIO SEGURO Y COMPACTO)
# =========================================================
if archivo_mem and not df_cursos_prefiltrados.empty:
    st.markdown("### ⚙️ 2. Procesar Núcleo de Optimización")
    if st.button("🚀 Ejecutar Algoritmo Multi-Fase"):
        with st.spinner("Asignando espacios con control de desperdicio hper-veloz..."):
            # 📌 PUNTO 3: Herencia controlada según el botón radial seleccionado
            limpiar_memoria = ("Nuevo escenario" in modo_flujo)
            ocupacion_inyectable = {} if limpiar_memoria else esc_state["ocupacion_maestra"]
            
            # 📌 PUNTO 1 & 2: Firma compacta y limpia, recibe df y retorna dict unificado
            resultado_dict = ejecutar_asignacion_escenario(
                df_cursos=df_cursos_prefiltrados,
                lista_salas_origen=salas_prefiltradas,
                relax_level=tasa_relax,
                ocupacion_previa=ocupacion_inyectable
            )
            
            # Actualizamos el session state maestro sin usar st.rerun() (Punto 8 y 9)
            esc_state["resultado"] = resultado_dict
            esc_state["ocupacion_maestra"] = resultado_dict["ocupacion"]
            st.success("¡Optimización completada! Renderizando vistas en tiempo real.")

# =========================================================
# CAPA DE RENDERS / VISTA DE RESULTADOS
# =========================================================
if esc_state["resultado"] is not None:
    st.markdown("### 📊 3. Dashboard del Escenario")
    res_dict = esc_state["resultado"]
    df_malla = res_dict["malla"]
    meta = res_dict["resumen"]
    df_salas = res_dict["metricas"]
    df_rechazos = res_dict["rechazos"]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Secciones Evaluadas", meta.get("total_cursos", 0))
    col2.metric("Asignadas con Éxito", meta.get("total_asignadas", 0))
    col3.metric("Efectividad", f"{meta.get('porcentaje_asignacion', 0)}%")
    col4.metric("Sin Aula Física", meta.get("sin_sala", 0), delta_color="inverse")

    tab_malla, tab_calendario, tab_salas, tab_criticos, tab_exportar = st.tabs([
        "📋 Malla Consolidada", "📅 Agenda por Sala", "🏫 Uso de Infraestructura", "🚨 Cursos No Asignados", "📥 Descargas"
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
                col_texto = "TITULO" if "TITULO" in df_sala_filtrado.columns else "MATERIA"
                try:
                    df_pivot = pd.pivot_table(
                        df_sala_filtrado, index="HORARIO", columns="DIA", values=col_texto,
                        aggfunc=lambda x: " / ".join(sorted(list(map(str, x.unique()))))
                    )
                    # 📌 PUNTO 5: ORDENAMIENTO ESTRICTO DE HORARIOS Y DÍAS
                    dias_ordenados = [d for d in ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES", "SABADO"] if d in df_pivot.columns]
                    df_pivot = df_pivot.reindex(columns=dias_ordenados)
                    df_pivot = df_pivot.sort_index() # Ordenación alfanumérica natural del bloque horario
                    st.dataframe(df_pivot, use_container_width=True)
                except Exception:
                    st.dataframe(df_sala_filtrado[["DIA", "HORARIO", col_texto]], use_container_width=True, hide_index=True)
        else:
            st.info("No se registran asignaciones físicas en esta iteración.")

    with tab_salas:
        st.subheader("📊 Analíticas Avanzadas de Ocupación")
        
        # 📌 PUNTO 6: RENDERS GRÁFICOS AVANZADOS DE INFRAESTRUCTURA
        if not df_salas.empty:
            df_salas["% Utilización"] = (df_salas["BLOQUES_OCUPADOS"] / 50 * 100).round(1)
            
            m1, m2, m3 = st.columns(3)
            # Extremos de uso
            max_row = df_salas.loc[df_salas["BLOQUES_OCUPADOS"].idxmax()]
            min_row = df_salas.loc[df_salas["BLOQUES_OCUPADOS"].idxmin()]
            
            m1.metric("Promedio de Ocupación Campus", f"{round(df_salas['% Utilización'].mean(), 1)}%")
            m2.metric("Aula Más Demandada", f"{max_row['EDIFICIO']}-{max_row['SALA']}", f"{max_row['% Utilización']}% Uso")
            m3.metric("Aula Menos Demandada", f"{min_row['EDIFICIO']}-{min_row['SALA']}", f"{min_row['% Utilización']}% Uso")
            
            st.markdown("**Porcentaje de utilización semanal por Aula Física**")
            st.bar_chart(df_salas, x="SALA", y="% Utilización", color="EDIFICIO", use_container_width=True)
            st.dataframe(df_salas[["SALA", "EDIFICIO", "CAPACIDAD", "BLOQUES_OCUPADOS", "% Utilización", "HORAS_LIBERADAS" if "HORAS_LIBERADAS" in df_salas.columns else "HORAS_LIBRES"]], use_container_width=True, hide_index=True)

    with tab_criticos:
        df_sin_sala = df_malla[df_malla["ESTADO"] == "SIN SALA"]
        if not df_sin_sala.empty:
            c_izq, c_der = st.columns([2, 1])
            with c_izq:
                st.dataframe(df_sin_sala[["ID_ASIGNACION_UNICO", "MATERIA", "CUPOS", "DIA", "HORARIO", "MOTIVO_RECHAZO"]], use_container_width=True, hide_index=True)
            with c_der:
                st.markdown("**Frenos de Asignación por Carrera**")
                st.dataframe(df_rechazos, use_container_width=True, hide_index=True)
        else:
            st.success("🎉 ¡Excelente! Cero rechazos reportados para este subgrupo.")

    with tab_exportar:
        st.subheader("Auditoría de Configuración e Historial")
        
        # 📌 PUNTO 7: EXPORTADOR DOCUMENTADO DE ARTIFACTS MULTI-HOJA
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            df_malla.to_excel(writer, sheet_name="Malla_Asignacion", index=False)
            df_salas.to_excel(writer, sheet_name="Uso_Salas_Analitico", index=False)
            df_rechazos.to_excel(writer, sheet_name="Rechazos_Agrupados", index=False)
            
            # Hoja de Configuración/Metadata para Trazabilidad Académica
            df_meta_run = pd.DataFrame([
                {"Parametro": "ID Escenario", "Valor": id_config},
                {"Parametro": "Nivel Relax Configurado", "Valor": f"{tasa_relax}%"},
                {"Parametro": "Modo de Flujo de Operación", "Valor": modo_flujo},
                {"Parametro": "Filtro de Materias Aplicado", "Valor": ", ".join(esc_state["filtros_carrera"]) if esc_state["filtros_carrera"] else "TODO EL UNIVERSO"},
                {"Parametro": "Filtro Edificios", "Valor": ", ".join(esc_state["filtros_edificio"]) if esc_state["filtros_edificio"] else "TODO EL CAMPUS"},
                {"Parametro": "Cursos Exitosos", "Valor": meta.get("total_asignadas", 0)},
                {"Parametro": "Cursos Rechazados", "Valor": meta.get("sin_sala", 0)}
            ])
            df_meta_run.to_excel(writer, sheet_name="Config_Corrida_KPI", index=False)
            
        st.download_button(
            label="📥 Descargar Libro de Planificación Certificado (.xlsx)",
            data=excel_buffer.getvalue(),
            file_name=f"Reporte_Consolidado_{id_config}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

if st.sidebar.button("Limpiar Todo y Reiniciar Sistema"):
    st.session_state["escenario"] = {
        "resultado": None, "ocupacion_maestra": {},
        "filtros_carrera": [], "filtros_edificio": [], "filtros_sala": []
    }
    st.rerun()
