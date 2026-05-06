import streamlit as st
import geopandas as gpd
import pandas as pd
import matplotlib.pyplot as plt
import io
import matplotlib.font_manager as fm
import math
import folium
from streamlit_folium import st_folium



st.set_page_config(page_title="교육용 지도 생성기", layout="wide")
st.title("교육용 지도 생성기")

with st.expander("사용법 보기", expanded=False):
    st.markdown(
        """
        - **탐색 모드**에서 지도를 확대/이동해 원하는 범위를 찾고 **탐색 좌표 저장**을 누릅니다.
        - **제작 모드**에서 **저장 좌표 불러오기**를 누르면 탐색한 범위가 적용됩니다.
        - **지도 프리셋**은 세계지도, 유럽, 아시아 등 기본 범위를 빠르게 적용할 때 사용합니다.
        - **라벨 설정**에서 지도만 보기, 국가명 보이기, 번호 보이기를 선택할 수 있습니다.
        - **선으로 빼기**를 켜면 작은 국가의 번호를 바깥으로 분리하고 선으로 연결합니다.
        - **국가 강조**에서 G7, G20, EU 같은 국가 묶음을 색으로 표시할 수 있습니다.
        - **해당 국가만 보기**를 끄면 강조 국가뿐 아니라 다른 국가 이름도 함께 표시됩니다.
        - 완성된 지도는 **PNG, SVG, PDF**로 다운로드할 수 있습니다.
        """
    )


# -----------------------------
# 폰트 설정
# -----------------------------
FONT_PATH = "fonts/NanumGothic.otf"

fm.fontManager.addfont(FONT_PATH)
font_prop = fm.FontProperties(fname=FONT_PATH)

plt.rcParams["font.family"] = font_prop.get_name()
plt.rcParams["axes.unicode_minus"] = False


@st.cache_data
def load_data():
    world = gpd.read_file("zip://data/ne_110m_admin_0_countries.zip")
    ko_df = pd.read_csv("country_ko.csv")
    country_ko = dict(zip(ko_df["ADMIN"], ko_df["KO"]))
    world["KO"] = world["ADMIN"].map(country_ko)
    return world


world = load_data()

# -----------------------------
# 프리셋
# -----------------------------
presets = {
    "세계지도": (-180.0, 180.0, -90.0, 90.0),
    "유럽": (-10.0, 70.0, 25.0, 70.0),
    "아시아": (25.0, 150.0, -10.0, 60.0),
    "아프리카": (-20.0, 55.0, -40.0, 40.0),
    "북아메리카": (-170.0, -50.0, 5.0, 75.0),
    "남아메리카": (-90.0, -30.0, -60.0, 15.0),
    "오세아니아": (100.0, 180.0, -50.0, 10.0),
}

st.sidebar.header("지도 프리셋")

view_mode = st.sidebar.radio(
    "작업 모드",
    ["제작 모드", "탐색 모드"],
    index=0
)

preset_name = st.sidebar.selectbox(
    "프리셋 선택",
    list(presets.keys()),
    index=0
)

preset_x_min, preset_x_max, preset_y_min, preset_y_max = presets[preset_name]

# -----------------------------
# 지도 범위 / 세션 상태
# -----------------------------
if "x_min" not in st.session_state:
    st.session_state.x_min = preset_x_min
    st.session_state.x_max = preset_x_max
    st.session_state.y_min = preset_y_min
    st.session_state.y_max = preset_y_max

if "saved_view" not in st.session_state:
    st.session_state.saved_view = None

if "explore_view" not in st.session_state:
    st.session_state.explore_view = None

A4_LANDSCAPE_RATIO = 297 / 210


def fit_view_to_ratio(x_min, x_max, y_min, y_max, target_ratio=A4_LANDSCAPE_RATIO):
    width = x_max - x_min
    height = y_max - y_min

    if width <= 0 or height <= 0:
        return x_min, x_max, y_min, y_max

    center_x = (x_min + x_max) / 2
    center_y = (y_min + y_max) / 2

    current_ratio = width / height

    if current_ratio > target_ratio:
        height = width / target_ratio
    else:
        width = height * target_ratio

    max_width = 360.0
    max_height = 180.0

    if height > max_height:
        height = max_height
        width = height * target_ratio

    if width > max_width:
        width = max_width
        height = width / target_ratio

    x_min = center_x - width / 2
    x_max = center_x + width / 2
    y_min = center_y - height / 2
    y_max = center_y + height / 2

    if x_min < -180:
        x_max += -180 - x_min
        x_min = -180
    if x_max > 180:
        x_min -= x_max - 180
        x_max = 180

    if y_min < -90:
        y_max += -90 - y_min
        y_min = -90
    if y_max > 90:
        y_min -= y_max - 90
        y_max = 90

    return x_min, x_max, y_min, y_max



