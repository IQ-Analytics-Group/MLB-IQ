import streamlit as st
import pandas as pd
import requests
from datetime import date

st.set_page_config(page_title="MLB IQ", layout="wide")

st.title("⚾ MLB IQ")
st.subheader("Baseball Analytics & Game Intelligence")


# -----------------------------
# Helpers
# -----------------------------
def _get_json(url: str) -> dict:
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return r.json()


@st.cache_data(ttl=300)
def fetch_today_schedule() -> pd.DataFrame:
    """
    Pull today's MLB schedule and include probable pitchers when available.
    """
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
    """
    Returns a small summary:
    - Runs per game (R/G)
    - Team batting OPS
    - Team pitching ERA
    - Team pitching WHIP (if available)
    """
    # Hitting
    hit_url = (
        f"https://statsapi.mlb.com/api/v1/teams/{team_id}/stats"
        "?stats=season&group=hitting"
    )
    hit_data = _get_json(hit_url)

    # Pitching
    pit_url = (
        f"https://statsapi.mlb.com/api/v1/teams/{team_id}/stats"
        "?stats=season&group=pitching"
    )
    pit_data = _get_json(pit_url)

    def _safe_stat(stats_payload: dict, key: str, default=None):
        try:
            splits = stats_payload["stats"][0]["splits"]
            if not splits:
                return default
            return splits[0]["stat"].get(key, default)
        except Exception:
            return default

    # Hitting stats
    runs = _safe_stat(hit_data, "runs", 0)
    games_played = _safe_stat(hit_data, "gamesPlayed", 0)
    ops = _safe_stat(hit_data, "ops", None)

    r_per_game = None
    if isinstance(runs, (int, float)) and isinstance(games_played, (int, float)) and games_played:
        r_per_game = round(runs / games_played, 3)

    # Pitching stats
    era = _safe_stat(pit_data, "era", None)
    whip = _safe_stat(pit_data, "whip", None)

    return {
        "runs": runs,
        "games_played": games_played,
        "r_per_game": r_per_game,
        "ops": ops,
        "era": era,
        "whip": whip,
    }


@st.cache_data(ttl=3600)
def fetch_pitcher_season_stats(player_id: int) -> dict:
    """
    Pull pitcher season stats (ERA, WHIP, SO, IP, etc.) when available.
    """
    url = (
        f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats"
        "?stats=season&group=pitching"
    )
    data = _get_json(url)

    try:
        splits = data["stats"][0]["splits"]
        if not splits:
            return {}
        stat = splits[0]["stat"]
        # Keep a small, useful subset
        return {
            "era": stat.get("era"),
            "whip": stat.get("whip"),
            "inningsPitched": stat.get("inningsPitched"),
            "strikeOuts": stat.get("strikeOuts"),
            "baseOnBalls": stat.get("baseOnBalls"),
            "hits": stat.get("hits"),
            "homeRuns": stat.get("homeRuns"),
            "gamesPlayed": stat.get("gamesPlayed"),
        }
    except Exception:
        return {}


def baseline_projection(away_team_stats: dict, home_team_stats: dict) -> dict:
    """
    Very simple baseline projection using only team Runs/Game.
    (This is NOT an ML model yet — just a sanity baseline.)
    """
    away_rg = away_team_stats.get("r_per_game")
    home_rg = home_team_stats.get("r_per_game")

    if away_rg is None or home_rg is None:
        return {"away_runs": None, "home_runs": None, "total_runs": None}

    # baseline: each team scored approx their season R/G
    away_runs = round(float(away_rg), 2)
    home_runs = round(float(home_rg), 2)
    total_runs = round(away_runs + home_runs, 2)

    return {"away_runs": away_runs, "home_runs": home_runs, "total_runs": total_runs}


# -----------------------------
# Main App
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

# Pull team stats
try:
    away_team_stats = fetch_team_season_stats(away_id)
    home_team_stats = fetch_team_season_stats(home_id)
except Exception as e:
    st.error(f"Team stats fetch failed: {e}")
    st.stop()

# Pull pitcher stats if available
away_pit_stats = {}
home_pit_stats = {}
if pd.notna(game.get("away_pitcher_id")):
    try:
        away_pit_stats = fetch_pitcher_season_stats(int(game["away_pitcher_id"]))
    except Exception:
        away_pit_stats = {}

if pd.notna(game.get("home_pitcher_id")):
    try:
        home_pit_stats = fetch_pitcher_season_stats(int(game["home_pitcher_id"]))
    except Exception:
        home_pit_stats = {}

# Header row
c1, c2 = st.columns(2)

with c1:
    st.markdown("### Away Team")
    st.markdown(f"**{away_team}**")
    st.write("**Probable Pitcher:**", game["away_pitcher"])
    if away_pit_stats:
        st.caption(
            f"Pitcher ERA: {away_pit_stats.get('era', '—')} | "
            f"WHIP: {away_pit_stats.get('whip', '—')} | "
            f"IP: {away_pit_stats.get('inningsPitched', '—')} | "
            f"K: {away_pit_stats.get('strikeOuts', '—')}"
        )
    else:
        st.caption("Pitcher stats: —")

    st.write("---")
    st.write("**Team Snapshot (Season):**")
    st.write(f"Runs/Game: {away_team_stats.get('r_per_game', '—')}")
    st.write(f"OPS: {away_team_stats.get('ops', '—')}")
    st.write(f"Team ERA: {away_team_stats.get('era', '—')}")
    st.write(f"Team WHIP: {away_team_stats.get('whip', '—')}")

with c2:
    st.markdown("### Home Team")
    st.markdown(f"**{home_team}**")
    st.write("**Probable Pitcher:**", game["home_pitcher"])
    if home_pit_stats:
        st.caption(
            f"Pitcher ERA: {home_pit_stats.get('era', '—')} | "
            f"WHIP: {home_pit_stats.get('whip', '—')} | "
            f"IP: {home_pit_stats.get('inningsPitched', '—')} | "
            f"K: {home_pit_stats.get('strikeOuts', '—')}"
        )
    else:
        st.caption("Pitcher stats: —")

    st.write("---")
    st.write("**Team Snapshot (Season):**")
    st.write(f"Runs/Game: {home_team_stats.get('r_per_game', '—')}")
    st.write(f"OPS: {home_team_stats.get('ops', '—')}")
    st.write(f"Team ERA: {home_team_stats.get('era', '—')}")
    st.write(f"Team WHIP: {home_team_stats.get('whip', '—')}")

st.divider()

# Baseline projection
proj = baseline_projection(away_team_stats, home_team_stats)

st.subheader("Projection (Baseline)")
if proj["total_runs"] is None:
    st.info("Not enough stats available yet to compute baseline projection.")
else:
    p1, p2, p3 = st.columns(3)
    p1.metric("Away Runs (baseline)", proj["away_runs"])
    p2.metric("Home Runs (baseline)", proj["home_runs"])
    p3.metric("Total Runs (baseline)", proj["total_runs"])

st.caption(
    "Note: This is a simple baseline using season Runs/Game. Next step is feature engineering + ML models."
)