import streamlit as st
import pandas as pd
import io
from motor import ejecutar_asignacion_escenario

st.set_page_config(layout="wide", page_title="BI Planta Física V2", page_icon="🏛️")
st.title("🏛️ Sistema BI de Infraestructura Universitaria")

if "planificacion" not in st.session_state:
    st.session_state["planificacion"] = {
        "df_resultado": pd.DataFrame(), "ocupacion": {}, "df_malla": pd.DataFrame(),
        "escenarios_metadata": [], "escenarios_config": {}, "archivo_maestro_bytes": None,
        "metricas_salas": pd.DataFrame(), "metricas_edificios": pd.DataFrame(),
        "met_carreras": pd.DataFrame(), "met_tipos": pd.DataFrame(), 
        "demanda_horaria": pd.DataFrame(), "salas_libres": pd.DataFrame(), "rechazos_carrera": pd.DataFrame()
    }

@st.cache_data
def cargar_datos_infraestructura_filtros():
    try:
        df_infra = pd.read_excel("infraestructura_constante.xlsx", sheet_name="SALAS")
        df_infra["EDIFICIO"] = df_infra["EDIFICIO"].fillna("").astype(str).str.strip().str.upper()
        df_infra["SALA"] = df_infra["SALA"].fillna("").astype(str).str.strip().str.upper()
        
        salas_duplicadas = df_infra[df_infra.duplicated(subset=["SALA"], keep=False)]["SALA"].unique()
        for idx, fila in df_infra.iterrows():
            s_nombre = str(fila["SALA"]).strip().upper()
            if s_nombre in salas_duplicadas:
                df_infra.at[idx, "SALA"] = f"{s_nombre} {int(fila['CAPACIDAD'])}"
                
        edificios = sorted([e for e in df_infra["EDIFICIO"].unique() if e != ""])
        salas = sorted([s for s in df_infra["SALA"].unique() if s != ""])
        return df_infra, edificios, salas
    except:
        return pd.DataFrame(), [], []

df_infra, opciones_edificios, opciones_salas = cargar_datos_infraestructura_filtros()

@st.cache_data
def extraer_materias_del_excel(bytes_file):
    try:
        xl = pd.ExcelFile(io.BytesIO(bytes_file))
        materias = set()
        for sheet in ["BASE PREGRADO", "BASE POSTGRADO"]:
            if sheet in xl.sheet_names:
                df = xl.parse(sheet)
                if "MATERIA" in df.columns:
                    valores = df["MATERIA"].dropna().astype(str).str.strip().str.upper().unique()
                    materias.update(valores)
        return sorted(list(materias))
    except:
        return []

st.sidebar.header("⚙️ Configuración y Filtros")
archivo_maestro = st.sidebar.file_uploader("1️⃣ Subir Malla Académica (.xlsx)", type=["xlsx"])

opciones_materias = []
if archivo_maestro is not None:
    bytes_maestro = archivo_maestro.getvalue()
    st.session_state["planificacion"]["archivo_maestro_bytes"] = bytes_maestro
    opciones_materias = extraer_materias_del_excel(bytes_maestro)
elif st.session_state["planificacion"]["archivo_maestro_bytes"] is not None:
    opciones_materias = extraer_materias_del_excel(st.session_state["planificacion"]["archivo_maestro_bytes"])

st.sidebar.markdown("---")
st.sidebar.subheader("2️⃣ Filtros de Selección Dinámica")

# FILTRO DE MATERIAS ASIGNADAS
if opciones_materias:
    st.sidebar.markdown("**Materias a seleccionar**")
    seleccionar_todas_mat = st.sidebar.checkbox("Incluir todas las materias", value=True)
    if seleccionar_todas_mat:
        materias_seleccionadas = opciones_materias
        st.sidebar.caption(f"✓ Listas las {len(opciones_materias)} materias detectadas.")
    else:
        materias_seleccionadas = st.sidebar.multiselect("Filtrar materias específicas:", options=opciones_materias)
