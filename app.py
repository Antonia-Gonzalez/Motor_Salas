# app.py
import streamlit as st
import pandas as pd
import io
import os

# Importación unificada del cerebro lógico (Nuevo Retorno unificado)
from motor import ejecutar_asignacion_escenario

st.set_page_config(layout="wide", page_title="🏛️ Sistema de Planificación", page_icon="🏛️")
st.title("🏛️ Sistema de Asignación de Salas UAndes")

# Inicialización de estados globales de persistencia
if "planificacion" not in st.session_state:
    st.session_state["planificacion"] = None

if "ocupacion_acumulada" not in st.session_state:
    st.session_state["ocupacion_acumulada"] = {}

# =========================================================
# CONFIGURACIÓN Y PARÁMETROS INTERACTIVOS (SIDEBAR)
# =========================================================
st.sidebar.header("⚙️ Parámetros de la asignación")
id_config = st.sidebar.text_input("ID de Planificación / Corrida", value="ESC-2026")

tasa_relax = st.sidebar.slider("Nivel de Relajación de Reglas (%)", min_value=60, max_value=100, value=90, step=5)
st.sidebar.caption("💡 100%: Solo edificios ideales fijados por carrera.\n"
                   "90%: Busca en el ideal, si colisiona abre el resto del campus.\n"
                   "60%: Todos los edificios compiten libremente desde la Fase 1.")

# --- CARGA AUTOMÁTICA DE INFRAESTRUCTURA ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ruta_infra = os.path.join(BASE_DIR, "infraestructura_constante.xlsx")

df_infra_raw = pd.DataFrame()

if os.path.exists(ruta_infra):
    df_infra_raw = pd.read_excel(ruta_infra)
    if "TIPO DE SALA" not in df_infra_raw.columns and "TIPO_SALA" in df_infra_raw.columns:
        df_infra_raw = df_infra_raw.rename(columns={"TIPO_SALA": "TIPO DE SALA"})
    
    salas_seleccionadas_base = df_infra_raw.to_dict("records")
    st.sidebar.success(f"✅ {len(salas_seleccionadas_base)} salas base disponibles en infraestructura.")
else:
    st.sidebar.error(f"❌ Falta el archivo crítico de infraestructura.")
    salas_seleccionadas_base = []

# =========================================================
# 📥 PASO 1: SUBIR EL ARCHIVO DE CURSOS
# =========================================================
st.markdown("### 📥 1. Cargar Programación Académica")
archivo_mem = st.file_uploader("📂 Subir archivo de 'Programación académica (.xlsx)'", type=["xlsx"])

# Inicializamos variables de control limpias
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

if archivo_mem:
    try:
        excel_inspeccion = pd.ExcelFile(archivo_mem)
        dfs_hojas = []
        
        # Leemos y etiquetamos el origen de los datos de forma transparente para el motor
        if "BASE PREGRADO" in excel_inspeccion.sheet_names:
            df_p = pd.read_excel(excel_inspeccion, sheet_name="BASE PREGRADO")
            df_p["ORIGEN_BASE"] = "PREGRADO"
            dfs_hojas.append(df_p)
        if "BASE POSTGRADO" in excel_inspeccion.sheet_names:
            df_g = pd.read_excel(excel_inspeccion, sheet_name="BASE POSTGRADO")
            df_g["ORIGEN_BASE"] = "POSTGRADO"
            dfs_hojas.append(df_g)
        
        if dfs_hojas:
            df_cursos_prefiltrados = pd.concat(dfs_hojas, ignore_index=True)
            
            # Extraer universos únicos de Entrada de forma dinámica
            carreras_disponibles = sorted(df_cursos_prefiltrados["MATERIA"].dropna().unique()) if "MATERIA" in df_cursos_prefiltrados.columns else []
            edificios_disponibles = sorted(df_infra_raw["EDIFICIO"].dropna().unique()) if "EDIFICIO" in df_infra_raw.columns else []
            salas_disponibles = sorted(df_infra_raw["SALA"].dropna().unique()) if "SALA" in df_infra_raw.columns else []
            
            # Renderizar selectores en la barra lateral
            filtro_carrera = st.sidebar.multiselect("Filtrar por Materia (Ej: ICA, ICI):", carreras_disponibles)
            filtro_edificio = st.sidebar.multiselect("Limitar a Edificios:", edificios_disponibles)
            filtro_sala = st.sidebar.multiselect("Limitar a Salas Específicas:", salas_disponibles)
            
            # Aplicar filtros en caliente sobre los DataFrames de entrada
            if filtro_carrera:
                df_cursos_prefiltrados = df_cursos_prefiltrados[df_cursos_prefiltrados["MATERIA"].isin(filtro_carrera)]
            
            df_infra_filtrada = df_infra_raw.copy()
            if filtro_edificio:
                df_infra_filtrada = df_infra_filtrada[df_infra_filtrada["EDIFICIO"].isin(filtro_edificio)]
            if filtro_sala:
                df_infra_filtrada = df_infra_filtrada[df_infra_filtrada["SALA"].isin(filtro_sala)]
                
            salas_prefiltradas = df_infra_filtrada.to_dict("records")
            
            st.info(f"📊 **Filtro activo de entrada:** Se enviarán al motor **{len(df_cursos_prefiltrados)} secciones** y **{len(salas_prefiltradas)} salas** físicas.")
    except Exception as e:
        st.error(f"Error leyendo el archivo para filtros: {e}")
else:
    st.sidebar.info("ℹ️ Sube un archivo de cursos para activar los filtros previos.")

