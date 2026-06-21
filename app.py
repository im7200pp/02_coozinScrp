import streamlit as st
import os
import asyncio
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from scraper import scrape_itemscout_rankings

# Load environment variables (useful for local development credentials)
load_dotenv()

# Automatic Playwright browser installation on Streamlit Community Cloud
@st.cache_resource
def install_playwright_browsers():
    import subprocess
    import sys
    try:
        # Run playwright installation using the current python executable
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    except Exception as e:
        st.error(f"Failed to install Playwright browser: {e}")

install_playwright_browsers()


# Page Configuration
st.set_page_config(
    page_title="ItemScout Rank Tracker",
    page_icon="📈",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Custom Styling for Premium Aesthetics
st.markdown(
    """
    <style>
    /* Gradient Title */
    .title-container {
        text-align: center;
        margin-top: 1rem;
        margin-bottom: 2rem;
    }
    .main-title {
        background: linear-gradient(135deg, #6366f1 0%, #a855f7 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.6rem;
        font-weight: 800;
        margin-bottom: 0.5rem;
    }
    .subtitle {
        color: #9ca3af;
        font-size: 1rem;
        line-height: 1.6;
    }
    /* Hide Streamlit default header/footer for cleaner UI */
    header {visibility: hidden;}
    footer {visibility: hidden;}
    .viewerBadge_container__1QS1h {display: none !important;}
    </style>
    """,
    unsafe_allow_html=True
)

# Header Section
st.markdown(
    """
    <div class="title-container">
        <h1 class="main-title">ItemScout Rank Tracker</h1>
        <p class="subtitle">
            아이템스카웃 계정을 입력하여 순위 분석 데이터를 수집하고<br>
            CSV 파일로 다운로드합니다.
        </p>
    </div>
    """,
    unsafe_allow_html=True
)

# Form container
with st.form("scraper_form"):
    st.subheader("🔑 계정 및 보안 인증")
    
    username = st.text_input(
        "아이디 (이메일)",
        value=os.getenv("ITEMSCOUT_USERNAME", ""),
        placeholder="example@email.com"
    )
    
    password = st.text_input(
        "비밀번호",
        value=os.getenv("ITEMSCOUT_PASSWORD", ""),
        type="password",
        placeholder="••••••••"
    )
    
    access_key = st.text_input(
        "서버 액세스 키 (Access Key)",
        type="password",
        placeholder="액세스 키를 입력하세요"
    )
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    submit_button = st.form_submit_button(
        "분석 시작 및 다운로드",
        use_container_width=True,
        type="primary"
    )

if submit_button:
    # 1. Validation
    correct_key = os.getenv("SCRAPER_ACCESS_KEY", "Coozin321!!")
    if access_key != correct_key:
        st.error("🔒 유효하지 않은 액세스 키입니다. 다시 입력해 주세요.")
    elif not username or not password:
        st.error("⚠️ 아이디와 비밀번호를 모두 입력해 주세요.")
    else:
        # 2. Execution Container
        st.subheader("⚙️ 수집 콘솔 로그")
        
        with st.status("Initializing scraper engine...", expanded=True) as status:
            # Progress callback for the async scraper
            async def progress_callback(message: str):
                st.write(f"🔹 {message}")
                status.update(label=message)
            
            try:
                # Run the scraper asynchronously
                rows = asyncio.run(scrape_itemscout_rankings(username, password, progress_callback))
                
                if not rows:
                    raise ValueError("No scraper items returned. Ensure you have active keywords registered in your Daily Tracker.")
                
                # Progress logging for CSV collation
                st.write("🔹 Compiling results to CSV format...")
                status.update(label="Compiling results to CSV format...")
                
                today_str = datetime.now().strftime("%Y-%m-%d")
                new_df = pd.DataFrame(rows)
                new_df["product_id"] = new_df["product_id"].astype(str)
                new_df.insert(0, "date", today_str)
                
                # Check for existing data and merge
                output_dir = "data"
                os.makedirs(output_dir, exist_ok=True)
                csv_path = os.path.join(output_dir, "rankings.csv")
                
                if os.path.exists(csv_path):
                    st.write(f"🔹 Reading existing rankings log from {csv_path}...")
                    existing_df = pd.read_csv(csv_path, dtype={"product_id": str})
                    combined_df = pd.concat([existing_df, new_df], ignore_index=True)
                    combined_df.drop_duplicates(subset=["date", "product_id", "keyword"], keep="last", inplace=True)
                else:
                    st.write("🔹 Creating new rankings log...")
                    combined_df = new_df
                    
                combined_df.sort_values(by=["date", "product_name", "keyword"], ascending=[True, True, True], inplace=True)
                combined_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
                
                # Finish status
                status.update(label="수집 및 정리가 완료되었습니다!", state="complete")
                st.success("🎉 수집 및 정리가 성공적으로 완료되었습니다!")
                
                # Convert DataFrame to bytes for download button
                csv_bytes = combined_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
                
                # Download Button
                st.download_button(
                    label="📥 CSV 파일 다운로드",
                    data=csv_bytes,
                    file_name="rankings.csv",
                    mime="text/csv",
                    use_container_width=True
                )
                
                # Data Preview Section
                st.markdown("<br>", unsafe_allow_html=True)
                st.subheader("📊 금일 수집된 순위 요약")
                st.dataframe(
                    new_df[["product_name", "keyword", "rank"]],
                    use_container_width=True,
                    hide_index=True
                )
                
            except Exception as e:
                error_msg = str(e)
                st.write(f"❌ Scraper task failed: {error_msg}")
                status.update(label="수집 실패", state="error")
                st.error(f"🚨 오류 발생: {error_msg}")