else:
    st.sidebar.info("💡 Sube una malla curricular para extraer las materias dinámicamente.")
    materias_seleccionadas = []

# FILTROS DE INFRAESTRUCTURA
if opciones_edificios:
    st.sidebar.markdown("**Edificios a seleccionar**")
    seleccionar_todos_edf = st.sidebar.checkbox("Incluir todos los edificios", value=True)
    edificios_seleccionados = None if seleccionar_todos_edf else st.sidebar.multiselect("Filtrar edificios:", options=opciones_edificios)
else:
    edificios_seleccionados = None

if opciones_salas:
    st.sidebar.markdown("**Salas a seleccionar**")
    seleccionar_todas_sal = st.sidebar.checkbox("Incluir todas las salas", value=True)
    if seleccionar_todas_sal:
        salas_seleccionadas = None
    else:
        if edificios_seleccionados:
            salas_disponibles = sorted(df_infra[df_infra["EDIFICIO"].isin(edificios_seleccionados)]["SALA"].unique().tolist())
        else:
            salas_disponibles = opciones_salas
        salas_seleccionadas = st.sidebar.multiselect("Filtrar salas específicas:", options=salas_disponibles)
else:
    salas_seleccionadas = None

st.sidebar.markdown("---")
st.sidebar.subheader("3️⃣ Parámetros Algorítmicos")

id_config = st.sidebar.text_input("Código de Corrida", value=f"RUN_{len(st.session_state['planificacion']['escenarios_metadata'])+1}")
eficiencia_pct = st.sidebar.slider("Exigencia Eficiencia Mínima (%)", 0, 100, 75, step=5)
modo_estricto_bool = st.sidebar.checkbox("Desactivar Cascada (Modo Estricto)", value=False)
modo_cruzada_sel = st.sidebar.selectbox("Agrupamiento Listas Cruzadas", ["MAXIMO", "SUMAR", "PROMEDIO"], index=0)

