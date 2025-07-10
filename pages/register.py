import streamlit as st
import json
import requests
import os

# 설정
INFLUX_URL = "http://192.168.0.7:8086"
ADMIN_PASSWORD = "1234567p"
MOCK_MODE = False  # 실제 연결 시 False
DATA_FILE = "mock_department_data.json"
INFLUXDB_TOKEN = "jr5ymI9x7oX55O5Y6_OY0-aTN0vct61foWoSY5ZOgoPkDSN8COWHmy3RaN_pXDtyBsJ_GmRZGx2xsbUBa_xBIg=="


# 파일 기반 데이터 로딩

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

# UI
st.title("📋 설정")
st.markdown("""
- 부서 및 프로젝트 정보를 등록하면 InfluxDB에 org, bucket, token이 자동 생성됩니다.
- 관리자는 비밀번호로 인증합니다.
""")

org = st.text_input("부서명 (Organization 이름)")
bucket = st.text_input("프로젝트명 (Bucket 이름)")
password = st.text_input("관리자 비밀번호", type="password")

if st.button("등록하기"):
    if not (org and bucket and password):
        st.error("모든 항목을 입력해주세요.")
        st.stop()

    if password != ADMIN_PASSWORD:
        st.error("비밀번호가 틀렸습니다.")
        st.stop()

    data = load_data()
    if org not in data:
        data[org] = {}

    if bucket in data[org]:
        st.warning("이미 등록된 프로젝트입니다.")
    else:
        if MOCK_MODE:
            # 테스트 모드: UUID로 토큰 생성
            import uuid
            mock_token = str(uuid.uuid4())
            data[org][bucket] = {"token": mock_token}
            save_data(data)
            st.success("(Mock) 등록 완료!")
            st.code(json.dumps(data[org][bucket], indent=4))
        else:
            # 실제 InfluxDB 연결
            try:
                headers = {"Authorization": f"Token {token}"} if 'token' in st.session_state else {"Authorization": "Token <root_or_admin_token>"}
                # 1. Org 생성
                org_payload = {"name": org}
                res1 = requests.post(f"{INFLUX_URL}/api/v2/orgs", json=org_payload, headers=headers)
                org_id = res1.json()["id"]

                # 2. Bucket 생성
                bucket_payload = {
                    "name": bucket,
                    "orgID": org_id,
                    "retentionRules": [{"type": "expire", "everySeconds": 0}]
                }
                res2 = requests.post(f"{INFLUX_URL}/api/v2/buckets", json=bucket_payload, headers=headers)
                bucket_id = res2.json()["id"]

                # 3. Token 생성
                token_payload = {
                    "orgID": org_id,
                    "description": f"Token for {org}/{bucket}",
                    "permissions": [
                        {"action": "read", "resource": {"type": "buckets", "id": bucket_id}},
                        {"action": "write", "resource": {"type": "buckets", "id": bucket_id}}
                    ]
                }
                res3 = requests.post(f"{INFLUX_URL}/api/v2/authorizations", json=token_payload, headers=headers)
                generated_token = res3.json()["token"]

                data[org][bucket] = {"token": generated_token}
                save_data(data)
                st.success("등록 완료!")
                st.code(json.dumps(data[org][bucket], indent=4), language="json")
            except Exception as e:
                st.error(f"InfluxDB 연동 오류: {e}")

# 확인용 리스트
st.subheader("📂 등록된 부서/프로젝트 리스트")
data = load_data()
for org, buckets in data.items():
    st.markdown(f"### 🏢 {org}")
    for bucket, info in buckets.items():
        st.markdown(f"- **{bucket}**  | 🔑 Token: `{info['token']}`")
