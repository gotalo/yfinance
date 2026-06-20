import streamlit as dict_streamlit
import streamlit as st
import os
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
import io
import plotly.express as px

# Configuración de la página web
st.set_page_config(page_title="Acciones", layout="wide")
st.title("📊 Dashboard de Análisis de Activos")

# Configuración de tema de gráficos
sns.set_theme(style="darkgrid")

# 1. CARGA DEL ARCHIVO EXCEL
st.sidebar.header("Configuración")
archivo_cargado = st.sidebar.file_uploader("Sube 'tickets.xlsx'", type=["xlsx"])

if archivo_cargado is not None:
    df_excel = pd.read_excel(archivo_cargado)
    df_excel.columns = df_excel.columns.str.strip()
    
    # Filtrar filas donde 'Buscar' sea 'X'
    df_filtrado = df_excel[df_excel['Buscar'].astype(str).str.strip().str.upper() == 'X']

    tickers = {}
    # --- Relación directa del Nombre con su Ticker limpio ---
    ticker_puro = {} 
    
    for _, fila in df_filtrado.iterrows():
        titulo = f"{str(fila['Descripcion']).strip()}-{str(fila['Tipo']).strip()}-{str(fila['Rubro']).strip()}"
        ticker_yahoo = str(fila['Ticket']).strip()
        tickers[titulo] = ticker_yahoo
        ticker_puro[titulo] = ticker_yahoo 

    st.sidebar.success(f"🎯 Se cargaron {len(tickers)} activos.")

    # --- SECCIÓN DE FECHAS EN PANTALLA ---
    #st.header("📅 Rango de Fechas del Análisis")
    
    # Calcular fechas por defecto (hace 1 año hasta ayer)
    ayer = datetime.now() - timedelta(days=1)
    hace_un_ano = ayer - timedelta(days=1 * 365)
    
    col_fecha_1, col_fecha_2, col_fecha_3 = st.columns(3)
    
    with col_fecha_1:
        fecha_inicio = st.date_input("Fecha DESDE", value=hace_un_ano)
        INICIO = fecha_inicio.strftime("%Y-%m-%d")
        
    with col_fecha_2:
        fecha_fin = st.date_input("Fecha HASTA", value=ayer)
        FIN = fecha_fin.strftime("%Y-%m-%d")
    
    with col_fecha_3:
        st.info(f"📆 Seleccionado: del **{INICIO}** al **{FIN}**")
    
    
    # 2. DESCARGAR DATOS
    with st.spinner("🚀 Descargando datos desde Yahoo Finance..."):
        datos_precios = pd.DataFrame()
        for nombre, ticker in tickers.items():
            try:
                df = yf.download(ticker, start=INICIO, end=FIN, progress=False)
                if df.empty:
                    continue
                
                if df.index.tz is not None:
                    df.index = df.index.tz_localize(None)
                
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)

                if 'Adj Close' in df.columns:
                    datos_precios[nombre] = df['Adj Close']
                else:
                    datos_precios[nombre] = df['Close']
            except Exception as e:
                st.error(f"❌ Error con {nombre}: {e}")

        # Descarga del Dólar Oficial (ARS=X) para usar como Benchmark
        try:
            df_usd = yf.download("ARS=X", start=INICIO, end=FIN, progress=False)
            if not df_usd.empty:
                if isinstance(df_usd.columns, pd.MultiIndex):
                    df_usd.columns = df_usd.columns.get_level_values(0)
                
                val_usd = df_usd['Adj Close'] if 'Adj Close' in df_usd.columns else df_usd['Close']
                df_dolar = pd.DataFrame({"Dólar Oficial (ARS=X)": val_usd})
        except Exception as e:
            st.warning(f"⚠️ No se pudo descargar la evolución del dólar: {e}")
            df_dolar = pd.DataFrame()

        if not datos_precios.empty:
            datos_precios = datos_precios.ffill().bfill()
            if not df_dolar.empty:
                df_dolar = df_dolar.ffill().bfill()

    if not datos_precios.empty:
        # 3. PROCESAMIENTO
        rendimiento_acumulado = (datos_precios / datos_precios.iloc[0]) * 100
        retornos_diarios = datos_precios.pct_change().dropna()
        matriz_correlacion = retornos_diarios.corr()

        # --- NUEVO Y UNIFICADO: Unir Base 100 de Activos + Dólar ---
        if not df_dolar.empty:
            df_base100_completo = rendimiento_acumulado.join(df_dolar, how='inner')
            # Indexamos el dólar a Base 100 desde el primer día común del análisis
            df_base100_completo["Dólar Oficial (ARS=X)"] = (df_base100_completo["Dólar Oficial (ARS=X)"] / df_base100_completo["Dólar Oficial (ARS=X)"].iloc[0]) * 100
        else:
            df_base100_completo = rendimiento_acumulado

        # --- APLICACIÓN DE LA MEDIA MÓVIL DE 20 DÍAS SOBRE LA BASE 100 DE TODO ---
        tendencia_suavizada_completa = df_base100_completo.rolling(window=20, min_periods=1).mean()

        # --- ORGANIZACIÓN EN SOLAPAS (TABS) ---
        #st.header("📊 Resultados del Análisis")

        tab1, tab2, tab3 = st.tabs([
            "📈 Evolución y Tendencias", 
            "🔥 Correlación", 
            "🏆 Tabla Comparativa y Señales"
        ])

        # --- SOLAPA 1: EVOLUCIÓN Y TENDENCIAS ---
        with tab1:
            # Función auxiliar para crear los gráficos con la leyenda abajo
            def crear_grafico_interactivo(df_datos, titulo_grafico, eje_y_nombre):
                fig = px.line(
                    df_datos, 
                    labels={"value": eje_y_nombre, "index": "Fecha", "variable": "Activo"},
                    title=titulo_grafico
                )
                fig.update_layout(
                    legend=dict(
                        orientation="h",
                        yanchor="top",
                        y=-0.2, 
                        xanchor="center",
                        x=0.5
                    ),
                    margin=dict(l=20, r=20, t=50, b=100), 
                    hovermode="closest", 
                    template="plotly_dark" 
                )
                return fig

            # 1. Gráfico de Precios Reales (Unificando Activos + Dólar Real)
            st.markdown("**Evolución de Precios**")
            
            if not df_dolar.empty:
                # Unimos los precios reales de los activos con el valor real del dólar
                datos_precios_con_dolar = datos_precios.join(df_dolar, how='inner')
            else:
                datos_precios_con_dolar = datos_precios

            fig_reales = crear_grafico_interactivo(datos_precios_con_dolar, "", "Precio")
            st.plotly_chart(fig_reales, use_container_width=True)
            
            st.write("---") # Línea divisoria

            # 2. Tendencia Suavizada MM20 en Base 100 incluyendo al Dólar    
            st.markdown("**Tendencia Relativa: Media Móvil 20 días (Base 100 vs Variación del Dólar)**")        
            fig_tendencia_vs_usd = crear_grafico_interactivo(
                tendencia_suavizada_completa, "",  "Media Móvil del Rendimiento (%)"
            )
            st.plotly_chart(fig_tendencia_vs_usd, use_container_width=True)
            st.caption("💡 Las curvas muestran la tendencia suavizada (prom 20 días) partiendo de Base 100. Si la línea de un activo está por encima de la línea del **Dólar Oficial**, significa que en ese período su tendencia técnica superó a la devaluación (Retorno Real Técnico Positivo).")

        # --- SOLAPA 2: CORRELACIÓN (AHORA INTERACTIVA) ---
        with tab2:            
            st.markdown("**Correlación entre Activos**")
            # Creamos el Heatmap interactivo con Plotly Express
            fig_corr = px.imshow(
                matriz_correlacion,
                text_auto=".2f", # Muestra los valores con 2 decimales dentro de cada celda
                color_continuous_scale="RdBu_r", # Escala de colores clásica (Rojo=Positiva, Azul=Negativa)
                zmin=-1,
                zmax=1,
                title="",
                labels=dict(x="X", y="Y", color="Corr")
            )
            
            # Ajustes visuales para que se vea impecable
            fig_corr.update_layout(
                template="plotly_dark",
                margin=dict(l=20, r=20, t=50, b=50),
                height=550 # Altura cómoda para leer los nombres de los ejes
            )
            
            # Mostramos el gráfico en Streamlit ocupando el ancho completo
            st.plotly_chart(fig_corr, use_container_width=True)            



        # --- SOLAPA 3: TABLA E INDICADORES ---
        with tab3:
            st.markdown("**Indicadores y Señales de Inversión**")
            
            # Cálculo de métricas
            rendimiento_total = (datos_precios.iloc[-1] / datos_precios.iloc[0] - 1) * 100
            volatilidad_anualizada = retornos_diarios.std() * (252 ** 0.5) * 100
            retornos_promedio_anual = retornos_diarios.mean() * 252 * 100
            sharpe_ratio = retornos_promedio_anual / volatilidad_anualizada

            senales = {}
            links_yahoo = {} 
            
            for columna in datos_precios.columns:
                ma_rapida = datos_precios[columna].rolling(window=10, min_periods=1).mean()
                ma_lenta = datos_precios[columna].rolling(window=50, min_periods=1).mean()
                senales[columna] = "COMPRAR 🟢" if ma_rapida.iloc[-1] >= ma_lenta.iloc[-1] else "VENDER 🔴"
                
                ticker_actual = ticker_puro.get(columna, "")
                links_yahoo[columna] = f"https://es.finance.yahoo.com/quote/{ticker_actual}"

            # Construcción del DataFrame ordenado
            tabla_indicadores = pd.DataFrame({
                'Ver en Yahoo': pd.Series(links_yahoo), 
                'Rendimiento Total (%)': rendimiento_total,
                'Volatilidad Anualizada (%)': volatilidad_anualizada,
                'Ratio de Sharpe': sharpe_ratio,
                'Señal Actual': pd.Series(senales)
            }).sort_values(by='Ratio de Sharpe', ascending=False)
            
            columnas_num = ['Rendimiento Total (%)', 'Volatilidad Anualizada (%)', 'Ratio de Sharpe']
            tabla_indicadores[columnas_num] = tabla_indicadores[columnas_num].round(2)

            st.dataframe(
                tabla_indicadores, 
                use_container_width=True,
                column_config={
                    "Ver en Yahoo": st.column_config.LinkColumn(
                        "Detalle 🔗", 
                        display_text="Ver" 
                    )
                }
            )

            # Botón para descargar el reporte Excel
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                tabla_indicadores.to_excel(writer, sheet_name='Indicadores')
            
            st.download_button(
                label="💾 Descargar Reporte Excel",
                data=output.getvalue(),
                file_name=f"reporte_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
else:
    st.info("💡 Por favor, sube tu archivo Excel en la barra lateral para comenzar el análisis.")