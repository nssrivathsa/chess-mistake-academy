# ♟️ Chess Mistake Academy

An automated chess coaching and interactive training web application that connects to any **Chess.com** account, analyzes games move-by-move using **Stockfish**, detects critical mistakes and blunders, and automatically generates **custom interactive lessons** where you can retry your mistakes and play out positions against the engine to convert them to a win.

---

## ✨ Features

- **Automated Match Ingestion**: Fetches rated games (Bullet, Blitz, Rapid, Daily) directly from Chess.com's public API.
- **Stockfish Blunder Detection**:
  - Calculates evaluation drops across each move.
  - Automatically identifies **Blunders** ($-3.0+$ pawns), **Missed Wins**, and **Tactical Mistakes**.
- **Tactical Theme Classification**:
  - Automatically classifies mistakes into motifs: *Endgame Blunder*, *Tactical Blunder*, *Hanging Piece*, *Missed Capture*, *Missed Fork*, *Opening Inaccuracy*, and *Blundered Mate*.
- **Interactive "Play to Win" Training Board**:
  - Auto-flips board perspective to your played color (White or Black).
  - Review what move was originally played vs. the engine's best continuation.
  - **Play vs Stockfish**: Practice converting your advantage directly against the engine defense until checkmate!
- **Curriculum & Leak Diagnostics**: Filter lessons by tactical theme, blunder severity, and completion status.
- **1-Click Sync**: Enter any Chess.com username and click **"Sync Chess.com Games"** to analyze matches and generate fresh lessons.

---

## 🚀 Quickstart

### 1. Requirements
- Python 3.9+
- Stockfish chess engine ([Download Stockfish](https://stockfishchess.org/download/))

### 2. Setup
Install Python dependencies:
```bash
pip install fastapi uvicorn chess requests pydantic
```

*(Optional)* Download or place Stockfish into `engine/stockfish/` or ensure `stockfish` is in your system `PATH`.

### 3. Launch
Run the application server:
```bash
python server.py
```
Or on Windows:
```bash
run.bat
```

Open your browser at:
```
http://localhost:8000
```

---

## 🛠️ Architecture

- **Backend**: FastAPI, Python-Chess, SQLite
- **Engine**: Stockfish UCI + browser-side Stockfish.js (WebAssembly)
- **Frontend**: Responsive single-page application with Chessboard.js, Chess.js, and dark-mode CSS

---

## 📜 License
MIT License.
