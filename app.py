import streamlit as st
import pandas as pd
import io
from motor import ejecutar_asignacion_escenario

st.set_page_config(layout="wide", page_title="BI Planta Física V2", page_icon="🏛️")
st.title("🏛️ Sistema BI de Infraestructura Universitaria e Inteligencia Inversa")

if "planificacion" not in st.session_state:
    st.session_state["planificacion"] = {
        "df_resultado": pd.DataFrame(), "ocupacion": {}, "df_malla": pd.DataFrame(),
        "escenarios_metadata": [], "escenarios_config": {}, "archivo_maestro_bytes": None,
        "metricas_salas": pd.DataFrame(), "metricas_edificios": pd.DataFrame(),
        "met_carreras": pd.DataFrame(), "met_tipos": pd.DataFrame(), 
        "demanda_horaria": pd.DataFrame(), "salas_libres": pd.DataFrame(), "rechazos_carrera": pd.DataFrame()
    }

# PANEL DE CONTROL LATERAL
st.sidebar.header("⚙️ Parámetros de Simulación")
id_config = st.sidebar.text_input("Código de Corrida", value=f"RUN_{len(st.session_state['planificacion']['escenarios_metadata'])+1}")
carreras_input = st.sidebar.multiselect("Escuelas Planificadas", ["ICA", "ICC", "ADM", "DEM", "MED"], default=["ICA", "ICC"])
eficiencia_pct = st.sidebar.slider("Exigencia Eficiencia Mínima (%)", 0, 100, 75, step=5)
modo_estricto_bool = st.sidebar.checkbox("Desactivar Cascada (Modo Estricto)", value=False)
modo_cruzada_sel = st.sidebar.selectbox("Agrupamiento Listas Cruzadas", ["MAXIMO", "SUMAR", "PROMEDIO"], index=0)

archivo_maestro = st.sidebar.file_uploader("Subir Malla Académica (.xlsx)", type=["xlsx"])
if archivo_maestro is not None:
    st.session_state["planificacion"]["archivo_maestro_bytes"] = archivo_maestro.read()

if st.sidebar.button("⚡ Computar Asignación de Planta"):
    if st.session_state["planificacion"]["archivo_maestro_bytes"] is not None and carreras_input:
        with st.spinner("Ejecutando balance multi-fase en memoria transaccional..."):
            archivo_mem = io.BytesIO(st.session_state["planificacion"]["archivo_maestro_bytes"])
            
            # Sincronización exacta de variables devueltas
            df_res, nueva_oc, df_malla, resumen, df_s, df_e, df_car, df_tip, df_dem, df_lib, df_rech = ejecutar_asignacion_escenario(
                archivo_cursos_excel=archivo_mem, escenario_id=id_config,
                eficiencia_minima=eficiencia_pct / 100.0, modo_estricto=modo_estricto_bool,
                modo_lista_cruzada=modo_cruzada_sel, ocupacion_previa=st.session_state["planificacion"]["ocupacion"],
                lista_carreras=carreras_input
            )
            
            if not df_res.empty:
                st.session_state["planificacion"]["df_resultado"] = df_res
                st.session_state["planificacion"]["escenarios_config"][id_config] = {
                    "escenario_id": id_config, "eficiencia": eficiencia_pct / 100.0,
                    "modo_estricto": modo_estricto_bool, "modo_cruzada": modo_cruzada_sel, "carreras": carreras_input
                }
                st.session_state["planificacion"]["ocupacion"] = nueva_oc
                st.session_state["planificacion"]["df_malla"] = df_malla
                st.session_state["planificacion"]["escenarios_metadata"].append(resumen)
                st.session_state["planificacion"]["metricas_salas"] = df_s
                st.session_state["planificacion"]["metricas_edificios"] = df_e
                st.session_state["planificacion"]["met_carreras"] = df_car
                st.session_state["planificacion"]["met_tipos"] = df_tip
                st.session_state["planificacion"]["demanda_horaria"] = df_dem
                st.session_state["planificacion"]["salas_libres"] = df_lib
                st.session_state["planificacion"]["rechazos_carrera"] = df_rech
                st.success(f"Corrida '{id_config}' integrada al historial.")
                st.rerun()

if st.session_state["planificacion"]["escenarios_metadata"]:
    meta_actual = st.session_state["planificacion"]["escenarios_metadata"][-1]
    st.markdown("### 🎯 Cuadro de Mando Operativo General")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Cursos Asignados con Éxito", meta_actual["asignados"])
    c2.metric("Efectividad de Asignación", f"{meta_actual['porcentaje_asignacion']}%")
    c3.metric("Salas Activas en Malla", meta_actual["salas_utilizadas"])
    c4.metric("Horas Totales Ocupadas", f"{meta_actual['horas_ocupadas']} hrs")
    st.markdown("---")