# =========================================================
# 🚀 PASO 3: EJECUCIÓN DEL MOTOR CON FILTRADO BIFÁSICO Y O(1)
# =========================================================
if archivo_mem and not df_cursos_prefiltrados.empty:
    st.markdown("### ⚙️ 2. Ejecutar asignación")
    
    # Checkbox opcional para heredar o limpiar la memoria acumulada entre corridas
    heredar_ocupacion = st.checkbox("Heredar ocupación de corridas anteriores congeladas", value=False)
    
    if st.button("🚀 Inicializar Asignación Inteligente de Salas"):
        with st.spinner("Ejecutando asignación acelerada multi-fase en tiempo lineal..."):
            try:
                # Definición del estado de la ocupación previa en base a la decisión del usuario
                estado_previo = st.session_state["ocupacion_acumulada"] if heredar_ocupacion else {}
                
                # Invocación directa pasándole el DataFrame filtrado listo (Sin buffers intermedios)
                resultado = ejecutar_asignacion_escenario(
                    df_cursos=df_cursos_prefiltrados,
                    lista_salas_origen=salas_prefiltradas,
                    relax_level=tasa_relax,
                    ocupacion_previa=estado_previo,
                    id_corrida=id_config
                )
                
                # Guardar el diccionario completo del escenario en el session_state
                st.session_state["planificacion"] = resultado
                # Sincronizar el mapa maestro de ocupación global de la memoria de la aplicación
                st.session_state["ocupacion_acumulada"] = resultado["ocupacion"]
                
                st.success("¡Asignación calculada exitosamente! Complejidad optimizada y desperdicio mitigado.")
                st.rerun()
            except Exception as e:
                st.error(f"Error crítico en el acoplamiento con motor.py: {str(e)}")

# =========================================================
# CAPA DE RENDERS / VISTA DE RESULTADOS (DICCIONARIO ENCAPSULADO)
# =========================================================
if st.session_state["planificacion"] is not None:
    st.markdown("### 📊 3. Resultados del Escenario Calculado")
    
    # Desempaquetado del objeto unificado de escenario
    escenario = st.session_state["planificacion"]
    df_visual = escenario["malla"]
    meta = escenario["resumen"]
    df_salas = escenario["metricas"]
    df_rechazos = escenario["rechazos"]
    
    # Despliegue de métricas clave (KPIs de Eficiencia)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Cursos Procesados (Secciones)", meta.get("total_cursos", 0))
    col2.metric("Asignaciones Exitosas", meta.get("total_asignadas", 0))
    col3.metric("Efectividad global", f"{meta.get('porcentaje_asignacion', 0)}%")
    col4.metric("Secciones sin sala", meta.get("sin_sala", 0), delta_color="inverse")
    
    tab_malla, tab_calendario, tab_salas, tab_criticos, tab_exportar = st.tabs([
        "📋 Malla Consolidada", "📅 Agenda por Sala", "🏫 Uso de Infraestructura", "🚨 Cursos No Asignados", "📥 Descargas"
    ])
    
    with tab_malla:
        st.subheader("Registros Lineales Asignados")
        st.dataframe(df_visual, use_container_width=True, hide_index=True)
        
    with tab_calendario:
        st.subheader("Auditoría de Horarios por Espacio")
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
            st.info("No hay salas físicas ocupadas en esta asignación.")

    with tab_salas:
        st.subheader("Métricas de rendimiento de aulas físicas (Mapeo O(1))")
        st.caption("Muestra la cantidad de bloques ocupados y el espacio libre remanente basado en una semana estándar.")
        st.dataframe(df_salas, use_container_width=True, hide_index=True)

    with tab_criticos:
        st.subheader("Secciones rechazadas por el motor")
        df_sin_sala = df_visual[df_visual["ESTADO"] == "SIN SALA"]
        
        if not df_sin_sala.empty:
            col_a, col_b = st.columns([2, 1])
            with col_a:
                st.dataframe(df_sin_sala[["ID_ASIGNACION_UNICO", "MATERIA", "CUPOS", "DIA", "HORARIO", "MOTIVO_RECHAZO"]], use_container_width=True, hide_index=True)
            with col_b:
                st.markdown("**Resumen de Rechazos por Materia/Carrera**")
                st.dataframe(df_rechazos, use_container_width=True, hide_index=True)
        else:
            st.success("🎉 ¡Felicidades! Ningún curso se quedó sin sala bajo los parámetros de este escenario.")

    with tab_exportar:
        st.subheader("Exportación de Datos Consolidados")
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            df_visual.to_excel(writer, sheet_name="Malla_Consolidada", index=False)
            df_salas.to_excel(writer, sheet_name="Rendimiento_Infraestructura", index=False)
            df_rechazos.to_excel(writer, sheet_name="Resumen_Rechazos", index=False)
            
            # Convertimos el diccionario extendido de ocupación de celdas a un DataFrame plano descargable
            if escenario["ocupacion"]:
                plano_ocupacion = []
                for (sala_id, dia, hora), info in escenario["ocupacion"].items():
                    plano_ocupacion.append({"SALA_ID": sala_id, "DIA": dia, "HORARIO": hora, **info})
                pd.DataFrame(plano_ocupacion).to_excel(writer, sheet_name="Matriz_Ocupacion_Detalle", index=False)
            
        st.download_button(
            label="💾 Descargar Excel de Planificación Completo (.xlsx)",
            data=excel_buffer.getvalue(),
            file_name=f"Resultado_Escenario_{id_config}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

# Botón de reset estructural del sistema
if st.sidebar.button("Limpiar Memoria Total del Modelo"):
    st.session_state["planificacion"] = None
    st.session_state["ocupacion_acumulada"] = {}
    st.rerun()
