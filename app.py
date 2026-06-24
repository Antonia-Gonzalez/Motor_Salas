# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import io
from motor import ejecutar_asignacion_global

st.set_page_config(page_title="Motor de Asignación de Salas", layout="wide")

st.title("🏫 Programa para Asignación de Salas")
st.markdown("Optimización de espacios académicos con filtros activos en tiempo real.")

archivo = st.file_uploader(
    "Sube tu archivo 'Programación académica.xlsx'",
    type=["xlsx"]
)

if archivo:
    st.success("📂 Archivo cargado correctamente en memoria.")

    # =============================================================================
    # 🔍 LECTURA DINÁMICA DE OPCIONES PARA LOS FILTROS
    # =============================================================================
    try:
        # 1. Leer y concatenar las hojas de cursos del archivo subido
        df_pre_previa = pd.read_excel(archivo, sheet_name="BASE PREGRADO")
        df_post_previa = pd.read_excel(archivo, sheet_name="BASE POSTGRADO")
        df_base_previa = pd.concat([df_pre_previa, df_post_previa], ignore_index=True)
        
        # 2. Leer las salas desde el archivo maestro constante
        df_salas_previa = pd.read_excel("infraestructura_constante.xlsx", sheet_name="SALAS")
        
        # 3. Extraer opciones para los selectores de la barra lateral
        carreras_disponibles = sorted(df_base_previa["MATERIA"].dropna().astype(str).str.strip().str.upper().unique())
        edificios_disponibles = sorted(df_salas_previa["EDIFICIO"].dropna().astype(str).str.strip().str.upper().unique())
        tipos_disponibles = sorted(df_salas_previa["TIPO DE SALA"].dropna().astype(str).str.strip().str.upper().unique())
        formatos_disponibles = sorted(df_salas_previa["FORMATO"].dropna().astype(str).str.strip().str.upper().unique())
        
        # NUEVO: Lista de salas individuales disponibles
        salas_disponibles = sorted(df_salas_previa["SALA"].dropna().astype(str).str.strip().str.upper().unique())
        
        reuniones_raw = df_base_previa["TIPO"].dropna().astype(str).str.strip().str.upper().replace({"HYBR": "HIBR"}).unique()
        reuniones_validas_sistema = ["AYUD", "CLAS", "HIBR", "PRBA", "EXAM"]
        reuniones_disponibles = sorted([r for r in reuniones_raw if r in reuniones_validas_sistema])

    except Exception as e:
        st.error(f"Error al leer las hojas del Excel para los filtros: {e}")
        st.stop()

    # =============================================================================
    # ⚙️ FILTROS EN LA BARRA LATERAL (SIDEBAR)
    # =============================================================================
    st.sidebar.header("⚙️ Filtros Establecidos")
    
    solo_post = st.sidebar.checkbox("Filtrar solo Postgrado", value=False)
    solo_pre = st.sidebar.checkbox("Filtrar solo Pregrado", value=False)

    st.sidebar.markdown("---")
    st.sidebar.header("⚙️ Filtros Multiselección")

    carreras_sel = st.sidebar.multiselect(
        "Carreras a procesar",
        options=carreras_disponibles,
        default=carreras_disponibles
    )

    reuniones_sel = st.sidebar.multiselect(
        "Tipos de reunión a procesar",
        options=reuniones_disponibles,
        default=reuniones_disponibles
    )

    edificios_sel = st.sidebar.multiselect(
        "Edificios permitidos",
        options=edificios_disponibles,
        default=edificios_disponibles
    )

    tipos_sel = st.sidebar.multiselect(
        "Tipos de Sala permitidos",
        options=tipos_disponibles,
        default=tipos_disponibles
    )

    formatos_sel = st.sidebar.multiselect(
        "Formatos permitidos",
        options=formatos_disponibles,
        default=formatos_disponibles
    )

    # NUEVO: Filtro multiselección para Salas específicas
    salas_sel = st.sidebar.multiselect(
        "Salas específicas permitidas",
        options=salas_disponibles,
        default=salas_disponibles
    )

    # Validación: verificar que ningún filtro se quede vacío
    if not carreras_sel or not edificios_sel or not tipos_sel or not formatos_sel or not reuniones_sel or not salas_sel:
        st.sidebar.warning("⚠️ Debes seleccionar al menos un elemento en cada filtro para poder ejecutar el motor.")
        ejecutar_deshabilitado = True
    else:
        ejecutar_deshabilitado = False

    # =============================================================================
    # 🚀 EJECUCIÓN DEL MOTOR
    # =============================================================================
    if st.button("🚀 Ejecutar Motor de Optimización", disabled=ejecutar_deshabilitado):
        with st.spinner("Procesando asignaciones jerárquicas con filtros aplicados..."):
            try:
                # 🎯 Enviamos todas las selecciones de la UI directamente hacia motor.py
                resultado_base, df_malla = ejecutar_asignacion_global(
                    archivo,
                    solo_postgrado=solo_post,
                    solo_pregrado=solo_pre,
                    lista_carreras=carreras_sel,
                    lista_reuniones=reuniones_sel,
                    lista_edificios=edificios_sel,
                    lista_tipos_sala=tipos_sel,
                    lista_formatos=formatos_sel,
                    lista_salas=salas_sel  
                )
                
                st.success("🎉 ¡Proceso terminado exitosamente!")
                
                # =============================================================================
                # 🛠️ [AQUÍ SE APLICÓ EL CAMBIO] NUEVA LÓGICA DE FILTRADO POR ESTADO CLAVE
                # =============================================================================
                total_cursos = len(resultado_base)
                
                # Consideramos asignados a todos los que empiecen con "ASIGNADO" (Automáticos y Manuales)
                cursos_asignados = resultado_base[resultado_base["ESTADO"].str.startswith("ASIGNADO", na=False)].shape[0]
                
                # Consideramos sin sala ÚNICAMENTE a los que el motor marcó explícitamente como "SIN SALA"
                cursos_sin_sala = resultado_base[resultado_base["ESTADO"] == "SIN SALA"].shape[0]
                
                porcentaje_asignacion = (cursos_asignados / total_cursos * 100) if total_cursos > 0 else 0
                
                resumen_estados = resultado_base["ESTADO"].value_counts().reset_index()
                resumen_estados.columns = ["ESTADO", "CANTIDAD"]
                resumen_estados["PORCENTAJE"] = (resumen_estados["CANTIDAD"] / total_cursos * 100).round(2)
                
                # Filtramos la tabla de "Sin asignar" basándonos en el ESTADO estricto de error del motor
                df_sin_sala = resultado_base[resultado_base["ESTADO"] == "SIN SALA"]
                carreras_sin_asignar = df_sin_sala["MATERIA"].nunique() if not df_sin_sala.empty else 0
                
                if not df_sin_sala.empty:
                    resumen_sin_sala_carrera = df_sin_sala.groupby(["MATERIA"]).size().reset_index(name="CURSOS SIN SALA")
                    resumen_sin_sala_carrera = resumen_sin_sala_carrera.sort_values("CURSOS SIN SALA", ascending=False)
                else:
                    resumen_sin_sala_carrera = pd.DataFrame(columns=["MATERIA", "CURSOS SIN SALA"])
                # =============================================================================

                st.subheader("📊 Indicadores de Rendimiento")
                kpi1, kpi2, kpi3, kpi4 = st.columns(4)
                kpi1.metric("Total Cursos Procesados", f"{total_cursos}")
                kpi2.metric("Cursos Asignados", f"{cursos_asignados}")
                kpi3.metric("Porcentaje de Asignación", f"{porcentaje_asignacion:.2f}%")
                kpi4.metric("Carreras sin Sala", f"{carreras_sin_asignar}")

                st.subheader("🔍 Pestañas de Análisis")
                tab1, tab2, tab3, tab4 = st.tabs([
                    "📋 Resumen de Estados", 
                    "⚠️ Cursos y Carreras Sin Asignar", 
                    "🏫 Malla de Ocupación por Sala",
                    "👁️ Vista Previa Data Completa"
                ])
                
                with tab1:
                    st.markdown("### Resumen Global de Estados")
                    st.dataframe(resumen_estados, use_container_width=True)
                
                with tab2:
                    st.markdown("### Detalle de Infraestructura Faltante")
                    if cursos_sin_sala > 0:
                        st.warning(f"Se detectaron un total de {cursos_sin_sala} cursos sin sala asignada.")
                        col_izq, col_der = st.columns([1, 2])
                        with col_izq:
                            st.dataframe(resumen_sin_sala_carrera, use_container_width=True)
                        with col_der:
                            columnas_visibles = ["MATERIA", "TITULO", "CUPOS", "DIA", "HORARIO", "MOTIVO_RECHAZO"]
                            st.dataframe(df_sin_sala[columnas_visibles], use_container_width=True)
                    else:
                        st.success("¡Excelente! El 100% de los cursos consiguieron sala con las restricciones provistas.")
                
                with tab3:
                    st.markdown("### Distribución del Horario por Sala Física")
                    st.dataframe(df_malla, use_container_width=True)
                    
                with tab4:
                    st.markdown("### Tabla de Cursos General (Primeros 150 registros)")
                    st.dataframe(resultado_base.head(150), use_container_width=True)

                output = io.BytesIO()
                with pd.ExcelWriter(output, engine="openpyxl") as writer:
                    resultado_base.to_excel(writer, sheet_name="Asignacion_Cursos", index=False)
                    resumen_estados.to_excel(writer, sheet_name="Resumen_Estados", index=False)
                    resumen_sin_sala_carrera.to_excel(writer, sheet_name="Sin_Sala_Carrera", index=False)
                    df_malla.to_excel(writer, sheet_name="Malla_Ocupacion_Salas", index=False)
                
                excel_en_memoria = output.getvalue()

                st.markdown("---")
                st.download_button(
                    label="📥 Descargar Reporte Final de Auditoría (.xlsx)",
                    data=excel_en_memoria,
                    file_name="Resultado_Final_Con_Filtros.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

            except Exception as e:
                st.error(f"❌ Ocurrió un error al procesar el motor de optimización: {str(e)}")
