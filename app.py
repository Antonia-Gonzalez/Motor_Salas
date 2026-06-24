import streamlit as st
import pandas as pd
from motor import ejecutar_asignacion_incremental

# Inicialización de las estructuras persistentes en memoria global de la sesión
if "ocupacion_global" not in st.session_state:
    st.session_state["ocupacion_global"] = None  # Almacena el diccionario interno de colisiones
if "historico_cursos" not in st.session_state:
    st.session_state["historico_cursos"] = pd.DataFrame()  # Acumula las filas asignadas de todas las corridas

st.sidebar.title("🗺️ Planificador Incremental")

# Control de Flujo de Datos
modo_planificacion = st.sidebar.radio(
    "Modo de Planificación",
    ["Nueva planificación (Limpiar pizarra)", "Continuar sobre escenario existente"]
)

if modo_planificacion == "Nueva planificación (Limpiar pizarra)":
    st.session_state["ocupacion_global"] = None
    st.session_state["historico_cursos"] = pd.DataFrame()

# Control de eficiencia vía Slider Dinámico como solicitaste
eficiencia_slider = st.sidebar.slider(
    "Eficiencia de ocupación mínima requerida (%)",
    min_value=0, max_value=100, value=75, step=5
)
eficiencia_minima_float = eficiencia_slider / 100.0

# [Filtros de carrera, edificios, etc. normales de tu interfaz...]
carreras_seleccionadas = st.sidebar.multiselect("Carreras para esta corrida", ["ICA", "ICC", "ADM", "DEM", "MED"])

archivo_cargado = st.file_uploader("Cargar Base Excel de Cursos", type=["xlsx"])

if st.sidebar.button("⚡ Ejecutar corrida de escenario"):
    if archivo_cargado is not None:
        # Ejecutar el motor inyectando el estado previo acumulado
        df_resultado, nueva_ocupacion, df_malla = ejecutar_asignacion_incremental(
            archivo_cursos_excel=archivo_cargado,
            eficiencia_minima=eficiencia_minima_float,
            ocupacion_previa=st.session_state["ocupacion_global"],
            lista_carreras=carreras_seleccionadas
        )
        
        # Guardar estados devueltos en la sesión global
        st.session_state["ocupacion_global"] = nueva_ocupacion
        st.session_state["historico_cursos"] = pd.concat([st.session_state["historico_cursos"], df_resultado]).drop_duplicates(
            subset=["NRC", "DIA", "HORARIO"], keep="last"
        )
        
        st.success(f"¡Corrida de escenario para {carreras_seleccionadas} consolidada con éxito!")

df_asignados = st.session_state["historico_cursos"]
df_asignados["% Num"] = pd.to_numeric(df_asignados["% OCUPACION SALA"].str.replace("%", ""), errors="coerce")

sobredimensionados = df_asignados[df_asignados["% Num"] < 25][["CARRERA", "TITULO", "SALA", "CUPOS", "CAPACIDAD SALA", "% OCUPACION SALA"]]
st.dataframe(sobredimensionados)

if not df_malla.empty:
    uso_edificios = df_malla.groupby("EDIFICIO").agg(
        asientos_solicitados=("CUPOS", "sum"),
        capacidad_instalada=("CAPACIDAD", "sum")
    ).reset_index()
    uso_edificios["% Eficiencia"] = (uso_edificios["asientos_solicitados"] / uso_edificios["capacidad_instalada"]) * 100
    
    st.bar_chart(data=uso_edificios, x="EDIFICIO", y="% Eficiencia")

if not df_malla.empty:
    heatmap_data = df_malla.pivot_table(
        index="HORARIO", 
        columns="EDIFICIO", 
        values="CURSO_OCUPANTE", 
        aggfunc="count"
    ).fillna(0)
    st.dataframe(heatmap_data.style.background_gradient(cmap="Oranges"))