def apply_view(x_min, x_max, y_min, y_max):
    if x_min >= x_max or y_min >= y_max:
        st.sidebar.error("좌표 범위가 올바르지 않습니다.")
        return

    x_min, x_max, y_min, y_max = fit_view_to_ratio(
        x_min,
        x_max,
        y_min,
        y_max
    )

    st.session_state.x_min = x_min
    st.session_state.x_max = x_max
    st.session_state.y_min = y_min
    st.session_state.y_max = y_max
    st.rerun()



def clamp_view(x_min, x_max, y_min, y_max):
    x_min = max(-180.0, min(180.0, x_min))
    x_max = max(-180.0, min(180.0, x_max))
    y_min = max(-90.0, min(90.0, y_min))
    y_max = max(-90.0, min(90.0, y_max))
    return x_min, x_max, y_min, y_max


def get_center(bounds):
    x_min, x_max, y_min, y_max = bounds
    return [(y_min + y_max) / 2, (x_min + x_max) / 2]


current_bounds = (
    st.session_state.x_min,
    st.session_state.x_max,
    st.session_state.y_min,
    st.session_state.y_max
)

if st.sidebar.button("프리셋 좌표 적용"):
    apply_view(
        preset_x_min,
        preset_x_max,
        preset_y_min,
        preset_y_max
    )


# =============================
# 탐색 모드: 실제 화면 bounds 저장
# =============================
if view_mode == "탐색 모드":

    st.sidebar.header("탐색 좌표")

    if st.session_state.explore_view is None:
        st.sidebar.caption("지도를 이동하거나 확대하면 현재 화면 좌표를 저장할 수 있습니다.")
    else:
        ex_x_min, ex_x_max, ex_y_min, ex_y_max = st.session_state.explore_view

        st.sidebar.caption(
            f"현재 탐색 화면\n\n"
            f"X: {ex_x_min:.2f} ~ {ex_x_max:.2f}\n\n"
            f"Y: {ex_y_min:.2f} ~ {ex_y_max:.2f}"
        )

        if st.sidebar.button("탐색 좌표 저장"):
            st.session_state.saved_view = fit_view_to_ratio(
                *st.session_state.explore_view
)
            st.sidebar.success("탐색 좌표 저장 완료")


# =============================
# 제작 모드: 저장 좌표 불러오기
# =============================
if view_mode == "제작 모드":

    st.sidebar.header("저장된 탐색 좌표")

    if st.session_state.saved_view is None:
        st.sidebar.caption("아직 저장된 탐색 좌표가 없습니다.")
    else:
        saved_x_min, saved_x_max, saved_y_min, saved_y_max = st.session_state.saved_view

        st.sidebar.caption(
            f"X: {saved_x_min:.2f} ~ {saved_x_max:.2f}\n\n"
            f"Y: {saved_y_min:.2f} ~ {saved_y_max:.2f}"
        )

        if st.sidebar.button("저장 좌표 불러오기"):
            apply_view(
                saved_x_min,
                saved_x_max,
                saved_y_min,
                saved_y_max
            )


x_min = st.session_state.x_min
x_max = st.session_state.x_max
y_min = st.session_state.y_min
y_max = st.session_state.y_max

