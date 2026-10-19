import os
import sys
import asyncio
from typing import Optional, Dict, Any
from fastapi import FastAPI, BackgroundTasks, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import chess
import chess.engine
import database
import analyzer

app = FastAPI(title="Chess Mistake Academy", version="1.0.0")

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
database.init_db()

# Analysis state tracker
analysis_state = {
    "is_syncing": False,
    "last_message": "Ready"
}

class AttemptRequest(BaseModel):
    move: str # UCI or SAN string, e.g. "e2e4"

class BotMoveRequest(BaseModel):
    fen: str
    difficulty: Optional[int] = 10 # depth

@app.get("/api/stats")
def get_stats():
    return database.get_stats()

@app.get("/api/mistakes")
def get_mistakes(
    theme: Optional[str] = "all",
    category: Optional[str] = "all",
    time_class: Optional[str] = "all",
    solved: Optional[str] = "all",
    limit: int = 50,
    offset: int = 0
):
    solved_filter = None
    if solved == "solved":
        solved_filter = 1
    elif solved == "unsolved":
        solved_filter = 0

    return database.get_mistakes(
        theme=theme,
        category=category,
        time_class=time_class,
        solved=solved_filter,
        limit=limit,
        offset=offset
    )

@app.get("/api/mistake/{mistake_id}")
def get_mistake(mistake_id: int):
    conn = database.get_db()
    row = conn.execute("SELECT * FROM mistakes WHERE id = ?", (mistake_id,)).fetchone()
    conn.close()
    if not row:
        return JSONResponse(status_code=404, content={"error": "Mistake not found"})
    return dict(row)

@app.post("/api/mistake/{mistake_id}/attempt")
def submit_attempt(mistake_id: int, req: AttemptRequest):
    conn = database.get_db()
    row = conn.execute("SELECT * FROM mistakes WHERE id = ?", (mistake_id,)).fetchone()
    conn.close()

    if not row:
        return JSONResponse(status_code=404, content={"error": "Mistake not found"})

    mistake = dict(row)
    fen_before = mistake["fen_before"]
    board = chess.Board(fen_before)

    # Validate move
    user_uci = req.move.strip().lower()
    best_uci = mistake["best_move"].strip().lower()

    # Also parse if user submitted SAN
    matched_move = None
    try:
        if len(user_uci) in (4, 5):
            matched_move = chess.Move.from_uci(user_uci)
            if matched_move not in board.legal_moves:
                matched_move = None
    except Exception:
        matched_move = None

    if matched_move is None:
        try:
            matched_move = board.parse_san(req.move.strip())
        except Exception:
            pass

    if matched_move is None:
        return {"success": False, "is_legal": False, "message": "Illegal move for this position."}

    user_move_uci = matched_move.uci()
    is_correct = (user_move_uci == best_uci)

    # If not exact best move, check if it's virtually equal in quality
    bot_reply = None
    bot_reply_san = None

    if is_correct:
        database.record_attempt(mistake_id, success=True)
        # Calculate opponent's bot response from PV or engine so player can play it out!
        board.push(matched_move)
        if not board.is_game_over():
            # Use Stockfish to find engine's defensive reply
            try:
                engine = analyzer.get_engine()
                res = engine.analyse(board, chess.engine.Limit(time=0.08, depth=10))
                pv = res.get("pv", [])
                if pv:
                    bot_reply = pv[0].uci()
                    bot_reply_san = board.san(pv[0])
                engine.quit()
            except Exception as e:
                print(f"Engine bot reply error: {e}")

        return {
            "success": True,
            "is_legal": True,
            "message": "Correct move! You found the winning solution.",
            "bot_reply": bot_reply,
            "bot_reply_san": bot_reply_san,
            "fen_after": board.fen()
        }
    else:
        database.record_attempt(mistake_id, success=False)
        return {
            "success": False,
            "is_legal": True,
            "message": f"Not quite the best move. Try again!",
            "best_move": mistake["best_move"],
            "best_move_san": mistake["best_move_san"]
        }

@app.post("/api/bot-move")
def get_bot_move(req: BotMoveRequest):
    """
    Returns the bot opponent's move for any given board FEN so the user can play out the position to a full win.
    """
    try:
        board = chess.Board(req.fen)
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid FEN"})

    if board.is_game_over():
        return {
            "game_over": True,
            "is_checkmate": board.is_checkmate(),
            "is_stalemate": board.is_stalemate()
        }

    try:
        engine = analyzer.get_engine()
        depth = min(max(req.difficulty or 10, 5), 15)
        res = engine.analyse(board, chess.engine.Limit(time=0.1, depth=depth))
        pv = res.get("pv", [])
        engine.quit()

        if not pv:
            return {"game_over": True}

        engine_move = pv[0]
        san = board.san(engine_move)
        board.push(engine_move)

        return {
            "game_over": board.is_game_over(),
            "move": engine_move.uci(),
            "san": san,
            "fen_after": board.fen(),
            "is_checkmate": board.is_checkmate(),
            "is_stalemate": board.is_stalemate(),
            "is_check": board.is_check()
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

def run_sync_task(username: str, max_games: int):
    global analysis_state
    analysis_state["is_syncing"] = True
    analysis_state["last_message"] = f"Fetching up to {max_games} recent games for {username}..."
    try:
        fetched = analyzer.fetch_recent_games(username, max_games=max_games)
        analysis_state["last_message"] = f"Fetched {len(fetched)} games. Analyzing positions with Stockfish..."
        result = analyzer.analyze_pending_games(limit_games=max_games, username=username)
        analysis_state["last_message"] = f"Finished! Analyzed {result['games_analyzed']} games, extracted {result['mistakes_found']} tailored lessons."
    except Exception as e:
        analysis_state["last_message"] = f"Error during sync: {str(e)}"
    finally:
        analysis_state["is_syncing"] = False

@app.post("/api/sync")
def trigger_sync(background_tasks: BackgroundTasks, username: str = Query(..., description="Chess.com username"), games_count: int = 25):
    global analysis_state
    clean_user = username.strip()
    if not clean_user:
        return JSONResponse(status_code=400, content={"error": "Username is required"})
    if analysis_state["is_syncing"]:
        return {"status": "busy", "message": "A sync job is already currently in progress."}

    background_tasks.add_task(run_sync_task, clean_user, games_count)
    return {"status": "started", "message": f"Sync started for {clean_user}."}

@app.get("/api/sync/status")
def get_sync_status():
    global analysis_state
    return analysis_state

# Serve index.html at root
@app.get("/")
def serve_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

# Mount static folder
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

if __name__ == "__main__":
    import uvicorn
    print("Starting Chess Mistake Academy server at http://127.0.0.1:8000 ...")
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=False)
