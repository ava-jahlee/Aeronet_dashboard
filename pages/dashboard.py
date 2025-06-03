import streamlit as st
from influxdb_client import InfluxDBClient
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

# 페이지 설정
st.set_page_config(
    page_title="AeroPup Dashboard",
    page_icon="🐾",
    layout="wide"
)

# InfluxDB 설정
url = "http://10.1.1.45:8086/"
token = "KnTeQgIilv1hmqbHqS8kJKaIDFKlFhz8s5kGJX_E2wL6pWaJI4n-8NzQzKwJDv4xPEcktjeE6Dn0B7GjVVw1YA=="
org = "eantec_ru"
bucket = "Aeropups_4F"

# InfluxDB 연결
try:
    # timeout을 30초 (30000ms)로 설정
    client = InfluxDBClient(url=url, token=token, org=org, timeout=30_000) #
    query_api = client.query_api()
except Exception as e:
    st.error(f"InfluxDB 연결 실패: {e}")
    st.stop()

# 센서 종류와 측정 항목 매핑
sensor_measurement_map = {
    "bme280": ("environment", ["temperature", "humidity", "pressure", "altitude"]),
    "cm1107n": ("airquality", ["CO2"])
}

# InfluxDB 연결
try:
    client = InfluxDBClient(url=url, token=token, org=org)
    query_api = client.query_api()
except Exception as e:
    st.error(f"InfluxDB 연결 실패: {e}")
    st.stop()

# device_id 목록 조회
device_query = f'''
import "influxdata/influxdb/schema"
schema.tagValues(
  bucket: "{bucket}",
  tag: "device_id"
)
'''
device_result = query_api.query_data_frame(device_query)
device_ids = device_result['_value'].dropna().unique().tolist()

# sensor_md 목록 조회
sensor_query = f'''
import "influxdata/influxdb/schema"
schema.tagValues(
  bucket: "{bucket}",
  tag: "sensor_md"
)
'''
sensor_result = query_api.query_data_frame(sensor_query)
sensor_ids = sensor_result['_value'].dropna().unique().tolist()

# 사이드바 UI 구성
st.sidebar.title("👀 AeroPup")
device_id = st.sidebar.selectbox("디바이스 선택", device_ids)
sensor_md = st.sidebar.selectbox("모델 선택", sensor_ids)

# 데이터 범위 선택 옵션
data_range_option = st.sidebar.radio("데이터 범위 선택", ["최근 몇 시간", "날짜/시간 지정"])

if data_range_option == "최근 몇 시간":
    hours = st.sidebar.slider("최근 데이터 보기 (h)", 1, 24, 12)
    # InfluxDB의 range(start:)는 음수 문자열 사용 가능
    range_start = f"-{hours}h"
    range_stop = None
else:
    # 시작/종료 날짜/시간 입력 (시간까지 지정 가능)
    default_start = datetime.now() - timedelta(hours=12)
    
    # 날짜와 시간을 분리하여 입력받음
    start_date = st.sidebar.date_input("시작 날짜", value=default_start.date())
    start_time = st.sidebar.time_input("시작 시간", value=default_start.time())
    end_date = st.sidebar.date_input("종료 날짜", value=datetime.now().date())
    end_time = st.sidebar.time_input("종료 시간", value=datetime.now().time())
    
    # 날짜와 시간을 합쳐서 datetime 객체 생성
    start_dt = datetime.combine(start_date, start_time)
    end_dt = datetime.combine(end_date, end_time)
    
    if start_dt >= end_dt:
        st.error("시작 시간은 종료 시간보다 이전이어야 합니다.")
        st.stop()
    range_start = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    range_stop = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

# 선택된 모델에 따라 measurement와 필드 결정
measurement, fields = sensor_measurement_map.get(sensor_md, (None, []))
if not measurement:
    st.warning("알 수 없는 센서입니다.")
    st.stop()

# 다운로드용 필드명 매핑
field_label_map = {
    "temperature": "온도(Temperature)",
    "humidity": "습도(Humidity)",
    "pressure": "기압(Pressure)",
    "altitude": "고도(Altitude)",
    "CO2": "이산화탄소(CO₂)"
}

selected_sensors_for_download = st.sidebar.multiselect(
    "CSV로 다운로드할 센서 데이터",
    [field_label_map[f] for f in fields],
    []
)

