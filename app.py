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
        return splits[0].get("stat", {}) or {}
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

    data = None
    for u in urls:
        data = _get_json(u)
        if data:
            break

    hit = _safe_first_split(data)

    runs = hit.get("runs")
    games = hit.get("gamesPlayed")
    ops = hit.get("ops")

    r_per_game = None
    if isinstance(runs, (int, float)) and isinstance(games, (int, float)) and games:
        r_per_game = round(runs / games, 3)

    return {
        "runs": runs,
        "games": games,
        "r_per_game": r_per_game,
        "ops": ops,
        "ok": bool(hit),
    }


# ---------------------------------------------------
# Roster + Player Stats (with fallbacks)
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
        position = p.get("position", {})
        if person.get("id") and person.get("fullName"):
            roster.append({
                "id": person["id"],
                "name": person["fullName"],
                "pos": position.get("abbreviation") or position.get("name") or "",
                "team_id": team_id,
            })

    return roster


@st.cache_data(ttl=3600)
def fetch_player_hitting(player_id):
    year = date.today().year
    urls = [
        f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats?stats=season&group=hitting",
        f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats?stats=season&group=hitting&sportId=1",
        f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats?stats=season&group=hitting&season={year}",
        f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats?stats=season&group=hitting&sportId=1&season={year}",
    ]

    data = None
    for u in urls:
        data = _get_json(u)
        if data:
            break

    return _safe_first_split(data)


@st.cache_data(ttl=3600)
def fetch_player_pitching(player_id):
    year = date.today().year
    urls = [
        f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats?stats=season&group=pitching",
        f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats?stats=season&group=pitching&sportId=1",
        f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats?stats=season&group=pitching&season={year}",
        f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats?stats=season&group=pitching&sportId=1&season={year}",
    ]

    data = None
    for u in urls:
        data = _get_json(u)
        if data:
            break

    return _safe_first_split(data)


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
away_id = int(game["away_id"])
home_id = int(game["home_id"])

away_stats = fetch_team_stats(away_id)
home_stats = fetch_team_stats(home_id)

if not away_stats["ok"] or not home_stats["ok"]:
    st.warning("Team stats endpoint returned limited data. Player Finder still works.")

col1, col2 = st.columns(2)

with col1:
    st.markdown(f"### {away_team}")
    st.write("Probable Pitcher:", game["away_pitcher"])
    if away_stats.get("r_per_game") is not None:
        st.caption(f"Runs/Game: {away_stats.get('r_per_game')} | OPS: {away_stats.get('ops','—')}")

with col2:
    st.markdown(f"### {home_team}")
    st.write("Probable Pitcher:", game["home_pitcher"])
    if home_stats.get("r_per_game") is not None:
        st.caption(f"Runs/Game: {home_stats.get('r_per_game')} | OPS: {home_stats.get('ops','—')}")

st.divider()


# ---------------------------------------------------
# Player Finder (Searchable dropdown)
# ---------------------------------------------------
st.subheader("Player Finder (Type to Search)")

roster = fetch_roster(away_id) + fetch_roster(home_id)
roster = sorted(roster, key=lambda x: x["name"].lower())

if not roster:
    st.warning("Roster unavailable for this matchup.")
    st.stop()

def _label(p):
    extra = f" • {p['pos']}" if p.get("pos") else ""
    return f"{p['name']}{extra}"

selected_player = st.selectbox(
    "Search Player",
    roster,
    format_func=_label
)

player_id = int(selected_player["id"])
player_name = selected_player["name"]

st.write("Selected:", player_name)

hit = fetch_player_hitting(player_id) or {}
pit = fetch_player_pitching(player_id) or {}

st.divider()
st.subheader("Season Snapshot")

colA, colB = st.columns(2)

with colA:
    st.markdown("#### Hitting")
    if hit:
        st.write("Games:", hit.get("gamesPlayed", "—"))
        st.write("AVG:", hit.get("avg", "—"))
        st.write("OPS:", hit.get("ops", "—"))
        st.write("HR:", hit.get("homeRuns", "—"))
        st.write("SB:", hit.get("stolenBases", "—"))
        st.write("RBI:", hit.get("rbi", "—"))
    else:
        st.info("No hitting stats.")

with colB:
    st.markdown("#### Pitching")
    if pit:
        st.write("Games:", pit.get("gamesPlayed", "—"))
        st.write("ERA:", pit.get("era", "—"))
        st.write("WHIP:", pit.get("whip", "—"))
        st.write("IP:", pit.get("inningsPitched", "—"))
        st.write("K:", pit.get("strikeOuts", "—"))
        st.write("Saves:", pit.get("saves", "—"))
    else:
        st.info("No pitching stats.")

st.divider()


# ---------------------------------------------------
# Pick Builder (Season Props - simple pace projection)
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

if season_total is not None and games_played not in (None, 0):
    pace = season_total / games_played
    proj_162 = round(pace * 162, 1)

    c1, c2, c3 = st.columns(3)
    c1.metric("Current Total", round(season_total, 2))
    c2.metric("Per-Game Pace", round(pace, 3))
    c3.metric("162-Game Projection", proj_162)

    if proj_162 > line:
        st.success("Lean: Higher")
    elif proj_162 < line:
        st.error("Lean: Lower")
    else:
        st.info("Lean: Even")
else:
    st.info("Insufficient data to project yet (or player has no season stats yet).")