# -----------------------------
# 국가 강조 프리셋
# -----------------------------
highlight_presets = {
    "없음": [],

    "G7": [
        "Canada",
        "France",
        "Germany",
        "Italy",
        "Japan",
        "United Kingdom",
        "United States of America",
    ],

    "G20": [
        "Argentina",
        "Australia",
        "Brazil",
        "Canada",
        "China",
        "France",
        "Germany",
        "India",
        "Indonesia",
        "Italy",
        "Japan",
        "Mexico",
        "Russia",
        "Saudi Arabia",
        "South Africa",
        "South Korea",
        "Turkey",
        "United Kingdom",
        "United States of America",
    ],

    "EU": [
        "Austria",
        "Belgium",
        "Bulgaria",
        "Croatia",
        "Cyprus",
        "Czechia",
        "Denmark",
        "Estonia",
        "Finland",
        "France",
        "Germany",
        "Greece",
        "Hungary",
        "Ireland",
        "Italy",
        "Latvia",
        "Lithuania",
        "Luxembourg",
        "Malta",
        "Netherlands",
        "Poland",
        "Portugal",
        "Romania",
        "Slovakia",
        "Slovenia",
        "Spain",
        "Sweden",
    ],

    "NATO": [
        "Albania",
        "Belgium",
        "Bulgaria",
        "Canada",
        "Croatia",
        "Czechia",
        "Denmark",
        "Estonia",
        "Finland",
        "France",
        "Germany",
        "Greece",
        "Hungary",
        "Iceland",
        "Italy",
        "Latvia",
        "Lithuania",
        "Luxembourg",
        "Montenegro",
        "Netherlands",
        "North Macedonia",
        "Norway",
        "Poland",
        "Portugal",
        "Romania",
        "Slovakia",
        "Slovenia",
        "Spain",
        "Sweden",
        "Turkey",
        "United Kingdom",
        "United States of America",
    ],

    "BRICS": [
        "Brazil",
        "Russia",
        "India",
        "China",
        "South Africa",
        "Egypt",
        "Ethiopia",
        "Iran",
        "United Arab Emirates",
    ],

    "ASEAN": [
        "Brunei",
        "Cambodia",
        "Indonesia",
        "Laos",
        "Malaysia",
        "Myanmar",
        "Philippines",
        "Singapore",
        "Thailand",
        "Vietnam",
    ],

    "발트 3국": [
        "Estonia",
        "Latvia",
        "Lithuania",
    ],

    "북유럽": [
        "Norway",
        "Sweden",
        "Finland",
        "Denmark",
        "Iceland",
    ],

    "한중일": [
        "South Korea",
        "China",
        "Japan",
    ],
}

# -----------------------------
# 항상 표시할 국가
# -----------------------------
must_show = [
    "South Korea",
    "North Korea",
    "Japan",
    "Taiwan",
    "Singapore",
    "Israel",
    "Lebanon",
    "Jordan",
    "Qatar",
    "Kuwait",
    "United Arab Emirates",
    "United Kingdom",
    "Ireland",
    "Belgium",
    "Netherlands",
    "Luxembourg",
    "Switzerland",
    "Denmark",
    "Czechia",
    "Slovakia",
    "Slovenia",
    "Croatia",
    "Bosnia and Herzegovina",
    "Montenegro",
    "Kosovo",
    "Albania",
    "North Macedonia",
    "Estonia",
    "Latvia",
    "Lithuania",
    "Armenia",
    "Azerbaijan",
    "Georgia",
    "The Bahamas",
    "Jamaica",
    "Trinidad and Tobago",
    "New Zealand",
]

# -----------------------------
# 라벨 설정
# -----------------------------
st.sidebar.header("라벨 설정")

label_mode = st.sidebar.selectbox(
    "라벨 종류",
    ["지도만 보기", "국가명 보이기", "번호 보이기"],
    index=0
)

use_leader_lines = st.sidebar.checkbox(
    "선으로 빼기",
    value=True
)

with st.sidebar.expander("상세 라벨 설정", expanded=False):

    label_font_size = st.slider(
        "국가명 크기",
        min_value=3.0,
        max_value=12.0,
        value=6.0,
        step=0.5
    )

    number_font_size = st.slider(
        "번호 크기",
        min_value=3.0,
        max_value=10.0,
        value=4.8,
        step=0.2
    )

    circle_pad = st.slider(
        "번호 원 크기",
        min_value=0.02,
        max_value=0.30,
        value=0.06,
        step=0.01
    )

    number_min_dist = st.slider(
        "번호 최소 거리",
        min_value=1.0,
        max_value=8.0,
        value=2.4,
        step=0.1
    )

    small_area = st.slider(
        "작은 국가 기준",
        min_value=1.0,
        max_value=30.0,
        value=1.0,
        step=0.5
    )

    leader_line_width = st.slider(
        "선 굵기",
        min_value=0.05,
        max_value=2.0,
        value=0.32,
        step=0.05
    )

    leader_line_alpha = st.slider(
        "선 진하기",
        min_value=0.05,
        max_value=1.0,
        value=0.60,
        step=0.05
    )

# -----------------------------
# 국가 강조
# -----------------------------
st.sidebar.header("국가 강조")

highlight_preset_name = st.sidebar.selectbox(
    "강조 프리셋",
    list(highlight_presets.keys()),
    index=0
)

highlight_color = st.sidebar.color_picker(
    "강조 색상",
    value="#ffcc66"
)

highlight_alpha = st.sidebar.slider(
    "강조 진하기",
    min_value=0.1,
    max_value=1.0,
    value=0.75,
    step=0.05
)