# 쿼리 빌더 함수 (날짜 범위에 따라 start와 stop 적용)
@st.cache_data
def build_query(field, start, stop):
    # range() 구문 동적 생성
    range_clause = f'range(start: {start}' + (f', stop: {stop}' if stop else '') + ')'
    return f'''
    from(bucket: "{bucket}")
      |> {range_clause}
      |> filter(fn: (r) => r._measurement == "{measurement}")
      |> filter(fn: (r) => r._field == "{field}")
      |> filter(fn: (r) => r.device_id == "{device_id}")
      |> filter(fn: (r) => r.sensor_md == "{sensor_md}")
      |> aggregateWindow(every: 1m, fn: mean, createEmpty: false)
      |> yield(name: "mean")
    '''

# 데이터 로딩 함수
@st.cache_data
def load_data(field, start, stop):
    query = build_query(field, start, stop)
    df = query_api.query_data_frame(query)
    if isinstance(df, list):
        df = pd.concat(df)
    if df.empty:
        return None
    df['_time'] = pd.to_datetime(df['_time'])
    df.set_index('_time', inplace=True)
    return df[['_value']].rename(columns={'_value': field})

all_dataframes = {}
for field in fields:
    df = load_data(field, range_start, range_stop)
    if df is not None:
        all_dataframes[field] = df

# 대시보드 제목
st.title(f"🐾 {device_id} 대시보드")

if not all_dataframes:
    st.warning("현재 선택한 디바이스와 시간 범위에 대한 센서 데이터가 없습니다.")
    st.stop()

# 시각화 관련 설정
emozies = {
    "temperature": "🌡️",
    "humidity": "💧",
    "pressure": "🎈",
    "altitude": "⛰️",
    "CO2": "🌫️"
}

colors = {
    "temperature": "#ff0000",
    "humidity": "#00ced1",
    "pressure": "#ff8c00",
    "altitude": "#6b8e23",
    "CO2": "#708090"
}

# 센서별 시각화 처리
if sensor_md.startswith("cm1107"):
    st.subheader("🌫️ CO₂")
    co2 = all_dataframes.get("CO2")
    if co2 is not None:
        latest = co2.iloc[-1][0]
        emoji = "🟢" if latest < 1000 else "🟡" if latest < 2000 else "🔴" if latest < 3000 else "🚨"
        st.metric("현재 CO₂", f"{latest:.1f} ppm", delta=emoji)
        st.line_chart(co2, height=200)
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=latest,
            domain={'x': [0, 1], 'y': [0, 1]},
            title={'text': "CO₂"},
            gauge={
                'bar': {'color': colors["CO2"]},
                'axis': {'range': [0, 5000]}
        }))
        st.plotly_chart(fig, use_container_width=True)
else:
    col1, col2 = st.columns(2)
    with col1:
        for f in ["temperature", "humidity"]:
            if f in all_dataframes:
                st.subheader(emozies[f] + " " + field_label_map[f])
                latest = all_dataframes[f].iloc[-1][0]
                unit = "°C" if f == "temperature" else "%"
                st.metric(f"현재 {field_label_map[f]}", f"{latest:.1f} {unit}")
                st.line_chart(all_dataframes[f], height=200)
    with col2:
        for f in ["pressure", "altitude"]:
            if f in all_dataframes:
                st.subheader(emozies[f] + " " + field_label_map[f])
                latest = all_dataframes[f].iloc[-1][0]
                unit = "hPa" if f == "pressure" else "m"
                st.metric(f"현재 {field_label_map[f]}", f"{latest:.1f} {unit}")
                st.line_chart(all_dataframes[f], height=200)

# CSV 다운로드 기능
default_filename = f"{device_id}_data.csv"
custom_filename = st.sidebar.text_input("📁 저장할 파일 이름 (선택)", value=default_filename)

if selected_sensors_for_download:
    download_frames = []
    for label in selected_sensors_for_download:
        for f, lab in field_label_map.items():
            if lab == label and f in all_dataframes:
                download_frames.append(all_dataframes[f])
    if download_frames:
        csv_data = pd.concat(download_frames, axis=1)
        if csv_data.index.tz is None:
            csv_data = csv_data.tz_localize("UTC")
        csv_data = csv_data.tz_convert("Asia/Seoul")
        csv_data.index.name = "time(Asia/Seoul)"
        csv_string = csv_data.to_csv().encode('utf-8')

        st.sidebar.download_button(
            label="📥 CSV 다운로드",
            data=csv_string,
            file_name=custom_filename if custom_filename else default_filename,
            mime='text/csv'
        )
else:
    st.sidebar.info("CSV로 다운로드할 데이터를 선택해주세요.")

client.close()
