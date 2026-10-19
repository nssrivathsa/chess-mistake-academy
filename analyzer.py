import io
import os
import sys
import json
import urllib.request
from typing import List, Dict, Any, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import chess
import chess.pgn
import chess.engine

import database

import shutil

USER_AGENT = "ChessMistakeAcademy/1.0 (https://github.com/nssrivathsa/chess-mistake-academy)"

def get_engine_path() -> str:
    # 1. Environment variable
    env_path = os.environ.get("STOCKFISH_PATH")
    if env_path and os.path.exists(env_path):
        return env_path
    
    # 2. System PATH
    which_path = shutil.which("stockfish") or shutil.which("stockfish.exe")
    if which_path:
        return which_path

    # 3. Local engine directory
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base_dir, "engine", "stockfish", "stockfish-windows-x86-64-avx2.exe"),
        os.path.join(base_dir, "engine", "stockfish", "stockfish.exe"),
        os.path.join(base_dir, "engine", "stockfish", "stockfish"),
        os.path.join(base_dir, "stockfish.exe"),
        os.path.join(base_dir, "stockfish")
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
            
    raise FileNotFoundError(
        "Stockfish binary not found. Please install Stockfish, set STOCKFISH_PATH, "
        "or place it in the engine/stockfish directory."
    )

def get_engine():
    engine_path = get_engine_path()
    return chess.engine.SimpleEngine.popen_uci(engine_path)

