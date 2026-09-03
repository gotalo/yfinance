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

# --- NUEVAS LIBRERÍAS DE PRECIOSHOY.PY ---
import cloudscraper
import re
import urllib3
import ssl
from requests.adapters import HTTPAdapter
from urllib3.util import create_urllib3_context

# Silenciamos las advertencias de SSL inseguro
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configuración de la página web
st.set_page_config(page_title="Acciones", layout="wide")
st.title("📊 Análisis de Activos")

# Configuración de tema de gráficos
sns.set_theme(style="darkgrid")

# --- ADAPTADOR SSL DE PRECIOSHOY.PY ---
class IgnorarSSLAdapter(HTTPAdapter):
    """Adaptador personalizado para apagar drásticamente check_hostname y la verificación"""
    def init_poolmanager(self, *args, **kwargs):
        context = create_urllib3_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        kwargs['ssl_context'] = context
        return super(IgnorarSSLAdapter, self).init_poolmanager(*args, **kwargs)

# --- FUNCIÓN SCRAPER DE PRECIOSHOY.PY ---
def obtener_precio_bono_quicktrade(ticker):
    """Busca el precio del bono burlando check_hostname y SSL"""
    url = f"https://www.quicktrade.com.ar/Bursatil/Especie/{ticker}/MERVAL/Inmed."
    scraper = cloudscraper.create_scraper()
    
    adapter = IgnorarSSLAdapter()
    scraper.mount("https://", adapter)
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'es-ES,es;q=0.9',
        'Referer': 'https://www.quicktrade.com.ar/',
        'Connection': 'keep-alive'
    }
    
    try:
        response = scraper.get(url, headers=headers, timeout=15, verify=False)
        if response.status_code == 200:
            texto_pagina = response.text
            match = re.search(r'"PrecioUltimo":\s*([0-9.]+)', texto_pagina)
            if match:
                precio_texto = match.group(1)
                return round(float(precio_texto), 4)
            return "No parseable"
        return f"Error HTTP {response.status_code}"
    except Exception as e:
        return f"Error: {str(e)}"


# 1. CARGA DEL ARCHIVO EXCEL
st.sidebar.header("Configuración")
archivo_cargado = st.sidebar.file_uploader("Sube 'tickets.xlsx'", type=["xlsx"])