tab_control, tab_analitica, tab_cuellos, tab_calendario, tab_criticos, tab_libres = st.tabs([
    "📋 Gestión de Corridas", "📊 Planta Física", "🔥 Saturación Temporal", "📅 Matriz de Calendarios", "🚨 Control de Rechazos", "🔓 Slots Libres Reales"
])

with tab_control:
    if st.session_state["planificacion"]["escenarios_metadata"]:
        st.dataframe(pd.DataFrame(st.session_state["planificacion"]["escenarios_metadata"]), use_container_width=True, hide_index=True)
        opciones_eliminar = [e["escenario"] for e in st.session_state["planificacion"]["escenarios_metadata"]]
        target_eliminar = st.selectbox("Seleccione simulación a remover:", opciones_eliminar)
        
        if st.button("🗑️ Purgar Escenario y Re-calcular Cascada"):
            st.session_state["planificacion"]["escenarios_config"].pop(target_eliminar, None)
            st.session_state["planificacion"]["ocupacion"] = {}
            configs_restantes = list(st.session_state["planificacion"]["escenarios_config"].values())
            st.session_state["planificacion"]["escenarios_metadata"] = []
            
            for cfg in configs_restantes:
                archivo_re = io.BytesIO(st.session_state["planificacion"]["archivo_maestro_bytes"])
                _, nueva_oc, df_malla, resumen, df_s, df_e, df_car, df_tip, df_dem, df_lib, df_rech = ejecutar_asignacion_escenario(
                    archivo_cursos_excel=archivo_re, escenario_id=cfg["escenario_id"],
                    eficiencia_minima=cfg["eficiencia"], modo_estricto=cfg["modo_estricto"],
                    modo_lista_cruzada=cfg["modo_cruzada"], ocupacion_previa=st.session_state["planificacion"]["ocupacion"],
                    lista_carreras=cfg["carreras"]
                )
                st.session_state["planificacion"]["ocupacion"] = nueva_oc
                st.session_state["planificacion"]["df_malla"] = df_malla
                st.session_state["planificacion"]["escenarios_metadata"].append(resumen)
                st.session_state["planificacion"]["metricas_salas"] = df_s
                st.session_state["planificacion"]["metricas_edificios"] = df_e
                st.session_state["planificacion"]["met_carreras"] = df_car
                st.session_state["planificacion"]["met_tipos"] = df_tip
                st.session_state["planificacion"]["demanda_horaria"] = df_dem
                st.session_state["planificacion"]["salas_libres"] = df_lib
                st.session_state["planificacion"]["rechazos_carrera"] = df_rech
            st.rerun()

with tab_analitica:
    st.subheader("📊 Métricas de Capacidad Física")
    df_s = st.session_state["planificacion"]["metricas_salas"]
    df_e = st.session_state["planificacion"]["metricas_edificios"]
    df_car = st.session_state["planificacion"]["met_carreras"]
    
    col_g1, col_g2 = st.columns(2)
    with col_g1:
        if not df_e.empty:
            st.markdown("##### 🏢 Uso Real de Infraestructura por Edificio (%)")
            st.bar_chart(df_e.set_index("EDIFICIO")["% UTILIZACIÓN SEMANAL HORARIA"])
        if not df_car.empty:
            st.markdown("##### 🎓 Consumo de Horas Cátedra por Escuela")
            st.bar_chart(df_car.set_index("CARRERA")["HORAS_CONSUMIDAS"])
    with col_g2:
        if not df_s.empty:
            st.markdown("##### 🏛️ Top 10 Aulas con Mayor Saturación (Horas Semanales)")
            st.bar_chart(df_s.sort_values("HORAS_OCUPADAS", ascending=False).head(10).set_index("SALA")["HORAS_OCUPADAS"])
            st.markdown("##### 📉 Top 10 Aulas con Peor Eficiencia de Asientos Ocupados")
            st.bar_chart(df_s.sort_values("EFICIENCIA_PROMEDIO", ascending=True).head(10).set_index("SALA")["EFICIENCIA_PROMEDIO"])

with tab_cuellos:
    # 🛠️ SOLUCIÓN PROBLEMA 1 Y 2: Renderizado impecable de la demanda temporal acoplada
    st.subheader("🔥 Análisis de Presión Temporal por Momento Operativo")
    df_dem = st.session_state["planificacion"]["demanda_horaria"]
    if not df_dem.empty:
        st.write("Identificación exacta de cuellos de botella bidimensionales (`DÍA` + `HORA`):")
        st.line_chart(df_dem.set_index("MOMENTO_OPERATIVO")["BLOQUES_ACTIVOS"])
        st.dataframe(df_dem[["DIA", "HORA_STR", "BLOQUES_ACTIVOS"]], use_container_width=True, hide_index=True)
    else:
        st.info("Sin registros de saturación temporal computados.")

