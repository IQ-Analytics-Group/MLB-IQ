import streamlit as st
import pandas as pd
import requests
from datetime import date


# -----------------------------
# Page Config
# -----------------------------
st.set_page_config(page_title="MLB IQ", layout="wide")
st.title("⚾ MLB IQ")
st.subheader("Baseball Analytics & Game Intelligence")


# -----------------------------
# HTTP Helpers
# -----------------------------
def _get_json(url: str) -> dict:
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return r.json()


def _safe_first_split(stats_payload: dict) -> dict:
    """
    MLB Stats API stats payload often looks like:
    {"stats":[{"splits":[{"stat": {...}}]}]}
    """
    try:
        splits = stats_payload["stats"][0]["splits"]
        if not splits:
            return {}
        return splits[0].get("stat", {}) or {}
    except Exception:
        return {}


# -----------------------------
# Schedule + Team + Pitcher Data
# -----------------------------
@st.cache_data(ttl=300)
def fetch_today_schedule() -> pd.DataFrame:
    today = date.today().strftime("%Y-%m-%d")
    url = (
        "https://statsapi.mlb.com/api/v1/schedule"
        f"?sportId=1&date={today}"
        "&hydrate=probablePitcher"
    )
    data = _get_json(url)

    games = []
    if not data.get("dates"):
        return pd.DataFrame(games)

    for g in data["dates"][0].get("games", []):
        away_team = g["teams"]["away"]["team"]["name"]
        home_team = g["teams"]["home"]["team"]["name"]
        away_id = g["teams"]["away"]["team"]["id"]
        home_id = g["teams"]["home"]["team"]["id"]

        away_pp = g["teams"]["away"].get("probablePitcher", {})
        home_pp = g["teams"]["home"].get("probablePitcher", {})

        games.append(
            {
                "matchup": f"{away_team} @ {home_team}",
                "game_id": g.get("gamePk"),
                "away_team": away_team,
                "home_team": home_team,
                "away_team_id": away_id,
                "home_team_id": home_id,
                "away_pitcher": away_pp.get("fullName", "TBD"),
                "home_pitcher": home_pp.get("fullName", "TBD"),
                "away_pitcher_id": away_pp.get("id"),
                "home_pitcher_id": home_pp.get("id"),
            }
        )

    return pd.DataFrame(games)


@st.cache_data(ttl=3600)
def fetch_team_season_stats(team_id: int) -> dict:
    hit_url = (
        f"https://statsapi.mlb.com/api/v1/teams/{team_id}/stats"
        "?stats=season&group=hitting"
    )
    pit_url = (
        f"https://statsapi.mlb.com/api/v1/teams/{team_id}/stats"
        "?stats=season&group=pitching"
    )

    hit_data = _get_json(hit_url)
    pit_data = _get_json(pit_url)

    hit = _safe_first_split(hit_data)
    pit = _safe_first_split(pit_data)

    runs = hit.get("runs", 0)
    games_played = hit.get("gamesPlayed", 0)
    ops = hit.get("ops", None)

    r_per_game = None
    if isinstance(runs, (int, float)) and isinstance(games_played, (int, float)) and games_played:
        r_per_game = round(runs / games_played, 3)

    return {
        "runs": runs,
        "games_played": games_played,
        "r_per_game": r_per_game,
        "ops": ops,
        "team_era": pit.get("era"),
        "team_whip": pit.get("whip"),
    }


@st.cache_data(ttl=3600)
def fetch_pitcher_season_stats(player_id: int) -> dict:
    url = (
        f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats"
        "?stats=season&group=pitching"
    )
    data = _get_json(url)
    pit = _safe_first_split(data)
    if not pit:
        return {}

    return {
        "era": pit.get("era"),
        "whip": pit.get("whip"),
        "ip": pit.get("inningsPitched"),
        "k": pit.get("strikeOuts"),
        "bb": pit.get("baseOnBalls"),
        "h": pit.get("hits"),
        "hr": pit.get("homeRuns"),
        "games": pit.get("gamesPlayed"),
        "saves": pit.get("saves"),
    }


# -----------------------------
# Player Search (Roster) + Player Stats
# -----------------------------
@st.cache_data(ttl=900)
def fetch_active_roster(team_id: int) -> list[dict]:
    """
    Pull active roster for a team.
    Returns list of dicts: {id, name, position, team_id}
    """
    url = f"https://statsapi.mlb.com/api/v1/teams/{team_id}/roster?rosterType=active"
    data = _get_json(url)
    roster = []

    for p in data.get("roster", []):
        person = p.get("person", {})
        pos = p.get("position", {})
        roster.append(
            {
                "player_id": person.get("id"),
                "name": person.get("fullName"),
                "position": pos.get("abbreviation") or pos.get("name"),
                "team_id": team_id,
            }
        )

    # Remove blanks
    roster = [x for x in roster if x.get("player_id") and x.get("name")]
    return roster