if archivo_cargado is not None:
    df_excel = pd.read_excel(archivo_cargado)
    df_excel.columns = df_excel.columns.str.strip()
    
    # --- FILTRADO HISTÓRICO (Buscar == X) ---
    df_filtrado = df_excel[df_excel['Buscar'].astype(str).str.strip().str.upper() == 'X']

    tickers = {}
    ticker_puro = {} 
    
    for _, fila in df_filtrado.iterrows():
        titulo = f"{str(fila['Descripcion']).strip()}-{str(fila['Tipo']).strip()}-{str(fila['Rubro']).strip()}"
        ticker_yahoo = str(fila['Ticket']).strip()
        tickers[titulo] = ticker_yahoo
        ticker_puro[titulo] = ticker_yahoo 

    # --- FILTRADO PRECIO HOY (Precio == X) ---
    if 'Precio' in df_excel.columns:
        df_filtrado_hoy = df_excel[df_excel['Precio'].astype(str).str.strip().str.upper() == 'X']
    else:
        df_filtrado_hoy = pd.DataFrame()

    st.sidebar.success(f"🎯 Históricos: {len(tickers)} activos | 💰 Tiempo Real: {len(df_filtrado_hoy)} activos.")

   # --- SECCIÓN DE FECHAS EN PANTALLA ---
    hoy = datetime.now()
    hace_un_ano = hoy - timedelta(days=1 * 365)
    
    col_fecha_1, col_fecha_2, col_fecha_3 = st.columns(3)
    
    with col_fecha_1:
        fecha_inicio = st.date_input("Fecha DESDE", value=hace_un_ano)
        INICIO = fecha_inicio.strftime("%Y-%m-%d")
        
    with col_fecha_2:
        fecha_fin = st.date_input("Fecha HASTA", value=hoy - timedelta(days=1))
        fecha_fin_api = fecha_fin + timedelta(days=1)
        FIN = fecha_fin_api.strftime("%Y-%m-%d")
    
    with col_fecha_3:
        st.info(f"📆 Seleccionado: del **{INICIO}** al **{fecha_fin.strftime('%Y-%m-%d')}**")
    
    
    # 2. DESCARGAR DATOS
    datos_precios = pd.DataFrame()
    df_precios_hoy = pd.DataFrame()
    
    with st.spinner("🚀 Descargando datos desde Yahoo Finance y Quicktrade..."):
        # Descarga Histórica
        if not df_filtrado.empty:
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

        # Descarga del Dólar Oficial
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

        
        # --- APLICACIÓN DE LA LÓGICA RELEVANTE DE PRECIOSHOY.PY ---
        lista_precios_hoy = []
        links_hoy = {}  # Diccionario para guardar las URLs sin romper la tabla
        
        if not df_filtrado_hoy.empty:
            for _, fila in df_filtrado_hoy.iterrows():
                activo_ticket = str(fila['Ticket']).strip()
                descripcion = str(fila['Descripcion']).strip()
                tipo = str(fila.get('Tipo', '-')).strip()
                rubro = str(fila.get('Rubro', '-')).strip()
                
                # REGLA CLAVE: Si no tiene punto es un bono local (Quicktrade), si tiene va por Yahoo Finance
                if "." not in activo_ticket:
                    precio_crudo = obtener_precio_bono_quicktrade(activo_ticket)
                    fuente = "Quicktrade"
                    enlace = f"https://www.quicktrade.com.ar/Bursatil/Especie/{activo_ticket}/MERVAL/Inmed."
                    
                    # NUEVO: Si es un número válido de Quicktrade, se divide por 100
                    if isinstance(precio_crudo, (int, float)):
                        precio_actual = round(precio_crudo / 100, 4)
                    else:
                        precio_actual = precio_crudo  # Mantiene el mensaje de error si falló el scrap
                else:
                    fuente = "Yahoo Finance"
                    enlace = f"https://es.finance.yahoo.com/quote/{activo_ticket}"
                    try:
                        asset = yf.Ticker(activo_ticket)
                        info = asset.history(period="1d")
                        if not info.empty:
                            precio_actual = round(info['Close'].iloc[-1], 2)  # Yahoo se mantiene tal cual
                        else:
                            precio_actual = "Sin operación"
                    except Exception:
                        precio_actual = "Error"
                
                # Guardamos la info limpia en la tabla
                lista_precios_hoy.append({
                    "Ticket": activo_ticket,
                    "Descripción": descripcion,
                    "Tipo": tipo,
                    "Rubro": rubro,
                    "Precio Actual": precio_actual,
                    "Fuente": fuente
                })
                # El enlace se vincula únicamente usando el Ticket como clave
                links_hoy[activo_ticket] = enlace
                
            df_precios_hoy = pd.DataFrame(lista_precios_hoy)

    # 3. PROCESAMIENTO HISTÓRICO
    if not datos_precios.empty:
        rendimiento_acumulado = (datos_precios / datos_precios.iloc[0]) * 100
        retornos_diarios = datos_precios.pct_change().dropna()
        matriz_correlacion = retornos_diarios.corr()

        if not df_dolar.empty:
            df_base100_completo = rendimiento_acumulado.join(df_dolar, how='inner')
            df_base100_completo["Dólar Oficial (ARS=X)"] = (df_base100_completo["Dólar Oficial (ARS=X)"] / df_base100_completo["Dólar Oficial (ARS=X)"].iloc[0]) * 100
        else:
            df_base100_completo = rendimiento_acumulado

        tendencia_suavizada_completa = df_base100_completo.rolling(window=20, min_periods=1).mean()


    # --- ORGANIZACIÓN EN SOLAPAS (NUEVA PESTAÑA AL PRINCIPIO) ---
    tab0, tab1, tab2, tab3 = st.tabs([
        "💰 Precios de Hoy",
        "📈 Evolución y Tendencias", 
        "🔥 Correlación", 
        "🏆 Tabla Comparativa y Señales"
    ])

    # --- SOLAPA 0: PRECIOS DE HOY ---
    with tab0:
        st.markdown("**Precios de Mercado en Tiempo Real / Último Cierre**")
        if not df_precios_hoy.empty:
            
            # Clonamos temporalmente para inyectar la columna interactiva de forma visual
            df_visual = df_precios_hoy.copy()
            df_visual["Enlace Fuente"] = df_visual["Ticket"].map(links_hoy)
            
            # Repartimos el espacio en un total de 11 unidades proporcionales fijas
            st.dataframe(
                df_visual, 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "Ticket": st.column_config.Column(width=1),         # Angosto
                    "Descripción": st.column_config.Column(width=3),    # El más ancho
                    "Tipo": st.column_config.Column(width=1),           # Angosto
                    "Rubro": st.column_config.Column(width=2),          # Mediano
                    "Precio Actual": st.column_config.Column(width=1),   # Angosto
                    "Fuente": st.column_config.Column(width=2),         # Mediano
                    "Enlace Fuente": st.column_config.LinkColumn(
                        "Fuente 🔗", 
                        display_text="Ver detalle",
                        width=1                                         # Angosto para el botón
                    )
                }
            )
            
            # Botón exclusivo para bajar los precios del día (limpio, sin links rotos)
            output_hoy = io.BytesIO()
            with pd.ExcelWriter(output_hoy, engine='openpyxl') as writer:
                df_precios_hoy.to_excel(writer, sheet_name='Precios_Hoy', index=False)
            
            st.download_button(
                label="📥 Descargar Extracto Precios de Hoy",
                data=output_hoy.getvalue(),
                file_name=f"precios_hoy_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.info("💡 No hay activos marcados con 'X' en la columna 'Precio' de tu Excel.")


    # --- SOLAPA 1: EVOLUCIÓN Y TENDENCIAS ---
    with tab1:
        if not datos_precios.empty:
            def crear_grafico_interactivo(df_datos, titulo_grafico, eje_y_nombre):
                fig = px.line(df_datos, labels={"value": eje_y_nombre, "index": "Fecha", "variable": "Activo"}, title=titulo_grafico)
                fig.update_layout(
                    legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5),
                    margin=dict(l=20, r=20, t=50, b=100), hovermode="closest", template="plotly_dark"
                )
                return fig

            st.markdown("**Evolución de Precios**")
            datos_precios_con_dolar = datos_precios.join(df_dolar, how='inner') if not df_dolar.empty else datos_precios
            fig_reales = crear_grafico_interactivo(datos_precios_con_dolar, "", "Precio")
            st.plotly_chart(fig_reales, use_container_width=True)
            
            st.write("---")

            st.markdown("**Tendencia Relativa: Media Móvil 20 días (Base 100 vs Variación del Dólar)**")        
            fig_tendencia_vs_usd = crear_grafico_interactivo(tendencia_suavizada_completa, "", "Media Móvil del Rendimiento (%)")
            st.plotly_chart(fig_tendencia_vs_usd, use_container_width=True)
        else:
            st.warning("⚠️ Sube activos con la columna 'Buscar' marcada con 'X' para ver gráficos históricos.")


    # --- SOLAPA 2: CORRELACIÓN  ---
    with tab2:            
        if not datos_precios.empty:
            #st.markdown("### 📊 Matriz Completa de Correlación")
            st.markdown("**Matriz Completa de Correlación**")
            fig_corr = px.imshow(
                matriz_correlacion, 
                text_auto=".2f", 
                color_continuous_scale="RdBu_r", 
                zmin=-1, zmax=1,
                labels=dict(x="Activo", y="Activo", color="Corr")
            )
            fig_corr.update_layout(template="plotly_dark", margin=dict(l=20, r=20, t=50, b=50), height=550)
            st.plotly_chart(fig_corr, use_container_width=True)            

            st.write("---")

            # --- TABLA Y FILTRO DE CORRELACIONES RELEVANTES ---
            #st.markdown("### 🎯 Tabla de Correlaciones Relevantes")
            st.markdown("**Tabla de Correlaciones Relevantes**")
            
            # Control interactivo para seleccionar el umbral
            umbral_corr = st.slider(
                "Filtrar por Umbral de Correlación Mínima (|r|):",
                min_value=0.0, 
                max_value=0.99, 
                value=0.60, 
                step=0.05,
                help="Se mostrarán únicamente los pares cuyo valor absoluto de correlación sea mayor o igual al seleccionado."
            )

            # Extraemos los pares de la matriz eliminando la diagonal principal y los duplicados
            import numpy as np

            mask = np.triu(np.ones(matriz_correlacion.shape), k=1).astype(bool)
            matriz_filtrada = matriz_correlacion.where(mask)
            
            df_pares = matriz_filtrada.stack().reset_index()
            df_pares.columns = ['Activo 1', 'Activo 2', 'Correlación']
            
            df_pares['Valor Absoluto'] = df_pares['Correlación'].abs()

            # Filtrar por el umbral y ordenar de mayor a menor correlación
            df_relevantes = df_pares[df_pares['Valor Absoluto'] >= umbral_corr].sort_values(by='Correlación', ascending=False)

            if not df_relevantes.empty:
                # Mostramos métrica resumen con la cantidad de coincidencias
                st.caption(f"Se encontraron **{len(df_relevantes)}** par(es) de activos con correlación |r| ≥ **{umbral_corr:.2f}**:")
                
                # Formateamos numéricamente la correlación a 2 decimales
                df_mostrar = df_relevantes[['Activo 1', 'Activo 2', 'Correlación']].copy()
                df_mostrar['Correlación'] = df_mostrar['Correlación'].round(2)

                # Mostramos la tabla en pantalla con altura dinámica
                altura_tabla = min(500, (len(df_mostrar) * 35) + 40)
                st.dataframe(
                    df_mostrar,
                    use_container_width=True,
                    hide_index=True,
                    height=altura_tabla,
                    column_config={
                        "Activo 1": st.column_config.Column(width="large"),
                        "Activo 2": st.column_config.Column(width="large"),
                        "Correlación": st.column_config.NumberColumn(
                            "Correlación (r)",
                            format="%.2f"
                        )
                    }
                )
            else:
                st.info(f"💡 No existen pares de activos con correlación mayor o igual a **{umbral_corr:.2f}**. Intenta bajando el filtro.")

        else:
            st.warning("⚠️ No hay suficientes datos históricos para calcular correlaciones.")


    # --- SOLAPA 3: TABLA E INDICADORES ---
    with tab3:
        if not datos_precios.empty:
            st.markdown("**Indicadores y Señales de Inversión**")
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

            tabla_indicadores = pd.DataFrame({
                'Ver en Yahoo': pd.Series(links_yahoo), 
                'Rendimiento Total (%)': rendimiento_total,
                'Volatilidad Anualizada (%)': volatilidad_anualizada,
                'Ratio de Sharpe': sharpe_ratio,
                'Señal Actual': pd.Series(senales)
            }).sort_values(by='Ratio de Sharpe', ascending=False)
            
            columnas_num = ['Rendimiento Total (%)', 'Volatilidad Anualizada (%)', 'Ratio de Sharpe']
            tabla_indicadores[columnas_num] = tabla_indicadores[columnas_num].round(2)
            altura_dinamica = (len(tabla_indicadores) * 35) + 40

            st.dataframe(
                tabla_indicadores, use_container_width=True, height=altura_dinamica,
                column_config={"Ver en Yahoo": st.column_config.LinkColumn("Detalle 🔗", display_text="Ver")}
            )

            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                tabla_indicadores.to_excel(writer, sheet_name='Indicadores')
            
            st.download_button(
                label="💾 Descargar Reporte Excel", data=output.getvalue(),
                file_name=f"reporte_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.warning("⚠️ No hay suficientes datos históricos para armar la tabla de indicadores.")
else:
    st.info("💡 Por favor, sube tu archivo Excel en la barra lateral para comenzar el análisis.")