if st.sidebar.button("⚡ Computar Asignación de Planta"):
    if st.session_state["planificacion"]["archivo_maestro_bytes"] is None:
        st.sidebar.error("❌ Sube un archivo de malla académica antes de simular.")
    elif not materias_seleccionadas:
        st.sidebar.error("❌ No hay materias seleccionadas para el procesamiento.")
    else:
        with st.spinner("Procesando balance de planta a velocidad optimizada..."):
            archivo_mem = io.BytesIO(st.session_state["planificacion"]["archivo_maestro_bytes"])
            
            df_res, nueva_oc, df_malla, resumen, df_s, df_e, df_car, df_tip, df_dem, df_lib, df_rech = ejecutar_asignacion_escenario(
                archivo_cursos_excel=archivo_mem, escenario_id=id_config,
                eficiencia_minima=eficiencia_pct / 100.0, modo_estricto=modo_estricto_bool,
                modo_lista_cruzada=modo_cruzada_sel, ocupacion_previa=st.session_state["planificacion"]["ocupacion"],
                lista_carreras=materias_seleccionadas,
                lista_edificios=edificios_seleccionados,
                lista_salas=salas_seleccionadas
            )
            
            # --- TRAZA DE DEPURACIÓN DE COLUMNAS SOLICITADA ---
            st.write("Columnas df_lib:")
            st.write(df_lib.columns.tolist())
            
            if not df_res.empty:
                st.session_state["planificacion"]["df_resultado"] = df_res
                st.session_state["planificacion"]["escenarios_config"][id_config] = {
                    "escenario_id": id_config, "eficiencia": eficiencia_pct / 100.0,
                    "modo_estricto": modo_estricto_bool, "modo_cruzada": modo_cruzada_sel, 
                    "carreras": materias_seleccionadas, "edificios": edificios_seleccionados, "salas": salas_seleccionadas
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
                st.success(f"Corrida '{id_config}' integrada con éxito.")
                st.rerun()

if st.session_state["planificacion"]["escenarios_metadata"]:
    meta_actual = st.session_state["planificacion"]["escenarios_metadata"][-1]
    st.markdown("### 🎯 Cuadro de Mando Operativo General")
    c1, c2, c3 = st.columns(3)
    c1.metric("Cursos Asignados con Éxito", meta_actual["asignados"])
    c2.metric("Efectividad de Asignación", f"{meta_actual['porcentaje_asignacion']}%")
    c3.metric("Salas Activas en Malla", meta_actual["salas_utilizadas"])
    st.markdown("---")

tab_control, tab_analitica, tab_cuellos, tab_calendario, tab_criticos, tab_libres = st.tabs([
    "📋 Gestión de Corridas", "📊 Planta Física", "🔥 Saturación Temporal", "📅 Matriz de Calendarios", "🚨 Control de Rechazos", "🔓 Horarios Libres de Salas"
])

with tab_control:
    if st.session_state["planificacion"]["escenarios_metadata"]:
        st.dataframe(pd.DataFrame(st.session_state["planificacion"]["escenarios_metadata"]), use_container_width=True, hide_index=True)
        opciones_eliminar = [e["escenario"] for e in st.session_state["planificacion"]["escenarios_metadata"]]
        target_eliminar = st.selectbox("Seleccione simulación a remover:", opciones_eliminar)
        
        if st.button("🗑️ Purgar Escenario"):
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
                    lista_carreras=cfg["carreras"], lista_edificios=cfg.get("edificios", None), lista_salas=cfg.get("salas", None)
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
    df_tip = st.session_state["planificacion"]["met_tipos"]
    
    col_g1, col_g2 = st.columns(2)
    with col_g1:
        if not df_e.empty:
            st.markdown("##### 🏢 Uso Real de Infraestructura por Edificio (%)")
            st.bar_chart(df_e.set_index("EDIFICIO")["% UTILIZACIÓN SEMANAL HORARIA"])
    with col_g2:
        if not df_s.empty:
            st.markdown("##### 🏛️ Top 10 Aulas con Mayor Saturación (Horas Semanales)")
            st.bar_chart(df_s.sort_values("HORAS_OCUPADAS", ascending=False).head(10).set_index("SALA")["HORAS_OCUPADAS"])
        if not df_tip.empty:
            st.markdown("##### ⚙️ Distribución de Horas por Tipo de Reunión")
            st.bar_chart(df_tip.set_index("TIPO_REUNION")["HORAS_CONSUMIDAS"])

with tab_cuellos:
    st.subheader("🔥 Análisis de Presión Temporal por Momento Operativo")
    df_dem = st.session_state["planificacion"]["demanda_horaria"]
    if not df_dem.empty:
        st.line_chart(df_dem.set_index("MOMENTO_OPERATIVO")["BLOQUES_ACTIVOS"])
        st.dataframe(df_dem[["DIA", "HORA_STR", "BLOQUES_ACTIVOS"]], use_container_width=True, hide_index=True)

with tab_calendario:
    st.subheader("📅 Distribución Semanal por Sala")
    df_malla_cal = st.session_state["planificacion"]["df_malla"]
    
    if not df_malla_cal.empty:
        sala_seleccionada = st.selectbox("Aula para Auditoría:", sorted(df_malla_cal["SALA"].unique()))
        df_sala_filtrado = df_malla_cal[df_malla_cal["SALA"] == sala_seleccionada]
        
        if not df_sala_filtrado.empty:
            df_pivot = pd.pivot_table(
                df_sala_filtrado, index="HORA_INICIO", columns="DIA", values="CURSO_OCUPANTE",
                aggfunc=lambda x: " ⚠️ COLISIÓN: ".join(sorted(list(map(str, x.unique())))) if len(x.unique()) > 1 else str(x.unique()[0])
            )
            indice_cronologico = sorted(df_pivot.index, key=lambda x: pd.to_datetime(x, format="%H:%M").time())
            dias_columnas = [d for d in ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES", "SABADO"] if d in df_pivot.columns]
            st.dataframe(df_pivot.reindex(index=indice_cronologico, columns=dias_columnas).fillna("🟢 Completamente Libre"), use_container_width=True)

with tab_criticos:
    st.subheader("🚨 Diagnóstico Estratégico y Tasas de Rechazo")
    df_rech = st.session_state["planificacion"]["rechazos_carrera"]
    df_res_criticos = st.session_state["planificacion"]["df_resultado"]
    
    if not df_rech.empty:
        st.markdown("##### 📈 Tasa de Rechazo de Aulas por Carrera (%)")
        st.bar_chart(df_rech.set_index("CARRERA")["TASA_RECHAZO_PCT"])
        st.dataframe(df_rech, use_container_width=True, hide_index=True)
        
        st.markdown("---")
        st.markdown("##### 🔎 Detalle de Secciones Afectadas")
        df_sin_sala = df_res_criticos[df_res_criticos["ESTADO"] == "SIN SALA"]
        if not df_sin_sala.empty:
            st.dataframe(df_sin_sala[["CARRERA", "NOMBRE SECCIÓN", "CUPOS_CONSOLIDADOS", "DIA", "HORARIO", "MOTIVO_RECHAZO"]].drop_duplicates(), use_container_width=True, hide_index=True)
        else:
            st.success("🏆 ¡Todos los cursos encontraron un aula compatible!")

with tab_libres:
    st.subheader("🔓 Inventario Disponible (Horarios Libres de Salas)")
    df_lib = st.session_state["planificacion"]["salas_libres"]
    
    if not df_lib.empty:
        col_f1, col_f2, col_f3 = st.columns(3)
        f_edificio = col_f1.selectbox("Edificio:", ["TODOS"] + sorted(list(df_lib["EDIFICIO"].unique())))
        f_dia = col_f2.selectbox("Día de la Semana:", ["TODOS"] + list(df_lib["DIA"].unique()))
        f_cap = col_f3.number_input("Aforo Mínimo Requerido:", min_value=0, value=20, step=5)
            
        df_filtro_libres = df_lib.copy()
        if f_edificio != "TODOS":
            df_filtro_libres = df_filtro_libres[df_filtro_libres["EDIFICIO"] == f_edificio]
        if f_dia != "TODOS":
            df_filtro_libres = df_filtro_libres[df_filtro_libres["DIA"] == f_dia]
        df_filtro_libres = df_filtro_libres[df_filtro_libres["CAPACIDAD"] >= f_cap]
        
        # --- BLOQUE REEMPLAZADO CON CONTROL DE COLUMNAS FALTANTES ---
        st.markdown(f"**Ventanas de tiempo disponibles encontradas:** {len(df_filtro_libres)}")

        columnas_requeridas = [
            "SALA",
            "EDIFICIO",
            "CAPACIDAD",
            "DIA",
            "INICIO",
            "FIN",
            "FECHA_DISP_INI",
            "FECHA_DISP_FIN"
        ]

        faltantes = [c for c in columnas_requeridas if c not in df_filtro_libres.columns]

        if faltantes:
            st.error(
                f"El motor devolvió un DataFrame sin las columnas esperadas.\n\n"
                f"Columnas faltantes: {faltantes}"
            )

            st.write("Columnas disponibles:")
            st.write(df_filtro_libres.columns.tolist())

            st.write("Primeras filas:")
            st.dataframe(df_filtro_libres.head())

        else:
            st.dataframe(
                df_filtro_libres[columnas_requeridas]
                .sort_values(
                    by=["EDIFICIO", "SALA", "DIA", "INICIO"]
                ),
                use_container_width=True,
                hide_index=True
            )