show_highlight_only = st.sidebar.checkbox(
    "해당 국가만 보기",
    value=True,
    disabled=(highlight_preset_name == "없음")
)

highlight_names = highlight_presets[highlight_preset_name]

if highlight_preset_name == "없음":
    show_highlight_only = False


# -----------------------------
# 지도 범위 데이터
# -----------------------------
region = world.cx[x_min:x_max, y_min:y_max].copy()

region = region.sort_values(["CONTINENT", "ADMIN"]).reset_index(drop=True)
region["NUM"] = range(1, len(region) + 1)

# =============================
# 탐색 모드
# =============================
if view_mode == "탐색 모드":

    st.subheader("탐색 모드")

    center = get_center(current_bounds)

    m = folium.Map(
        location=center,
        zoom_start=2,
        tiles="cartodbpositron",
        zoom_control=True,
        zoom_snap=0.25,
        zoom_delta=0.25,
        wheel_px_per_zoom_level=180,
)

    folium.GeoJson(
        world[["ADMIN", "KO", "geometry"]].to_json(),
        name="countries",
        tooltip=folium.GeoJsonTooltip(
            fields=["KO", "ADMIN"],
            aliases=["국가명", "영문명"],
            localize=True,
            sticky=False
        ),
        style_function=lambda feature: {
            "fillColor": "white",
            "color": "black",
            "weight": 0.6,
            "fillOpacity": 0.85,
        },
        highlight_function=lambda feature: {
            "fillColor": "#ffcc66",
            "color": "black",
            "weight": 1.2,
            "fillOpacity": 0.9,
        },
    ).add_to(m)

    m.fit_bounds([
        [y_min, x_min],
        [y_max, x_max]
    ])

    map_data = st_folium(
        m,
        height=700,
        use_container_width=True,
        returned_objects=["bounds"],
        key="explore_map"
    )

    if map_data and map_data.get("bounds"):
        bounds = map_data["bounds"]

        south = bounds["_southWest"]["lat"]
        west = bounds["_southWest"]["lng"]
        north = bounds["_northEast"]["lat"]
        east = bounds["_northEast"]["lng"]

        view_bounds = clamp_view(
            west,
            east,
            south,
            north
        )

        st.session_state.explore_view = fit_view_to_ratio(*view_bounds)

    st.stop()

# -----------------------------
# 지도 그리기
# -----------------------------
map_width = x_max - x_min
map_height = y_max - y_min
map_ratio = map_width / map_height

fig_width = 14
fig_height = fig_width / map_ratio

fig_height = max(4, min(fig_height, 12))

fig, ax = plt.subplots(figsize=(11.69, 8.27))

fig.patch.set_facecolor("#e6e6e6")
ax.set_facecolor("#e6e6e6")

region.plot(
    ax=ax,
    color="white",
    edgecolor="black",
    linewidth=0.45
)

# 강조 국가
if highlight_names:
    highlight_region = region[region["ADMIN"].isin(highlight_names)]

    if not highlight_region.empty:
        highlight_region.plot(
            ax=ax,
            color=highlight_color,
            edgecolor="black",
            linewidth=0.65,
            alpha=highlight_alpha
        )

# -----------------------------
# 국가명 표시
# -----------------------------
if label_mode == "국가명 보이기":

    for _, row in region.iterrows():

# 강조 프리셋 사용 + 해당 국가만 보기일 때만
# 강조 국가만 이름 표시
        if highlight_names and show_highlight_only:
            if row["ADMIN"] not in highlight_names:
                continue

        if pd.isna(row["KO"]):
            continue

        if (
            row.geometry.area < small_area
            and row["ADMIN"] not in must_show
        ):
            continue

        point = row.geometry.representative_point()

        ax.text(
            point.x,
            point.y,
            row["KO"],
            fontsize=label_font_size,
            ha="center",
            va="center",
            color="black",
            zorder=4,
            clip_on=True,
            bbox=dict(
                boxstyle="round,pad=0.08",
                facecolor="white",
                edgecolor="none",
                alpha=0.72
            )
        )

