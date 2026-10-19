import sqlite3
import os
import json
from typing import List, Dict, Any, Optional

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chess_trainer.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS games (
        id TEXT PRIMARY KEY,
        url TEXT,
        white_username TEXT,
        white_rating INTEGER,
        black_username TEXT,
        black_rating INTEGER,
        time_class TEXT,
        time_control TEXT,
        eco TEXT,
        eco_url TEXT,
        user_color TEXT,
        result TEXT,
        end_time INTEGER,
        pgn TEXT,
        analyzed INTEGER DEFAULT 0
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS mistakes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game_id TEXT,
        move_number INTEGER,
        user_color TEXT,
        fen_before TEXT,
        fen_after TEXT,
        user_move TEXT,
        user_move_san TEXT,
        best_move TEXT,
        best_move_san TEXT,
        pv TEXT,
        eval_before REAL,
        eval_after REAL,
        eval_drop REAL,
        category TEXT,
        theme TEXT,
        opponent_name TEXT,
        opponent_rating INTEGER,
        time_class TEXT,
        notes TEXT,
        solved INTEGER DEFAULT 0,
        attempts INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (game_id) REFERENCES games (id)
    )
    """)
    
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_mistakes_category ON mistakes (category);
    """)
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_mistakes_theme ON mistakes (theme);
    """)
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_mistakes_solved ON mistakes (solved);
    """)
    
    conn.commit()
    conn.close()

def save_game(game_data: Dict[str, Any], user_username: str = "") -> bool:
    conn = get_db()
    cursor = conn.cursor()
    
    game_id = game_data.get("uuid") or game_data.get("url", "")
    white = game_data.get("white", {})
    black = game_data.get("black", {})
    
    is_white = white.get("username", "").lower() == user_username.lower()
    user_color = "white" if is_white else "black"
    user_result = white.get("result", "") if is_white else black.get("result", "")
    
    try:
        cursor.execute("""
        INSERT OR IGNORE INTO games (
            id, url, white_username, white_rating, black_username, black_rating,
            time_class, time_control, eco, eco_url, user_color, result, end_time, pgn, analyzed
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """, (
            game_id,
            game_data.get("url", ""),
            white.get("username", ""),
            white.get("rating", 0),
            black.get("username", ""),
            black.get("rating", 0),
            game_data.get("time_class", ""),
            game_data.get("time_control", ""),
            game_data.get("eco", ""),
            game_data.get("eco_url", ""),
            user_color,
            user_result,
            game_data.get("end_time", 0),
            game_data.get("pgn", "")
        ))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error saving game {game_id}: {e}")
        return False
    finally:
        conn.close()

def save_mistake(mistake_data: Dict[str, Any]):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
        INSERT INTO mistakes (
            game_id, move_number, user_color, fen_before, fen_after,
            user_move, user_move_san, best_move, best_move_san, pv,
            eval_before, eval_after, eval_drop, category, theme,
            opponent_name, opponent_rating, time_class, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            mistake_data.get("game_id"),
            mistake_data.get("move_number"),
            mistake_data.get("user_color"),
            mistake_data.get("fen_before"),
            mistake_data.get("fen_after"),
            mistake_data.get("user_move"),
            mistake_data.get("user_move_san"),
            mistake_data.get("best_move"),
            mistake_data.get("best_move_san"),
            mistake_data.get("pv", ""),
            mistake_data.get("eval_before"),
            mistake_data.get("eval_after"),
            mistake_data.get("eval_drop"),
            mistake_data.get("category"),
            mistake_data.get("theme"),
            mistake_data.get("opponent_name"),
            mistake_data.get("opponent_rating"),
            mistake_data.get("time_class"),
            mistake_data.get("notes")
        ))
        conn.commit()
    except Exception as e:
        print(f"Error saving mistake: {e}")
    finally:
        conn.close()

def mark_game_analyzed(game_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE games SET analyzed = 1 WHERE id = ?", (game_id,))
    conn.commit()
    conn.close()

def get_mistakes(
    theme: Optional[str] = None,
    category: Optional[str] = None,
    time_class: Optional[str] = None,
    solved: Optional[int] = None,
    limit: int = 50,
    offset: int = 0
) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    
    query = "SELECT * FROM mistakes WHERE 1=1"
    params = []
    
    if theme and theme != "all":
        query += " AND theme = ?"
        params.append(theme)
    if category and category != "all":
        query += " AND category = ?"
        params.append(category)
    if time_class and time_class != "all":
        query += " AND time_class = ?"
        params.append(time_class)
    if solved is not None:
        query += " AND solved = ?"
        params.append(solved)
        
    query += " ORDER BY eval_drop DESC, id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    results = [dict(row) for row in rows]
    conn.close()
    return results

def get_stats() -> Dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()
    
    total_games = cursor.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    analyzed_games = cursor.execute("SELECT COUNT(*) FROM games WHERE analyzed = 1").fetchone()[0]
    total_mistakes = cursor.execute("SELECT COUNT(*) FROM mistakes").fetchone()[0]
    solved_mistakes = cursor.execute("SELECT COUNT(*) FROM mistakes WHERE solved = 1").fetchone()[0]
    
    by_category = {}
    for row in cursor.execute("SELECT category, COUNT(*) FROM mistakes GROUP BY category"):
        by_category[row[0]] = row[1]
        
    by_theme = {}
    for row in cursor.execute("SELECT theme, COUNT(*) FROM mistakes GROUP BY theme ORDER BY COUNT(*) DESC"):
        by_theme[row[0]] = row[1]
        
    by_time_class = {}
    for row in cursor.execute("SELECT time_class, COUNT(*) FROM mistakes GROUP BY time_class"):
        by_time_class[row[0]] = row[1]
        
    conn.close()
    
    return {
        "total_games": total_games,
        "analyzed_games": analyzed_games,
        "total_mistakes": total_mistakes,
        "solved_mistakes": solved_mistakes,
        "by_category": by_category,
        "by_theme": by_theme,
        "by_time_class": by_time_class
    }

def record_attempt(mistake_id: int, success: bool):
    conn = get_db()
    cursor = conn.cursor()
    if success:
        cursor.execute("UPDATE mistakes SET attempts = attempts + 1, solved = 1 WHERE id = ?", (mistake_id,))
    else:
        cursor.execute("UPDATE mistakes SET attempts = attempts + 1 WHERE id = ?", (mistake_id,))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
