import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from io import StringIO


def parse_bat_file(file_content: str) -> tuple[dict, pd.DataFrame]:
    """Parse a .TXT file and return metadata dict and DataFrame."""
    lines = file_content.strip().split("\n")

    metadata = {}
    data_started = False
    data_lines = []

    for line in lines:
        line = line.strip()
        if line == "DATAASCII":
            data_started = True
            continue
        if data_started:
            data_lines.append(line)
        elif line and not line.startswith("time_ms"):
            parts = line.split()
            if len(parts) >= 2:
                metadata[parts[0]] = (
                    parts[1] if len(parts) == 2 else " ".join(parts[1:])
                )

    if not data_lines:
        return metadata, pd.DataFrame()

    df = pd.read_csv(
        StringIO("\n".join(data_lines)),
        sep=r"\s+",
        names=["time_ms", "posFME", "posFI", "posFT", "posDUREE", "SNRdB"],
        dtype={
            "time_ms": float,
            "posFME": int,
            "posFI": int,
            "posFT": int,
            "posDUREE": int,
            "SNRdB": float,
        },
    )

    return metadata, df


def process_dataframe(
    df: pd.DataFrame, freq_khz_enreg: float, lenfft: int
) -> pd.DataFrame:
    """Apply frequency conversion and filtering rules."""
    df = df.copy()

    df["FME_khz"] = df["posFME"] * (freq_khz_enreg / lenfft)
    df["FI_khz"] = df["posFI"] * (freq_khz_enreg / lenfft)
    df["FT_khz"] = df["posFT"] * (freq_khz_enreg / lenfft)

    df = df[~((df["posFME"] == 0) & (df["SNRdB"] == 0))]

    return df


def load_and_process_file(uploaded_file) -> tuple[pd.DataFrame, dict]:
    """Load and process an uploaded file."""
    if uploaded_file is None:
        return pd.DataFrame(), {}

    content = uploaded_file.getvalue().decode("utf-8")
    metadata, df = parse_bat_file(content)

    if df.empty:
        return df, metadata

    freq_khz_enreg = float(metadata.get("FREQ_KHZ_ENREG", 200))
    lenfft = int(metadata.get("LENFFT", 512))

    df = process_dataframe(df, freq_khz_enreg, lenfft)

    return df, metadata


def create_visualization(
    df: pd.DataFrame, title: str, color_scale: str = "Viridis"
) -> go.Figure:
    """Create a Plotly scatter plot for bat detection data."""
    if df.empty:
        return go.Figure()

    fig = go.Figure()

    fig.add_trace(
        go.Scattergl(
            x=df["time_ms"],
            y=df["FME_khz"],
            mode="markers",
            marker=dict(
                size=6,
                color=df["SNRdB"],
                colorscale=color_scale,
                cmin=19,
                cmax=80,
                colorbar=dict(title="SNR (dB)"),
                opacity=0.8,
            ),
            text=[
                f"Time: {t}<br>FME: {f:.2f} kHz<br>FI: {fi:.2f} kHz<br>FT: {ft:.2f} kHz<br>SNR: {s:.1f} dB"
                for t, f, fi, ft, s in zip(
                    df["time_ms"],
                    df["FME_khz"],
                    df["FI_khz"],
                    df["FT_khz"],
                    df["SNRdB"],
                )
            ],
            hoverinfo="text",
        )
    )

    fig.update_layout(
        title=title,
        xaxis_title="Time (ms)",
        yaxis_title="Frequency (kHz)",
        height=500,
        margin=dict(l=50, r=50, t=50, b=50),
        template="plotly_white",
    )

    return fig


st.set_page_config(page_title="BAT - Echolocation Data Comparator", layout="wide")

st.title("🦇 BAT Detection Data Comparator")
st.markdown("Compare real vs simulated echolocation data")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Real Data")
    real_file = st.file_uploader("Upload real data file", type=["txt"], key="real")

with col2:
    st.subheader("Simulated Data")
    sim_file = st.file_uploader("Upload simulated data file", type=["txt"], key="sim")

with st.sidebar:
    st.header("Filters")

    snr_min = st.slider("Minimum SNR (dB)", min_value=19, max_value=80, value=19)
    st.caption(f"Showing signals with SNR ≥ {snr_min} dB")

    st.divider()

    view_mode = st.radio("View Mode", ["Side by Side", "Overlaid"], index=0)

    color_scale = st.selectbox("Color Scale", ["Viridis", "Jet", "Plasma", "Inferno"])