def fetch_recent_games(username: str, max_games: int = 50) -> List[Dict[str, Any]]:
    """
    Fetches the most recent games from chess.com for the user and saves them to DB.
    """
    archives_url = f"https://api.chess.com/pub/player/{username.lower()}/games/archives"
    req = urllib.request.Request(archives_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode("utf-8"))
            archives = data.get("archives", [])
    except Exception as e:
        print(f"Error fetching archives: {e}")
        return []

    collected_games = []
    # Traverse archives in reverse (most recent months first)
    for archive_url in reversed(archives):
        if len(collected_games) >= max_games:
            break
        try:
            areq = urllib.request.Request(archive_url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(areq) as resp:
                month_data = json.loads(resp.read().decode("utf-8"))
                games = month_data.get("games", [])
                for g in reversed(games):
                    if g.get("rules") != "chess":
                        continue
                    database.save_game(g, username)
                    collected_games.append(g)
                    if len(collected_games) >= max_games:
                        break
        except Exception as e:
            print(f"Error fetching archive {archive_url}: {e}")
            continue

    return collected_games

def classify_theme(board_before: chess.Board, user_move: chess.Move, best_move: chess.Move, eval_after: float) -> str:
    """
    Determines the tactical/strategic theme of the mistake.
    """
    # 0. Check if user blundered into mate
    if eval_after <= -10.0:
        return "blundered_mate"

    # 1. Opening trap (first 8 moves)
    if board_before.fullmove_number <= 8:
        return "opening_trap"

    # 2. Endgame blunder (total non-pawn pieces <= 6)
    non_pawn_pieces = len([
        p for p in board_before.piece_map().values()
        if p.piece_type not in (chess.PAWN, chess.KING)
    ])
    if non_pawn_pieces <= 6:
        return "endgame_blunder"

    # 3. Hanging piece check: user moved a piece to a square attacked and under-defended
    dest = user_move.to_square
    moving_piece = board_before.piece_at(user_move.from_square)
    user_color = board_before.turn
    opp_color = not user_color

    board_after = board_before.copy()
    board_after.push(user_move)

    opp_attackers = board_after.attackers(opp_color, dest)
    user_defenders = board_after.attackers(user_color, dest)
    if opp_attackers:
        if not user_defenders:
            return "hanging_piece"
        # If moving queen/rook to a square attacked by lower value piece
        if moving_piece and moving_piece.piece_type in (chess.QUEEN, chess.ROOK):
            cheaper_attackers = [
                sq for sq in opp_attackers
                if board_after.piece_at(sq) and board_after.piece_at(sq).piece_type in (chess.PAWN, chess.KNIGHT, chess.BISHOP)
            ]
            if cheaper_attackers:
                return "hanging_piece"

    # 4. Missed Fork by user
    if best_move:
        test_board = board_before.copy()
        test_board.push(best_move)
        best_dest = best_move.to_square
        best_piece = board_before.piece_at(best_move.from_square)
        if best_piece and best_piece.piece_type == chess.KNIGHT:
            attacked_squares = test_board.attacks(best_dest)
            valuable_targets = [
                sq for sq in attacked_squares
                if test_board.piece_at(sq) and test_board.piece_at(sq).color == opp_color
                and test_board.piece_at(sq).piece_type in (chess.KING, chess.QUEEN, chess.ROOK)
            ]
            if len(valuable_targets) >= 2:
                return "missed_fork"

    # 5. Check if best move was a capture
    if board_before.is_capture(best_move):
        return "missed_capture"

    # 6. King safety / check
    if board_before.is_check():
        return "king_safety"

    return "tactical_blunder"

def generate_coaching_notes(
    theme: str,
    user_san: str,
    best_san: str,
    eval_before: float,
    eval_after: float,
    eval_drop: float,
    eco: str
) -> str:
    theme_titles = {
        "hanging_piece": "Loose Piece Blunder",
        "missed_fork": "Missed Fork Opportunity",
        "endgame_blunder": "Endgame Precision Needed",
        "opening_trap": "Opening Inaccuracy",
        "missed_capture": "Missed Tactical Capture",
        "king_safety": "King Under Pressure",
        "blundered_mate": "Fatal Defensive Lapse",
        "tactical_blunder": "Positional Blunder"
    }
    title = theme_titles.get(theme, "Position Review")

    if eval_after <= -10.0:
        context = f"Playing {user_san} allowed opponent an unstoppable mating sequence or decisive material crush."
    elif eval_before > 2.0 and eval_after < 0.5:
        context = f"You had built a winning advantage (+{eval_before:.1f}), but {user_san} surrendered all the advantage."
    elif eval_drop >= 4.0:
        context = f"Playing {user_san} resulted in an immediate {eval_drop:.1f}-point swing."
    else:
        context = f"The move {user_san} ceded tactical control (-{eval_drop:.1f} pawns)."

    solution = f"The winning move was {best_san}. Finding moves like this in this structure will directly boost your rating."
    return f"**{title}**: {context} {solution}"

def analyze_game(game_row: Dict[str, Any], engine: chess.engine.SimpleEngine, username: str = None) -> int:
    """
    Analyzes a single game's PGN and records mistakes.
    Returns the count of mistakes found.
    """
    pgn_text = game_row.get("pgn", "")
    if not pgn_text:
        return 0

    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if not game:
        return 0

    headers = game.headers
    if username:
        white_name = headers.get("White", "").lower()
        user_is_white = (white_name == username.lower())
    else:
        user_is_white = (game_row.get("user_color", "white").lower() == "white")
    user_color = chess.WHITE if user_is_white else chess.BLACK

    opponent_name = headers.get("Black" if user_is_white else "White", "Opponent")
    opponent_rating = int(headers.get("BlackElo" if user_is_white else "WhiteElo", 0) or 0)
    time_class = game_row.get("time_class", "blitz")
    game_id = game_row.get("id")

    board = game.board()
    mistakes_found = 0

    # Limit search time per position (fast & accurate depth)
    search_limit = chess.engine.Limit(time=0.06, depth=10)

    for node in game.mainline():
        move = node.move
        is_user_turn = (board.turn == user_color)

        if is_user_turn:
            fen_before = board.fen()
            
            # Analyze position BEFORE user moves
            try:
                info_before = engine.analyse(board, search_limit)
            except Exception as e:
                print(f"Engine error: {e}")
                board.push(move)
                continue

            score_obj = info_before.get("score")
            if score_obj is None:
                board.push(move)
                continue

            pov_score_before = score_obj.pov(user_color)
            if pov_score_before.is_mate():
                eval_before_val = 15.0 if pov_score_before.mate() > 0 else -15.0
            else:
                eval_before_val = round(pov_score_before.score(mate_score=1500) / 100.0, 2)

            pv = info_before.get("pv", [])
            best_move = pv[0] if pv else None
            best_move_san = board.san(best_move) if best_move else ""
            pv_str = " ".join([m.uci() for m in pv[:6]])

            # Apply user's move
            user_move_san = board.san(move)
            board.push(move)
            fen_after = board.fen()

            # If user delivered checkmate, this was a winning move!
            if board.is_checkmate():
                continue

            # If user stalemated when winning
            if board.is_stalemate():
                if eval_before_val >= 2.0:
                    eval_after_val = 0.0
                    eval_drop = eval_before_val
                    mistake_record = {
                        "game_id": game_id,
                        "move_number": board.fullmove_number,
                        "user_color": "white" if user_is_white else "black",
                        "fen_before": fen_before,
                        "fen_after": fen_after,
                        "user_move": move.uci(),
                        "user_move_san": user_move_san,
                        "best_move": best_move.uci() if best_move else "",
                        "best_move_san": best_move_san,
                        "pv": pv_str,
                        "eval_before": eval_before_val,
                        "eval_after": 0.0,
                        "eval_drop": eval_drop,
                        "category": "blunder",
                        "theme": "endgame_blunder",
                        "opponent_name": opponent_name,
                        "opponent_rating": opponent_rating,
                        "time_class": time_class,
                        "notes": f"**Stalemate Blunder**: You had a completely winning position (+{eval_before_val:.1f}), but {user_move_san} allowed an accidental stalemate draw! The winning move was {best_move_san}."
                    }
                    database.save_mistake(mistake_record)
                    mistakes_found += 1
                continue

            # Analyze position AFTER user moves
            try:
                info_after = engine.analyse(board, search_limit)
            except Exception as e:
                print(f"Engine error: {e}")
                continue

            score_after_obj = info_after.get("score")
            if score_after_obj is None:
                continue

            pov_score_after = score_after_obj.pov(user_color)
            if pov_score_after.is_mate():
                eval_after_val = 15.0 if pov_score_after.mate() > 0 else -15.0
            else:
                eval_after_val = round(pov_score_after.score(mate_score=1500) / 100.0, 2)

            eval_drop = round(eval_before_val - eval_after_val, 2)

            # Mistake trigger conditions:
            # 1. Did not play best move (or move with virtually identical eval)
            # 2. Eval drop >= 1.8 pawns
            # 3. Or blundered into mate (eval_before > -3.0 and eval_after <= -10.0)
            # 4. Or threw away a winning position (eval_before >= 2.0 and eval_drop >= 1.3)
            is_mistake = (
                (best_move and move != best_move) and
                (
                    eval_drop >= 1.8 or
                    (eval_before_val >= 2.0 and eval_drop >= 1.3) or
                    (eval_before_val > -3.0 and eval_after_val <= -10.0)
                )
            )

            if is_mistake:
                category = "blunder" if eval_drop >= 3.0 or eval_after_val <= -10.0 else "mistake"
                if eval_before_val >= 3.0 and eval_after_val <= 0.5:
                    category = "missed_win"

                theme = classify_theme(chess.Board(fen_before), move, best_move, eval_after_val)
                notes = generate_coaching_notes(
                    theme, user_move_san, best_move_san,
                    eval_before_val, eval_after_val, eval_drop,
                    game_row.get("eco", "")
                )

                mistake_record = {
                    "game_id": game_id,
                    "move_number": board.fullmove_number,
                    "user_color": "white" if user_is_white else "black",
                    "fen_before": fen_before,
                    "fen_after": fen_after,
                    "user_move": move.uci(),
                    "user_move_san": user_move_san,
                    "best_move": best_move.uci(),
                    "best_move_san": best_move_san,
                    "pv": pv_str,
                    "eval_before": eval_before_val,
                    "eval_after": eval_after_val,
                    "eval_drop": eval_drop,
                    "category": category,
                    "theme": theme,
                    "opponent_name": opponent_name,
                    "opponent_rating": opponent_rating,
                    "time_class": time_class,
                    "notes": notes
                }
                database.save_mistake(mistake_record)
                mistakes_found += 1
        else:
            board.push(move)

    database.mark_game_analyzed(game_id)
    return mistakes_found

def analyze_pending_games(limit_games: int = 20, username: str = None) -> Dict[str, Any]:
    """
    Analyzes unanalyzed games in SQLite.
    """
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM games WHERE analyzed = 0 ORDER BY end_time DESC LIMIT ?", (limit_games,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    if not rows:
        return {"games_analyzed": 0, "mistakes_found": 0}

    engine = get_engine()
    total_mistakes = 0
    analyzed_count = 0

    try:
        for r in rows:
            m_count = analyze_game(r, engine, username)
            total_mistakes += m_count
            analyzed_count += 1
    finally:
        engine.quit()

    return {"games_analyzed": analyzed_count, "mistakes_found": total_mistakes}
