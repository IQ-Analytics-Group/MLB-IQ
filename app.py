import streamlit as st
import pandas as pd
import requests
from datetime import date


# ---------------------------------------------------
# Page Setup
# ---------------------------------------------------
st.set_page_config(page_title="MLB IQ", layout="wide")
st.title("⚾ MLB IQ")
st.subheader("Baseball Analytics & Game Intelligence")


# ---------------------------------------------------
# HTTP Helpers (404 SAFE)
# ---------------------------------------------------
HEADERS = {
    "User-Agent": "MLB-IQ-Streamlit-App"
}


def _get_json(url: str):
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def _safe_first_split(payload):
    if not payload:
        return {}
    try:
        splits = payload["stats"][0]["splits"]
        if not splits:
            return {}
        return splits[0].get("stat", {})
    except Exception:
        return {}


def _to_float(x):
    try:
        return float(x)
    except Exception:
        return None


# ---------------------------------------------------
# Schedule
# ---------------------------------------------------
@st.cache_data(ttl=300)
def fetch_today_schedule():
    today = date.today().strftime("%Y-%m-%d")
    url = (
        "https://statsapi.mlb.com/api/v1/schedule"
        f"?sportId=1&date={today}"
        "&hydrate=probablePitcher"
    )

    data = _get_json(url)
    games = []

    if not data or not data.get("dates"):
        return pd.DataFrame(games)

    for g in data["dates"][0].get("games", []):
        games.append({
            "matchup": f"{g['teams']['away']['team']['name']} @ {g['teams']['home']['team']['name']}",
            "away_team": g["teams"]["away"]["team"]["name"],
            "home_team": g["teams"]["home"]["team"]["name"],
            "away_id": g["teams"]["away"]["team"]["id"],
            "home_id": g["teams"]["home"]["team"]["id"],
            "away_pitcher": g["teams"]["away"].get("probablePitcher", {}).get("fullName", "TBD"),
            "home_pitcher": g["teams"]["home"].get("probablePitcher", {}).get("fullName", "TBD"),
            "away_pitcher_id": g["teams"]["away"].get("probablePitcher", {}).get("id"),
            "home_pitcher_id": g["teams"]["home"].get("probablePitcher", {}).get("id"),
        })

    return pd.DataFrame(games)


# ---------------------------------------------------
# Team Stats (with fallback URLs)
# ---------------------------------------------------
@st.cache_data(ttl=3600)
def fetch_team_stats(team_id):
    year = date.today().year

    urls = [
        f"https://statsapi.mlb.com/api/v1/teams/{team_id}/stats?stats=season&group=hitting",
        f"https://statsapi.mlb.com/api/v1/teams/{team_id}/stats?stats=season&group=hitting&sportId=1",
        f"https://statsapi.mlb.com/api/v1/teams/{team_id}/stats?stats=season&group=hitting&season={year}",
        f"https://statsapi.mlb.com/api/v1/teams/{team_id}/stats?stats=season&group=hitting&sportId=1&season={year}",
    ]

    hit_data = None
    for u in urls:
        hit_data = _get_json(u)
        if hit_data:
            break

    hit = _safe_first_split(hit_data)

    return {
        "runs": hit.get("runs"),
        "games": hit.get("gamesPlayed"),
        "ops": hit.get("ops"),
        "ok": bool(hit)
    }


# ---------------------------------------------------
# Player Data
# ---------------------------------------------------
@st.cache_data(ttl=900)
def fetch_roster(team_id):
    url = f"https://statsapi.mlb.com/api/v1/teams/{team_id}/roster?rosterType=active"
    data = _get_json(url)
    roster = []

    if not data:
        return roster

    for p in data.get("roster", []):
        person = p.get("person", {})
        if person.get("id") and person.get("fullName"):
            roster.append({
                "id": person["id"],
                "name": person["fullName"]
            })

    return roster


@st.cache_data(ttl=3600)
def fetch_player_hitting(player_id):
    url = f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats?stats=season&group=hitting"
    return _safe_first_split(_get_json(url))


