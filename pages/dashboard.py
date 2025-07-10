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
url = "http://192.168.0.15:8086"
token = "KnTeQgIilv1hmqbHqS8kJKaIDFKlFhz8s5kGJX_E2wL6pWaJI4n-8NzQzKwJDv4xPEcktjeE6Dn0B7GjVVw1YA=="
org = "eantec_ru"
bucket = "Aeropups_6F"

# InfluxDB 연결
try:
    client = InfluxDBClient(url=url, token=token, org=org)
    query_api = client.query_api()
except Exception as e:
    st.error(f"InfluxDB 연결 실패: {e}")
    st.stop()

# sensor_md 목록 조회
sensor_query = f'''
import "influxdata/influxdb/schema"
schema.tagValues(
  bucket: "{bucket}",
  tag: "sensor_md"
)
'''
try:
    sensor_result = query_api.query_data_frame(sensor_query)
    sensor_ids = sensor_result['_value'].dropna().unique().tolist()
except Exception as e:
    st.error(f"센서 목록 조회 실패: {e}")
    st.stop()

# 사이드바 UI 구성
st.sidebar.title("👀 AeroPup")
sensor_md = st.sidebar.selectbox("센서 모델 선택", sensor_ids)

# 선택된 센서에 해당하는 device_id 목록 조회
device_query = f'''
import "influxdata/influxdb/schema"
schema.tagValues(
  bucket: "{bucket}",
  tag: "device_id"
)
'''
try:
    device_result = query_api.query_data_frame(device_query)
    all_device_ids = device_result['_value'].dropna().unique().tolist()
    
    # 선택된 센서를 사용하는 디바이스만 필터링
    device_filter_query = f'''
    from(bucket: "{bucket}")
      |> range(start: -1h)
      |> filter(fn: (r) => r.sensor_md == "{sensor_md}")
      |> group(columns: ["device_id"])
      |> distinct(column: "device_id")
    '''
    device_filter_result = query_api.query_data_frame(device_filter_query)
    if not device_filter_result.empty:
        available_device_ids = device_filter_result['device_id'].dropna().unique().tolist()
    else:
        available_device_ids = all_device_ids
    
    device_id = st.sidebar.selectbox("디바이스 선택", available_device_ids)
except Exception as e:
    st.error(f"디바이스 목록 조회 실패: {e}")
    st.stop()

# 선택된 디바이스와 센서의 실제 필드 목록 조회
field_query = f'''
import "influxdata/influxdb/schema"
schema.fieldKeys(
  bucket: "{bucket}",
  predicate: (r) => r._measurement == "environment"
)
'''
try:
    field_result = query_api.query_data_frame(field_query)
    environment_fields = field_result['_value'].dropna().unique().tolist()
    
    field_result = query_api.query_data_frame(field_query.replace('measurement: "environment"', 'measurement: "airquality"'))
    airquality_fields = field_result['_value'].dropna().unique().tolist()
    
    # 실제 데이터에서 사용되는 필드만 확인
    actual_fields_query = f'''
    from(bucket: "{bucket}")
      |> range(start: -1h)
      |> filter(fn: (r) => r.device_id == "{device_id}")
      |> filter(fn: (r) => r.sensor_md == "{sensor_md}")
      |> group(columns: ["_field"])
      |> distinct(column: "_field")
    '''
    actual_fields_result = query_api.query_data_frame(actual_fields_query)
    available_fields = actual_fields_result['_field'].dropna().unique().tolist()
    
    st.sidebar.info(f"사용 가능한 필드: {', '.join(available_fields)}")
    
except Exception as e:
    st.error(f"필드 목록 조회 실패: {e}")
    st.stop()

# 데이터 범위 선택 옵션
data_range_option = st.sidebar.radio("데이터 범위 선택", ["최근 몇 시간", "날짜/시간 지정"])

if data_range_option == "최근 몇 시간":
    hours = st.sidebar.slider("최근 데이터 보기 (h)", 1, 24, 12)
    range_start = f"-{hours}h"
    range_stop = None
else:
    default_start = datetime.now() - timedelta(hours=12)
    start_date = st.sidebar.date_input("시작 날짜", value=default_start.date())
    start_time = st.sidebar.time_input("시작 시간", value=default_start.time())
    end_date = st.sidebar.date_input("종료 날짜", value=datetime.now().date())
    end_time = st.sidebar.time_input("종료 시간", value=datetime.now().time())
    
    start_dt = datetime.combine(start_date, start_time)
    end_dt = datetime.combine(end_date, end_time)
    
    if start_dt >= end_dt:
        st.error("시작 시간은 종료 시간보다 이전이어야 합니다.")
        st.stop()
    range_start = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    range_stop = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

# 다운로드용 필드명 매핑 (동적으로 확장)
field_label_map = {
    "temperature": "온도(Temperature)",
    "humidity": "습도(Humidity)",
    "pressure": "기압(Pressure)",
    "altitude": "고도(Altitude)",
    "CO2": "이산화탄소(CO₂)",
    "AQI": "대기질지수(AQI)",
    "eCO2": "등가CO₂(eCO₂)",
    "tVOC": "총휘발성유기화합물(tVOC)",
    "PM10": "미세먼지(PM10)",
    "PM2_5": "초미세먼지(PM2.5)",
    "PM1_0": "극미세먼지(PM1.0)"
}

# 사용 가능한 필드에 대한 라벨 생성
available_field_labels = []
for field in available_fields:
    if field in field_label_map:
        available_field_labels.append(field_label_map[field])
    else:
        available_field_labels.append(f"{field}")

