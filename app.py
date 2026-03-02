import streamlit as st
import pandas as pd
import requests
from datetime import date

st.set_page_config(page_title="MLB IQ", layout="wide")

st.title("⚾ MLB IQ")
st.subheader("Baseball Analytics & Game Intelligence")

def fetch_today_games():
    today = date.today().strftime("%Y-%m-%d")
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={today}"

    response = requests.get(url, timeout=15)
    response.raise_for_status()
    data = response.json()

    games = []
    if "dates" in data and len(data["dates"]) > 0:
        for game in data["dates"][0]["games"]:
            away = game["teams"]["away"]["team"]["name"]
            home = game["teams"]["home"]["team"]["name"]
            games.append({
                "matchup": f"{away} @ {home}",
                "away_team": away,
                "home_team": home,
                "game_id": game["gamePk"]
            })

    return pd.DataFrame(games)

try:
    games_df = fetch_today_games()
except Exception as e:
    st.error(f"Schedule fetch failed: {e}")
    st.stop()

if games_df.empty:
    st.warning("No MLB games found for today.")
else:
    selected_game = st.selectbox("Select a Game", games_df["matchup"])

    st.divider()

    game_data = games_df[games_df["matchup"] == selected_game].iloc[0]

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Away Team", game_data["away_team"])
    with col2:
        st.metric("Home Team", game_data["home_team"])

    st.divider()
    st.subheader("Projection (Coming Soon)")
    st.info("Model projections will appear here.")