@st.cache_data(ttl=3600)
def fetch_player_pitching(player_id):
    url = f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats?stats=season&group=pitching"
    return _safe_first_split(_get_json(url))


# ---------------------------------------------------
# MAIN APP
# ---------------------------------------------------
games_df = fetch_today_schedule()

if games_df.empty:
    st.warning("No MLB games found today.")
    st.stop()

matchup = st.selectbox("Select a Game", games_df["matchup"])
game = games_df[games_df["matchup"] == matchup].iloc[0]

away_team = game["away_team"]
home_team = game["home_team"]

away_stats = fetch_team_stats(game["away_id"])
home_stats = fetch_team_stats(game["home_id"])

if not away_stats["ok"] or not home_stats["ok"]:
    st.warning("Team stats endpoint returned limited data. Player Finder still works.")

col1, col2 = st.columns(2)

with col1:
    st.markdown(f"### {away_team}")
    st.write("Probable Pitcher:", game["away_pitcher"])

with col2:
    st.markdown(f"### {home_team}")
    st.write("Probable Pitcher:", game["home_pitcher"])

st.divider()


# ---------------------------------------------------
# Player Finder
# ---------------------------------------------------
st.subheader("Player Finder (Type to Search)")

roster = fetch_roster(game["away_id"]) + fetch_roster(game["home_id"])

if not roster:
    st.warning("Roster unavailable.")
    st.stop()

selected_player = st.selectbox(
    "Search Player",
    roster,
    format_func=lambda x: x["name"]
)

player_id = selected_player["id"]
player_name = selected_player["name"]

st.write("Selected:", player_name)

hit = fetch_player_hitting(player_id)
pit = fetch_player_pitching(player_id)

st.divider()
st.subheader("Season Snapshot")

colA, colB = st.columns(2)

with colA:
    st.markdown("#### Hitting")
    if hit:
        st.write("Games:", hit.get("gamesPlayed"))
        st.write("HR:", hit.get("homeRuns"))
        st.write("SB:", hit.get("stolenBases"))
        st.write("OPS:", hit.get("ops"))
    else:
        st.info("No hitting stats.")

with colB:
    st.markdown("#### Pitching")
    if pit:
        st.write("Games:", pit.get("gamesPlayed"))
        st.write("ERA:", pit.get("era"))
        st.write("K:", pit.get("strikeOuts"))
        st.write("Saves:", pit.get("saves"))
    else:
        st.info("No pitching stats.")

st.divider()


# ---------------------------------------------------
# Pick Builder
# ---------------------------------------------------
st.subheader("Pick Builder (Season Props)")

prop_choice = st.selectbox(
    "Prop Type",
    ["Season Home Runs", "Season Stolen Bases", "Season Saves", "Season Strikeouts"]
)

line = st.number_input("Enter Line", min_value=0.0, step=0.5)

season_total = None
games_played = None

if prop_choice == "Season Home Runs":
    season_total = _to_float(hit.get("homeRuns"))
    games_played = _to_float(hit.get("gamesPlayed"))

elif prop_choice == "Season Stolen Bases":
    season_total = _to_float(hit.get("stolenBases"))
    games_played = _to_float(hit.get("gamesPlayed"))

elif prop_choice == "Season Saves":
    season_total = _to_float(pit.get("saves"))
    games_played = _to_float(pit.get("gamesPlayed"))

elif prop_choice == "Season Strikeouts":
    season_total = _to_float(pit.get("strikeOuts"))
    games_played = _to_float(pit.get("gamesPlayed"))

if season_total and games_played:
    pace = season_total / games_played
    proj_162 = round(pace * 162, 1)

    st.metric("Current Total", season_total)
    st.metric("Projected 162 Game Total", proj_162)

    if proj_162 > line:
        st.success("Lean: Higher")
    elif proj_162 < line:
        st.error("Lean: Lower")
    else:
        st.info("Lean: Even")

else:
    st.info("Insufficient data to project.")