# -----------------------------
# 번호 표시
# -----------------------------
elif label_mode == "번호 보이기":

    MIN_DIST = number_min_dist
    ITERATIONS = 60

    labels = []

    for _, row in region.iterrows():
        point = row.geometry.representative_point()

        x = point.x
        y = point.y
        area = row.geometry.area
        continent = row["CONTINENT"]

        label_x = x
        label_y = y

        # 선으로 빼기를 켰을 때만 작은 국가 번호를 바깥으로 이동
        if use_leader_lines and area < small_area:
            dx, dy = 0, 0

            if continent in ["North America", "South America"]:
                dx, dy = -7, 0
            elif continent in ["Europe", "Asia", "Africa"]:
                if x > 20:
                    dx, dy = 7, 0
                elif x < -10:
                    dx, dy = -7, 0
                else:
                    dx, dy = 0, 6
            elif continent == "Oceania":
                dx, dy = 7, -2
            else:
                dx, dy = 6, 0

            label_x = x + dx
            label_y = y + dy

        labels.append({
            "num": row["NUM"],
            "anchor_x": x,
            "anchor_y": y,
            "label_x": label_x,
            "label_y": label_y,
        })

    # 선으로 빼기를 켰을 때만 번호끼리 겹침 방지
    if use_leader_lines:
        for _ in range(ITERATIONS):
            moved = False

            for i in range(len(labels)):
                for j in range(i + 1, len(labels)):
                    a = labels[i]
                    b = labels[j]

                    dx = b["label_x"] - a["label_x"]
                    dy = b["label_y"] - a["label_y"]
                    dist = math.sqrt(dx * dx + dy * dy)

                    if dist == 0:
                        dx, dy = 0.1, 0.1
                        dist = math.sqrt(dx * dx + dy * dy)

                    if dist < MIN_DIST:
                        overlap = (MIN_DIST - dist) / 2
                        ux = dx / dist
                        uy = dy / dist

                        a["label_x"] -= ux * overlap
                        a["label_y"] -= uy * overlap
                        b["label_x"] += ux * overlap
                        b["label_y"] += uy * overlap

                        moved = True

            if not moved:
                break

    for item in labels:
        moved_distance = math.sqrt(
            (item["label_x"] - item["anchor_x"]) ** 2 +
            (item["label_y"] - item["anchor_y"]) ** 2
        )

        if use_leader_lines and moved_distance > 1.2:
            ax.plot(
                [item["anchor_x"], item["label_x"]],
                [item["anchor_y"], item["label_y"]],
                color="black",
                linewidth=leader_line_width,
                alpha=leader_line_alpha,
                zorder=2,
                clip_on=True
            )

        ax.text(
            item["label_x"],
            item["label_y"],
            str(item["num"]),
            fontsize=number_font_size,
            ha="center",
            va="center",
            color="black",
            zorder=4,
            clip_on=True,
            bbox=dict(
                boxstyle=f"circle,pad={circle_pad}",
                facecolor="white",
                edgecolor="black",
                linewidth=0.35,
                alpha=0.97
            )
        )

# -----------------------------
# 마무리
# -----------------------------
ax.set_xlim(x_min, x_max)
ax.set_ylim(y_min, y_max)
ax.set_aspect("equal", adjustable="box")
ax.axis("off")

fig.subplots_adjust(left=0, right=1, top=1, bottom=0)

preview_buf = io.BytesIO()
fig.savefig(
    preview_buf,
    format="png",
    dpi=150,
    facecolor=fig.get_facecolor()
)
preview_buf.seek(0)

preview_col, _ = st.columns([A4_LANDSCAPE_RATIO, 0.2])

with preview_col:
    st.image(
        preview_buf,
        width=1200
    )


# -----------------------------
# 다운로드
# -----------------------------
st.subheader("다운로드")

col1, col2, col3 = st.columns(3)

png_buf = io.BytesIO()
fig.savefig(
    png_buf,
    format="png",
    dpi=600,
    facecolor=fig.get_facecolor()
)
png_buf.seek(0)

with col1:
    st.download_button(
        label="PNG 다운로드",
        data=png_buf,
        file_name="map.png",
        mime="image/png"
    )

svg_buf = io.BytesIO()
fig.savefig(
    svg_buf,
    format="svg",
    facecolor=fig.get_facecolor()
)

svg_buf.seek(0)

with col2:
    st.download_button(
        label="SVG 다운로드",
        data=svg_buf,
        file_name="map.svg",
        mime="image/svg+xml"
    )

pdf_buf = io.BytesIO()
fig.savefig(
    pdf_buf,
    format="pdf",
    facecolor=fig.get_facecolor()
)
pdf_buf.seek(0)

with col3:
    st.download_button(
        label="PDF 다운로드",
        data=pdf_buf,
        file_name="map.pdf",
        mime="application/pdf"
    )

# -----------------------------
# 번호표
# -----------------------------
if label_mode == "번호 보이기":
    st.subheader("번호표")
    legend_df = region[["NUM", "KO", "ADMIN", "CONTINENT"]]
    st.dataframe(legend_df, use_container_width=True)