selected_sensors_for_download = st.sidebar.multiselect(
    "CSV로 다운로드할 센서 데이터",
    available_field_labels,
    []
)

# 쿼리 빌더 함수
@st.cache_data
def build_query(field, start, stop):
    range_clause = f'range(start: {start}' + (f', stop: {stop}' if stop else '') + ')'
    return f'''
    from(bucket: "{bucket}")
      |> {range_clause}
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
    try:
        df = query_api.query_data_frame(query)
        if isinstance(df, list):
            df = pd.concat(df)
        if df.empty:
            return None
        df['_time'] = pd.to_datetime(df['_time'])
        df.set_index('_time', inplace=True)
        return df[['_value']].rename(columns={'_value': field})
    except Exception as e:
        st.error(f"데이터 로딩 실패 ({field}): {e}")
        return None

# 모든 필드에 대해 데이터 로딩
all_dataframes = {}
for field in available_fields:
    df = load_data(field, range_start, range_stop)
    if df is not None:
        all_dataframes[field] = df

# 대시보드 제목
st.title(f"🐾 {device_id} 대시보드")
st.subheader(f"센서: {sensor_md}")

if not all_dataframes:
    st.warning("현재 선택한 디바이스와 시간 범위에 대한 센서 데이터가 없습니다.")
    st.stop()

# 시각화 관련 설정
emozies = {
    "temperature": "🌡️",
    "humidity": "💧",
    "pressure": "🎈",
    "altitude": "⛰️",
    "CO2": "🌫️",
    "AQI": "🌤️",
    "eCO2": "🌫️",
    "tVOC": "💨",
    "PM10": "🌫️",
    "PM2_5": "🌫️",
    "PM1_0": "🌫️"
}

colors = {
    "temperature": "#ff0000",
    "humidity": "#00ced1",
    "pressure": "#ff8c00",
    "altitude": "#6b8e23",
    "CO2": "#708090",
    "AQI": "#ff6b6b",
    "eCO2": "#4ecdc4",
    "tVOC": "#45b7d1",
    "PM10": "#96ceb4",
    "PM2_5": "#feca57",
    "PM1_0": "#ff9ff3"
}

# 동적 시각화 생성
st.subheader("📊 센서 데이터 시각화")

# 필드를 그룹화하여 표시
environment_fields = ["temperature", "humidity", "pressure", "altitude"]
airquality_fields = ["CO2", "AQI", "eCO2", "tVOC", "PM10", "PM2_5", "PM1_0"]

# 환경 센서 데이터 표시
env_fields = [f for f in available_fields if f in environment_fields]
if env_fields:
    st.subheader("🌍 환경 센서")
    cols = st.columns(min(len(env_fields), 2))
    for i, field in enumerate(env_fields):
        if field in all_dataframes:
            with cols[i % 2]:
                emoji = emozies.get(field, "📊")
                label = field_label_map.get(field, field)
                latest = all_dataframes[field].iloc[-1][0]
                unit = "°C" if field == "temperature" else "%" if field == "humidity" else "hPa" if field == "pressure" else "m"
                st.metric(f"{emoji} {label}", f"{latest:.1f} {unit}")
                st.line_chart(all_dataframes[field], height=200)

# 공기질 센서 데이터 표시
aq_fields = [f for f in available_fields if f in airquality_fields]
if aq_fields:
    st.subheader("🌬️ 공기질 센서")
    cols = st.columns(min(len(aq_fields), 2))
    for i, field in enumerate(aq_fields):
        if field in all_dataframes:
            with cols[i % 2]:
                emoji = emozies.get(field, "📊")
                label = field_label_map.get(field, field)
                latest = all_dataframes[field].iloc[-1][0]
                
                # CO2 특별 처리
                if field == "CO2":
                    emoji_status = "🟢" if latest < 1000 else "🟡" if latest < 2000 else "🔴" if latest < 3000 else "🚨"
                    st.metric(f"{emoji} {label}", f"{latest:.1f} ppm", delta=emoji_status)
                    
                    # CO2 게이지 차트
                    fig = go.Figure(go.Indicator(
                        mode="gauge+number",
                        value=latest,
                        domain={'x': [0, 1], 'y': [0, 1]},
                        title={'text': "CO₂"},
                        gauge={
                            'bar': {'color': colors.get(field, "#708090")},
                            'axis': {'range': [0, 5000]},
                            'steps': [
                                {'range': [0, 1000], 'color': "lightgreen"},
                                {'range': [1000, 2000], 'color': "yellow"},
                                {'range': [2000, 3000], 'color': "orange"},
                                {'range': [3000, 5000], 'color': "red"}
                            ]
                        }
                    ))
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.metric(f"{emoji} {label}", f"{latest:.1f}")
                    st.line_chart(all_dataframes[field], height=200)

# CSV 다운로드 기능
default_filename = f"{device_id}_{sensor_md}_data.csv"
custom_filename = st.sidebar.text_input("📁 저장할 파일 이름 (선택)", value=default_filename)

if selected_sensors_for_download:
    download_frames = []
    for label in selected_sensors_for_download:
        for f, lab in field_label_map.items():
            if lab == label and f in all_dataframes:
                download_frames.append(all_dataframes[f])
    
    if download_frames:
        combined_df = pd.concat(download_frames, axis=1)
        csv_data = combined_df.to_csv()
        
        st.sidebar.download_button(
            label="📥 CSV 다운로드",
            data=csv_data,
            file_name=custom_filename,
            mime="text/csv"
        )

client.close()