@st.cache_data(ttl=3600)
def fetch_player_hitting_season(player_id: int) -> dict:
    url = (
        f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats"
        "?stats=season&group=hitting"
    )
    data = _get_json(url)
    hit = _safe_first_split(data)
    return hit or {}


@st.cache_data(ttl=3600)
def fetch_player_pitching_season(player_id: int) -> dict:
    url = (
        f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats"
        "?stats=season&group=pitching"
    )
    data = _get_json(url)
    pit = _safe_first_split(data)
    return pit or {}


def _to_float(x):
    try:
        return float(x)
    except Exception:
        return None


def _lean_higher_lower(proj: float | None, line: float | None) -> str:
    if proj is None or line is None:
        return "—"
    if proj > line:
        return "Lean: Higher"
    if proj < line:
        return "Lean: Lower"
    return "Lean: Even"


def _build_season_prop_projection(hitting: dict, pitching: dict, prop_key: str) -> float | None:
    """
    Simple baseline projection:
    Uses current season total directly (not end-of-season projection),
    because we don't have full season pace + games remaining in a stable way.
    For Underdog-style season props, you'll likely want:
      - current total
      - pace (per game)
      - projected end-of-season (pace * 162)
    We'll show pace + 162-projection where possible.
    """
    if prop_key in ("homeRuns", "stolenBases"):
        return _to_float(hitting.get(prop_key))
    if prop_key in ("saves", "strikeOuts"):
        return _to_float(pitching.get(prop_key))
    return None


def _pace_and_162_projection(total: float | None, games_played: float | None) -> tuple[float | None, float | None]:
    if total is None or games_played in (None, 0):
        return None, None
    pace = total / games_played
    season_162 = pace * 162
    return round(pace, 3), round(season_162, 1)


# -----------------------------
# UI: Select Game
# -----------------------------
try:
    games_df = fetch_today_schedule()
except Exception as e:
    st.error(f"Schedule fetch failed: {e}")
    st.stop()

if games_df.empty:
    st.warning("No MLB games found for today.")
    st.stop()

selected_matchup = st.selectbox("Select a Game", games_df["matchup"])
st.divider()

game = games_df[games_df["matchup"] == selected_matchup].iloc[0]
away_team = game["away_team"]
home_team = game["home_team"]
away_id = int(game["away_team_id"])
home_id = int(game["home_team_id"])

# Team stats
try:
    away_team_stats = fetch_team_season_stats(away_id)
    home_team_stats = fetch_team_season_stats(home_id)
except Exception as e:
    st.error(f"Team stats fetch failed: {e}")
    st.stop()

# Pitcher stats (probables)
away_prob_pit = {}
home_prob_pit = {}
if pd.notna(game.get("away_pitcher_id")):
    try:
        away_prob_pit = fetch_pitcher_season_stats(int(game["away_pitcher_id"]))
    except Exception:
        away_prob_pit = {}

if pd.notna(game.get("home_pitcher_id")):
    try:
        home_prob_pit = fetch_pitcher_season_stats(int(game["home_pitcher_id"]))
    except Exception:
        home_prob_pit = {}

# Display matchup summary
c1, c2 = st.columns(2)

with c1:
    st.markdown("### Away Team")
    st.markdown(f"**{away_team}**")
    st.write("**Probable Pitcher:**", game["away_pitcher"])
    if away_prob_pit:
        st.caption(
            f"ERA: {away_prob_pit.get('era','—')} | WHIP: {away_prob_pit.get('whip','—')} | "
            f"IP: {away_prob_pit.get('ip','—')} | K: {away_prob_pit.get('k','—')}"
        )
    st.write("---")
    st.write("**Team Snapshot (Season):**")
    st.write(f"Runs/Game: {away_team_stats.get('r_per_game','—')}")
    st.write(f"OPS: {away_team_stats.get('ops','—')}")
    st.write(f"Team ERA: {away_team_stats.get('team_era','—')}")
    st.write(f"Team WHIP: {away_team_stats.get('team_whip','—')}")

with c2:
    st.markdown("### Home Team")
    st.markdown(f"**{home_team}**")
    st.write("**Probable Pitcher:**", game["home_pitcher"])
    if home_prob_pit:
        st.caption(
            f"ERA: {home_prob_pit.get('era','—')} | WHIP: {home_prob_pit.get('whip','—')} | "
            f"IP: {home_prob_pit.get('ip','—')} | K: {home_prob_pit.get('k','—')}"
        )
    st.write("---")
    st.write("**Team Snapshot (Season):**")
    st.write(f"Runs/Game: {home_team_stats.get('r_per_game','—')}")
    st.write(f"OPS: {home_team_stats.get('ops','—')}")
    st.write(f"Team ERA: {home_team_stats.get('team_era','—')}")
    st.write(f"Team WHIP: {home_team_stats.get('team_whip','—')}")

