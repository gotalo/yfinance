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
    for _, fila in df_filtrado.iterrows():
        titulo = f"{str(fila['Descripcion']).strip()}-{str(fila['Tipo']).strip()}-{str(fila['Rubro']).strip()}"
        ticker_yahoo = str(fila['Ticket']).strip()
        tickers[titulo] = ticker_yahoo

    st.sidebar.success(f"🎯 Se cargaron {len(tickers)} activos.")

    # Fechas automáticas
    ayer = datetime.now() - timedelta(days=1)
    FIN = ayer.strftime("%Y-%m-%d")
    INICIO = (ayer - timedelta(days=2 * 365)).strftime("%Y-%m-%d")

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

        # --- SECCIÓN DE GRÁFICOS ---
        st.header("📈 Análisis Visual")
        
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Evolución de Precios Normalizados")
            fig1, ax1 = plt.subplots(figsize=(10, 5))
            for columna in rendimiento_acumulado.columns:
                ax1.plot(rendimiento_acumulado.index, rendimiento_acumulado[columna], label=columna, linewidth=2)
            ax1.set_title("Base 100", fontsize=12, fontweight='bold')
            ax1.legend(loc="upper left")
            st.pyplot(fig1)

        with col2:
            st.subheader("Tendencia (Media Móvil 100 días)")
            fig1b, ax1b = plt.subplots(figsize=(10, 5))
            tendencia_suavizada = rendimiento_acumulado.rolling(window=100, min_periods=1).mean()
            for columna in tendencia_suavizada.columns:
                ax1b.plot(tendencia_suavizada.index, tendencia_suavizada[columna], label=columna, linewidth=2.5)
            ax1b.legend(loc="upper left")
            st.pyplot(fig1b)

        st.subheader("🔥 Matriz de Correlación")
        fig2, ax2 = plt.subplots(figsize=(8, 4))
        sns.heatmap(matriz_correlacion, annot=True, cmap="coolwarm", vmin=-1, vmax=1, fmt=".2f", ax=ax2)
        st.pyplot(fig2)

        # 4. INDICADORES Y SEÑALES
        st.header("🏆 Tabla Comparativa de Inversión")
        
        rendimiento_total = (datos_precios.iloc[-1] / datos_precios.iloc[0] - 1) * 100
        volatilidad_anualizada = retornos_diarios.std() * (252 ** 0.5) * 100
        retornos_promedio_anual = retornos_diarios.mean() * 252 * 100
        sharpe_ratio = retornos_promedio_anual / volatilidad_anualizada

        senales = {}
        for columna in datos_precios.columns:
            ma_rapida = datos_precios[columna].rolling(window=10, min_periods=1).mean()
            ma_lenta = datos_precios[columna].rolling(window=50, min_periods=1).mean()
            senales[columna] = "COMPRAR 🟢" if ma_rapida.iloc[-1] >= ma_lenta.iloc[-1] else "VENDER 🔴"

        tabla_indicadores = pd.DataFrame({
            'Rendimiento Total (%)': rendimiento_total,
            'Volatilidad Anualizada (%)': volatilidad_anualizada,
            'Ratio de Sharpe': sharpe_ratio,
            'Señal Actual': pd.Series(senales)
        }).sort_values(by='Ratio de Sharpe', ascending=False).round(2)

        # Mostrar tabla interactiva en la web
        st.dataframe(tabla_indicadores, use_container_width=True)

        # Botón para descargar el reporte Excel creado en memoria
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