if real_file or sim_file:
    real_df, real_meta = load_and_process_file(real_file)
    sim_df, sim_meta = load_and_process_file(sim_file)

    time_min = 0
    time_max = max(
        real_df["time_ms"].max() if not real_df.empty else 0,
        sim_df["time_ms"].max() if not sim_df.empty else 0,
    )

    with st.sidebar:
        time_range = st.slider(
            "Time Window (ms)",
            min_value=int(time_min),
            max_value=int(time_max) if time_max > 0 else 1000000,
            value=(int(time_min), int(time_max) if time_max > 0 else 100000),
        )
        st.caption(f"Showing {time_range[0]:,} - {time_range[1]:,} ms")

    if not real_df.empty:
        real_df = real_df[
            (real_df["SNRdB"] >= snr_min)
            & (real_df["time_ms"] >= time_range[0])
            & (real_df["time_ms"] <= time_range[1])
        ]

    if not sim_df.empty:
        sim_df = sim_df[
            (sim_df["SNRdB"] >= snr_min)
            & (sim_df["time_ms"] >= time_range[0])
            & (sim_df["time_ms"] <= time_range[1])
        ]

    st.divider()

    if view_mode == "Side by Side":
        col_left, col_right = st.columns(2)

        with col_left:
            st.subheader("Real Data")
            if not real_df.empty:
                st.plotly_chart(
                    create_visualization(real_df, "", color_scale),
                    use_container_width=True,
                )
                st.caption(
                    f"Points: {len(real_df):,} | Freq range: {real_df['FME_khz'].min():.1f} - {real_df['FME_khz'].max():.1f} kHz"
                )
            else:
                st.info("No data loaded or filtered out")

        with col_right:
            st.subheader("Simulated Data")
            if not sim_df.empty:
                st.plotly_chart(
                    create_visualization(sim_df, "", color_scale),
                    use_container_width=True,
                )
                st.caption(
                    f"Points: {len(sim_df):,} | Freq range: {sim_df['FME_khz'].min():.1f} - {sim_df['FME_khz'].max():.1f} kHz"
                )
            else:
                st.info("No data loaded or filtered out")

    else:
        fig = go.Figure()

        if not real_df.empty:
            fig.add_trace(
                go.Scattergl(
                    x=real_df["time_ms"],
                    y=real_df["FME_khz"],
                    mode="markers",
                    marker=dict(size=6, color="blue", opacity=0.6),
                    name=f"Real ({len(real_df):,} pts)",
                    text=[
                        f"Time: {t}<br>FME: {f:.2f}<br>FI: {fi:.2f}<br>FT: {ft:.2f}<br>SNR: {s:.1f}"
                        for t, f, fi, ft, s in zip(
                            real_df["time_ms"],
                            real_df["FME_khz"],
                            real_df["FI_khz"],
                            real_df["FT_khz"],
                            real_df["SNRdB"],
                        )
                    ],
                    hoverinfo="text",
                )
            )

        if not sim_df.empty:
            fig.add_trace(
                go.Scattergl(
                    x=sim_df["time_ms"],
                    y=sim_df["FME_khz"],
                    mode="markers",
                    marker=dict(size=6, color="red", opacity=0.6),
                    name=f"Simulated ({len(sim_df):,} pts)",
                    text=[
                        f"Time: {t}<br>FME: {f:.2f}<br>FI: {fi:.2f}<br>FT: {ft:.2f}<br>SNR: {s:.1f}"
                        for t, f, fi, ft, s in zip(
                            sim_df["time_ms"],
                            sim_df["FME_khz"],
                            sim_df["FI_khz"],
                            sim_df["FT_khz"],
                            sim_df["SNRdB"],
                        )
                    ],
                    hoverinfo="text",
                )
            )

        fig.update_layout(
            title="Overlaid Comparison",
            xaxis_title="Time (ms)",
            yaxis_title="Frequency (kHz)",
            height=600,
            template="plotly_white",
        )

        st.plotly_chart(fig, use_container_width=True)

else:
    st.info("👆 Upload at least one data file to begin visualization")
