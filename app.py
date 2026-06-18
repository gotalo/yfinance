import streamlit as dict_streamlit
import streamlit as st
import os
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
import io

# Configuración de la página web
st.set_page_config(page_title="Dashboard de Inversiones", layout="wide")
st.title("📊 Dashboard de Análisis de Activos")

# Configuración de tema de gráficos
sns.set_theme(style="darkgrid")

# 1. CARGA DEL ARCHIVO EXCEL
st.sidebar.header("1. Configuración")
archivo_cargado = st.sidebar.file_uploader("Sube tu archivo 'tickets.xlsx'", type=["xlsx"])

if archivo_cargado is not None:
    df_excel = pd.read_excel(archivo_cargado)
    df_excel.columns = df_excel.columns.str.strip()
    
    # Filtrar filas donde 'Buscar' sea 'X'
    df_filtrado = df_excel[df_excel['Buscar'].astype(str).str.strip().str.upper() == 'X']

    tickers = {}
    # --- NUEVO: Guardamos una relación directa del Nombre con su Ticker limpio ---
    ticker_puro = {} 
    
    for _, fila in df_filtrado.iterrows():
        titulo = f"{str(fila['Descripcion']).strip()}-{str(fila['Tipo']).strip()}-{str(fila['Rubro']).strip()}"
        ticker_yahoo = str(fila['Ticket']).strip()
        tickers[titulo] = ticker_yahoo
        ticker_puro[titulo] = ticker_yahoo # Guardamos para armar el link después

    st.sidebar.success(f"🎯 Se cargaron {len(tickers)} activos.")

    # --- NUEVA SECCIÓN DE FECHAS EN PANTALLA ---
    st.header("📅 Rango de Fechas del Análisis")
    
    # Calcular fechas por defecto (hace 2 años hasta ayer)
    ayer = datetime.now() - timedelta(days=1)
    hace_dos_anos = ayer - timedelta(days=1 * 365)
    
    # Creamos dos columnas en la pantalla principal para mostrar y seleccionar las fechas
    col_fecha_1, col_fecha_2 = st.columns(2)
    
    with col_fecha_1:
        fecha_inicio = st.date_input("Fecha DESDE", value=hace_dos_anos)
        INICIO = fecha_inicio.strftime("%Y-%m-%d")
        
    with col_fecha_2:
        fecha_fin = st.date_input("Fecha HASTA", value=ayer)
        FIN = fecha_fin.strftime("%Y-%m-%d")
        
    # Muestra un texto informativo con las fechas seleccionadas
    st.info(f"📆 Analizando datos desde el **{INICIO}** hasta el **{FIN}**")
    


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
                
                # Manejo de MultiIndex o columnas simples de yfinance
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)

                if 'Adj Close' in df.columns:
                    datos_precios[nombre] = df['Adj Close']
                else:
                    datos_precios[nombre] = df['Close']
            except Exception as e:
                st.error(f"❌ Error con {nombre}: {e}")

        if not datos_precios.empty:
            datos_precios = datos_precios.ffill().bfill()

    if not datos_precios.empty:
        # 3. PROCESAMIENTO
        rendimiento_acumulado = (datos_precios / datos_precios.iloc[0]) * 100
        retornos_diarios = datos_precios.pct_change().dropna()
        matriz_correlacion = retornos_diarios.corr()

        # --- NUEVA ORGANIZACIÓN EN SOLAPAS (TABS) ---
        st.header("📊 Resultados del Análisis")

        # Creamos 3 solapas
        tab1, tab2, tab3 = st.tabs([
            "📈 Evolución y Tendencias", 
            "🔥 Correlación", 
            "🏆 Tabla Comparativa y Señales"
        ])

        # --- SOLAPA 1: EVOLUCIÓN Y TENDENCIAS ---
        with tab1:
            st.subheader("Análisis de Precios Normalizados")
            col1, col2 = st.columns(2)

            with col1:
                fig1, ax1 = plt.subplots(figsize=(10, 6))
                for columna in rendimiento_acumulado.columns:
                    ax1.plot(rendimiento_acumulado.index, rendimiento_acumulado[columna], label=columna, linewidth=2)
                ax1.set_title("Evolución (Base 100)", fontsize=12, fontweight='bold')
                ax1.legend(loc="upper left")
                st.pyplot(fig1)

            with col2:
                fig1b, ax1b = plt.subplots(figsize=(10, 6))
                tendencia_suavizada = rendimiento_acumulado.rolling(window=100, min_periods=1).mean()
                for columna in tendencia_suavizada.columns:
                    ax1b.plot(tendencia_suavizada.index, tendencia_suavizada[columna], label=columna, linewidth=2.5)
                ax1b.set_title("Tendencia (Media Móvil 100 días)", fontsize=12, fontweight='bold')
                ax1b.legend(loc="upper left")
                st.pyplot(fig1b)

        # --- SOLAPA 2: CORRELACIÓN ---
        with tab2:
            st.subheader("Matriz de Correlación de Retornos Diarios")
            fig2, ax2 = plt.subplots(figsize=(8, 4))
            sns.heatmap(matriz_correlacion, annot=True, cmap="coolwarm", vmin=-1, vmax=1, fmt=".2f", ax=ax2)
            st.pyplot(fig2)

        # --- SOLAPA 3: TABLA E INDICADORES ---
        with tab3:
            st.subheader("Indicadores Avanzados y Señales de Inversión")
            
            # Cálculo de métricas
            rendimiento_total = (datos_precios.iloc[-1] / datos_precios.iloc[0] - 1) * 100
            volatilidad_anualizada = retornos_diarios.std() * (252 ** 0.5) * 100
            retornos_promedio_anual = retornos_diarios.mean() * 252 * 100
            sharpe_ratio = retornos_promedio_anual / volatilidad_anualizada

            senales = {}
            links_yahoo = {} # Diccionario temporal para guardar las URLs
            
            for columna in datos_precios.columns:
                ma_rapida = datos_precios[columna].rolling(window=10, min_periods=1).mean()
                ma_lenta = datos_precios[columna].rolling(window=50, min_periods=1).mean()
                senales[columna] = "COMPRAR 🟢" if ma_rapida.iloc[-1] >= ma_lenta.iloc[-1] else "VENDER 🔴"
                
                # --- NUEVO: Construcción de la URL dinámica ---
                ticker_actual = ticker_puro.get(columna, "")
                links_yahoo[columna] = f"https://es.finance.yahoo.com/quote/{ticker_actual}"

            # Construcción del DataFrame ordenado
            tabla_indicadores = pd.DataFrame({
                'Ver en Yahoo': pd.Series(links_yahoo), # Insertada al principio
                'Rendimiento Total (%)': rendimiento_total,
                'Volatilidad Anualizada (%)': volatilidad_anualizada,
                'Ratio de Sharpe': sharpe_ratio,
                'Señal Actual': pd.Series(senales)
            }).sort_values(by='Ratio de Sharpe', ascending=False)
            
            # Redondeamos solo numéricos para no romper los strings de links o señales
            columnas_num = ['Rendimiento Total (%)', 'Volatilidad Anualizada (%)', 'Ratio de Sharpe']
            tabla_indicadores[columnas_num] = tabla_indicadores[columnas_num].round(2)

            # --- NUEVO: Mostrar tabla interactiva configurando la columna como Link ---
            st.dataframe(
                tabla_indicadores, 
                use_container_width=True,
                column_config={
                    "Ver en Yahoo": st.column_config.LinkColumn(
                        "Detalle 🔗", 
                        display_text="Ver" # Texto alternativo para que no se vea una URL kilométrica
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