st.divider()


# -----------------------------
# Player Finder (Searchable dropdown)
# -----------------------------
st.subheader("Player Finder (Type to Search)")
st.caption("Click the dropdown and start typing a player name (searchable).")

with st.spinner("Loading rosters..."):
    away_roster = fetch_active_roster(away_id)
    home_roster = fetch_active_roster(home_id)

players = []
for p in away_roster:
    players.append({**p, "team_name": away_team})
for p in home_roster:
    players.append({**p, "team_name": home_team})

players = [p for p in players if p.get("player_id") and p.get("name")]
players = sorted(players, key=lambda x: x["name"].lower())

if not players:
    st.warning("Could not load rosters for this matchup.")
    st.stop()

# Build a label so it looks good in the dropdown
def _player_label(p: dict) -> str:
    pos = p.get("position") or ""
    team = p.get("team_name") or ""
    return f"{p['name']}  •  {team}  •  {pos}"

selected_player = st.selectbox(
    "Search and select a player",
    players,
    format_func=_player_label,
    index=0
)

player_id = int(selected_player["player_id"])
player_name = selected_player["name"]
player_team = selected_player["team_name"]
player_pos = selected_player.get("position", "—")

st.write(f"**Selected:** {player_name} ({player_team}) — {player_pos}")

# Pull both hitting and pitching; some players will have one empty
with st.spinner("Loading player season stats..."):
    hit = fetch_player_hitting_season(player_id)
    pit = fetch_player_pitching_season(player_id)

# Show quick stat cards
st.divider()
st.subheader("Season Snapshot (Player)")

colA, colB = st.columns(2)

with colA:
    st.markdown("#### Hitting")
    if not hit:
        st.info("No hitting stats found (or not available).")
    else:
        st.write(f"Games: {hit.get('gamesPlayed','—')}")
        st.write(f"AVG: {hit.get('avg','—')} | OBP: {hit.get('obp','—')} | SLG: {hit.get('slg','—')} | OPS: {hit.get('ops','—')}")
        st.write(f"HR: {hit.get('homeRuns','—')} | SB: {hit.get('stolenBases','—')} | RBI: {hit.get('rbi','—')} | R: {hit.get('runs','—')}")

with colB:
    st.markdown("#### Pitching")
    if not pit:
        st.info("No pitching stats found (or not available).")
    else:
        st.write(f"Games: {pit.get('gamesPlayed','—')} | GS: {pit.get('gamesStarted','—')}")
        st.write(f"ERA: {pit.get('era','—')} | WHIP: {pit.get('whip','—')} | IP: {pit.get('inningsPitched','—')}")
        st.write(f"K: {pit.get('strikeOuts','—')} | BB: {pit.get('baseOnBalls','—')} | HR: {pit.get('homeRuns','—')} | Saves: {pit.get('saves','—')}")

st.divider()


# -----------------------------
# Pick Builder (Underdog-style)
# -----------------------------
st.subheader("Pick Builder (Season Props)")
st.caption("Enter a line (like Underdog) and MLB IQ will show a quick baseline + lean. This is a starting point; we’ll add ML next.")

prop_map = {
    "Season Home Runs": ("homeRuns", "hitting"),
    "Season Stolen Bases": ("stolenBases", "hitting"),
    "Season Saves": ("saves", "pitching"),
    "Season Strikeouts": ("strikeOuts", "pitching"),
}

prop_choice = st.selectbox("Prop Type", list(prop_map.keys()))
prop_key, prop_group = prop_map[prop_choice]

line = st.number_input("Enter the line", min_value=0.0, step=0.5, value=0.0)

# Build baseline
season_total = _build_season_prop_projection(hit, pit, prop_key)

# Games played needed for pace
games_played = None
if prop_group == "hitting":
    games_played = _to_float(hit.get("gamesPlayed"))
else:
    games_played = _to_float(pit.get("gamesPlayed"))

pace, proj_162 = _pace_and_162_projection(season_total, games_played)
lean = _lean_higher_lower(proj_162, line) if proj_162 is not None and line is not None else "—"

m1, m2, m3 = st.columns(3)
m1.metric("Current Season Total", "—" if season_total is None else round(season_total, 1))
m2.metric("Per-Game Pace", "—" if pace is None else pace)
m3.metric("162-Game Projection", "—" if proj_162 is None else proj_162)

st.write("**Suggestion:**", lean)

st.caption(
    "Important: This is a simple pace-based baseline. Next step is adding opponent/pitcher context, park factors, and ML models trained on historical data."
)