with tab_calendario:
    # 🛠️ SOLUCIÓN PROBLEMA 3: Orden cronológico estricto por hora de inicio sin solapamientos falsos
    st.subheader("📅 Distribución Semanal Libre de Falsas Colisiones")
    df_malla_cal = st.session_state["planificacion"]["df_malla"]
    
    if not df_malla_cal.empty:
        salas_disponibles_view = sorted(df_malla_cal["SALA"].unique())
        sala_seleccionada = st.selectbox("Aula para Auditoría:", salas_disponibles_view)
        df_sala_filtrado = df_malla_cal[df_malla_cal["SALA"] == sala_seleccionada]
        
        if not df_sala_filtrado.empty:
            df_pivot = pd.pivot_table(
                df_sala_filtrado,
                index="HORA_INICIO",
                columns="DIA",
                values="CURSO_OCUPANTE",
                aggfunc=lambda x: " ⚠️ COLISIÓN: ".join(sorted(list(map(str, x.unique())))) if len(x.unique()) > 1 else str(x.unique()[0])
            )
            dias_columnas = [d for d in ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES", "SABADO"] if d in df_pivot.columns]
            df_pivot = df_pivot.reindex(columns=dias_columnas).fillna("🟢 Completamente Libre")
            st.markdown(f"**Matriz Temporal de Operación de la Sala: {sala_seleccionada}**")
            st.dataframe(df_pivot, use_container_width=True)
        else:
            st.success("Esta sala no tiene asignaciones cargadas en este escenario.")
    else:
        st.info("Requiere una simulación activa para renderizar el calendario.")

with tab_criticos:
    # 🛠️ SOLUCIÓN PROBLEMA 5: Métricas macro para decisiones de infraestructura y expansión de planta
    st.subheader("🚨 Diagnóstico Estratégico y Tasas de Rechazo")
    df_rech = st.session_state["planificacion"]["rechazos_carrera"]
    df_res_criticos = st.session_state["planificacion"]["df_resultado"]
    
    if not df_rech.empty:
        st.markdown("##### 📈 Tasa de Rechazo de Aulas por Carrera (%)")
        st.bar_chart(df_rech.set_index("CARRERA")["TASA_RECHAZO_PCT"])
        st.dataframe(df_rech.rename(columns={"total_cursos": "CURSOS TOTALES", "sin_sala": "CURSOS RECHAZADOS", "TASA_RECHAZO_PCT": "% TASA RECHAZO"}), use_container_width=True, hide_index=True)
        
        st.markdown("---")
        st.markdown("##### 🔎 Detalle de Secciones Afectadas")
        df_sin_sala = df_res_criticos[df_res_criticos["ESTADO"] == "SIN SALA"]
        if not df_sin_sala.empty:
            columnas_operativas = ["CARRERA", "NOMBRE SECCIÓN", "CUPOS_CONSOLIDADOS", "DIA", "HORARIO", "MOTIVO_RECHAZO"]
            st.dataframe(df_sin_sala[columnas_operativas].drop_duplicates(), use_container_width=True, hide_index=True)
        else:
            st.success("🏆 ¡Eficiencia perfecta! Todos los cursos encontraron un aula compatible.")
    else:
        st.info("No se registran datos. Computa una asignación académica.")

with tab_libres:
    # 🛠️ SOLUCIÓN PROBLEMA 4: Inventario real sobre la grilla teórica maestra universitaria
    st.subheader("🔓 Disponibilidad Real Inversa (Inventario Oculto de la Universidad)")
    df_lib = st.session_state["planificacion"]["salas_libres"]
    
    if not df_lib.empty:
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            f_edificio = st.selectbox("Edificio:", ["TODOS"] + list(df_lib["EDIFICIO"].unique()))
        with col_f2:
            f_dia = st.selectbox("Día de la Semana:", ["TODOS"] + list(df_lib["DIA"].unique()))
        with col_f3:
            f_cap = st.number_input("Aforo Mínimo Requerido:", min_value=0, value=20, step=5)
            
        df_filtro_libres = df_lib.copy()
        if f_edificio != "TODOS":
            df_filtro_libres = df_filtro_libres[df_filtro_libres["EDIFICIO"] == f_edificio]
        if f_dia != "TODOS":
            df_filtro_libres = df_filtro_libres[df_filtro_libres["DIA"] == f_dia]
        df_filtro_libres = df_filtro_libres[df_filtro_libres["CAPACIDAD"] >= f_cap]
        
        st.metric("Bloques Libres Disponibles Reales", len(df_filtro_libres))
        st.dataframe(df_filtro_libres.sort_values(by=["DIA", "INICIO", "SALA"]), use_container_width=True, hide_index=True)
    else:
        st.info("Ejecuta un escenario para calcular los bloques libres puros.")
