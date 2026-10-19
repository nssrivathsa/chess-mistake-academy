// Chess Mistake Academy - Interactive Frontend Logic

let board = null;
let game = new Chess();
let currentMistake = null;
let allMistakes = [];
let isSparringMode = false;
let userColor = 'white';

// Filter state
let currentFilters = {
  theme: 'all',
  category: 'all',
  time_class: 'all',
  solved: 'all'
};

// Initialize app when DOM is ready
$(document).ready(function() {
  const savedUser = localStorage.getItem('chess_username') || '';
  if (savedUser) {
    $('#username-input').val(savedUser);
  }
  initBoard();
  loadStats();
  loadMistakes();
  setupEventListeners();
});

function initBoard() {
  const config = {
    draggable: true,
    position: 'start',
    pieceTheme: '/static/img/chesspieces/wikipedia/{piece}.png',
    onDragStart: onDragStart,
    onDrop: onDrop,
    onSnapEnd: onSnapEnd
  };
  board = Chessboard('chess-board', config);
  $(window).resize(board.resize);
}

function onDragStart(source, piece, position, orientation) {
  // Do not allow picking up pieces if game is over
  if (game.game_over()) return false;

  // Only allow player to move their own pieces
  if (userColor === 'white' && piece.search(/^b/) !== -1) return false;
  if (userColor === 'black' && piece.search(/^w/) !== -1) return false;

  // In training mode, only allow the user to make 1 move until validated
  if (!isSparringMode && game.turn() !== userColor[0]) return false;

  return true;
}

function onDrop(source, target) {
  clearHighlights();

  // Try move in chess.js
  const move = game.move({
    from: source,
    to: target,
    promotion: 'q' // default to queen for simplicity
  });

  // Illegal move
  if (move === null) return 'snapback';

  const moveUci = source + target + (move.promotion ? move.promotion : '');

  if (!isSparringMode) {
    // We are solving the puzzle/mistake!
    handlePuzzleAttempt(moveUci, move);
  } else {
    // We are in sparring mode against Stockfish!
    handleSparringUserMove();
  }
}

function onSnapEnd() {
  board.position(game.fen());
}

async function handlePuzzleAttempt(moveUci, move) {
  if (!currentMistake) return;

  try {
    const res = await fetch(`/api/mistake/${currentMistake.id}/attempt`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ move: moveUci })
    });
    const data = await res.json();

    if (data.success) {
      // User found the winning move!
      showStatus('success', '🎯 Excellent! You found the winning engine move!');
      highlightSquare(move.from, 'highlight-best');
      highlightSquare(move.to, 'highlight-best');
      revealSolutionBox(currentMistake.best_move_san);
      
      // Mark as solved in UI
      currentMistake.solved = 1;
      updateMistakeItemInList(currentMistake.id, true);
      loadStats();

      // If bot has a continuation move, play it and transition into sparring mode!
      if (data.bot_reply) {
        setTimeout(() => {
          const botMoveObj = game.move({
            from: data.bot_reply.slice(0, 2),
            to: data.bot_reply.slice(2, 4),
            promotion: data.bot_reply.length > 4 ? data.bot_reply[4] : undefined
          });
          board.position(game.fen());
          if (botMoveObj) {
            highlightSquare(botMoveObj.from, 'highlight-hint');
            highlightSquare(botMoveObj.to, 'highlight-hint');
          }
          enableSparringMode(true);
        }, 600);
      } else {
        showStatus('success', '🏆 Checkmate delivered! You completely converted the position!');
      }
    } else {
      // Wrong move - undo on board
      game.undo();
      setTimeout(() => board.position(game.fen()), 250);
      showStatus('error', `❌ ${data.message || 'Not the best move. Try again!'}`);
      highlightSquare(move.from, 'highlight-blunder');
    }
  } catch (err) {
    console.error('Error submitting attempt:', err);
  }
}

async function handleSparringUserMove() {
  updateEvalBarFromFen(game.fen());

  if (game.game_over()) {
    if (game.in_checkmate()) {
      showStatus('success', '🏆 Checkmate! You won against Stockfish!');
    } else if (game.in_draw()) {
      showStatus('prompt', 'Game drawn by repetition / stalemate.');
    }
    return;
  }

  showStatus('sparring', 'Stockfish is calculating response...');

  try {
    const res = await fetch('/api/bot-move', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fen: game.fen(), difficulty: 8 })
    });
    const data = await res.json();

    if (data.move) {
      setTimeout(() => {
        const fromSq = data.move.slice(0, 2);
        const toSq = data.move.slice(2, 4);
        const promo = data.move.length > 4 ? data.move[4] : undefined;

        game.move({ from: fromSq, to: toSq, promotion: promo });
        board.position(game.fen());
        highlightSquare(fromSq, 'highlight-hint');
        highlightSquare(toSq, 'highlight-hint');

        if (data.is_checkmate) {
          showStatus('error', 'Checkmate by Stockfish! Retry to find a better defense.');
        } else if (data.is_check) {
          showStatus('sparring', 'Check! Your turn to respond.');
        } else {
          showStatus('sparring', `Bot played ${data.san}. Your turn to convert!`);
        }
      }, 350);
    }
  } catch (err) {
    console.error('Error getting bot move:', err);
  }
}

function enableSparringMode(autoStart = false) {
  isSparringMode = true;
  $('#btn-spar').addClass('btn-primary').text('🎮 In Sparring Mode vs AI');
  if (autoStart) {
    showStatus('sparring', '⚔️ Position alive! Play it out against Stockfish to seal the victory.');
  } else {
    showStatus('sparring', '⚔️ Sparring Mode: Make your moves and Stockfish will defend!');
  }
}

function resetPosition() {
  if (!currentMistake) return;
  isSparringMode = false;
  $('#btn-spar').removeClass('btn-primary').html('⚔️ Play vs Stockfish');
  clearHighlights();
  game.load(currentMistake.fen_before);
  board.position(currentMistake.fen_before);
  updateEvalBar(currentMistake.eval_before);
  hideSolutionBox();
  showStatus('prompt', `Your turn! Play the best move for ${userColor}.`);
}

function selectMistake(mistake) {
  currentMistake = mistake;
  isSparringMode = false;
  $('#btn-spar').removeClass('btn-primary').html('⚔️ Play vs Stockfish');

  // Highlight active in sidebar
  $('.mistake-item').removeClass('active');
  $(`#mistake-card-${mistake.id}`).addClass('active');

  // Set orientation
  userColor = mistake.user_color.toLowerCase();
  board.orientation(userColor);

  // Load board state
  game.load(mistake.fen_before);
  board.position(mistake.fen_before);
  clearHighlights();

  // Highlight what user originally played as blunder
  if (mistake.user_move && mistake.user_move.length >= 4) {
    const fromSq = mistake.user_move.slice(0, 2);
    const toSq = mistake.user_move.slice(2, 4);
    // temporarily flash the blunder squares
  }

  // Update panels
  updateMeta(mistake);
  updateEvalBar(mistake.eval_before);
  hideSolutionBox();
  showStatus('prompt', `Move ${mistake.move_number}: Find the winning move for ${userColor}!`);
}

function updateMeta(mistake) {
  $('#meta-opponent').text(mistake.opponent_name || 'Opponent');
  $('#meta-rating').text(mistake.opponent_rating || '—');
  $('#meta-time-class').text((mistake.time_class || '').toUpperCase());
  $('#meta-move-num').text(`Move ${mistake.move_number}`);

  // Theme badge
  const themeNames = {
    'endgame_blunder': 'Endgame Blunder',
    'tactical_blunder': 'Tactical Blunder',
    'opening_trap': 'Opening Inaccuracy',
    'hanging_piece': 'Hanging Piece',
    'missed_capture': 'Missed Capture',
    'missed_fork': 'Missed Fork',
    'blundered_mate': 'Blundered Mate'
  };
  $('#meta-theme').text(themeNames[mistake.theme] || mistake.theme);
  $('#meta-eval-drop').text(`-${mistake.eval_drop.toFixed(1)} pawns`);

  // Blunder move text
  $('#blunder-move-val').text(mistake.user_move_san || mistake.user_move);
  $('#solution-move-val').text('???');

  // Notes
  $('#coach-notes').html(renderMarkdown(mistake.notes));
}

function revealSolutionBox(san) {
  $('#solution-move-val').text(san || (currentMistake ? currentMistake.best_move_san : '—'));
}

function hideSolutionBox() {
  $('#solution-move-val').text('???');
}

function showHint() {
  if (!currentMistake || !currentMistake.best_move) return;
  const fromSquare = currentMistake.best_move.slice(0, 2);
  highlightSquare(fromSquare, 'highlight-hint');
  showStatus('prompt', `💡 Hint: Focus on the piece on ${fromSquare.toUpperCase()}!`);
}

function showSolution() {
  if (!currentMistake) return;
  revealSolutionBox(currentMistake.best_move_san);
  const fromSq = currentMistake.best_move.slice(0, 2);
  const toSq = currentMistake.best_move.slice(2, 4);
  highlightSquare(fromSq, 'highlight-best');
  highlightSquare(toSq, 'highlight-best');
  showStatus('prompt', `Winning move: ${currentMistake.best_move_san}. You can now practice playing it!`);
}

function highlightSquare(square, className) {
  $(`#chess-board .square-${square}`).addClass(className);
}

function clearHighlights() {
  $('#chess-board .square-55d63').removeClass('highlight-blunder highlight-best highlight-hint');
}

function updateEvalBar(evalScore) {
  // evalScore: +val is white advantage, -val is black advantage
  let clamped = Math.max(-10, Math.min(10, evalScore || 0));
  // Map -10 to +10 into 0% to 100%
  let percent = 50 + (clamped / 20) * 100;
  $('#eval-fill').css('height', `${percent}%`);
}

function updateEvalBarFromFen(fen) {
  // Simple heuristic or keep position
}

function showStatus(type, msg) {
  const banner = $('#status-banner');
  banner.removeClass('status-prompt status-success status-error status-sparring');
  banner.addClass(`status-${type}`);
  banner.text(msg);
}

async function loadStats() {
  try {
    const res = await fetch('/api/stats');
    const data = await res.json();
    $('#stat-total-games').text(data.total_games || 0);
    $('#stat-analyzed-games').text(data.analyzed_games || 0);
    $('#stat-total-mistakes').text(data.total_mistakes || 0);
    $('#stat-solved').text(data.solved_mistakes || 0);
  } catch (err) {
    console.error('Error loading stats:', err);
  }
}

async function loadMistakes() {
  const query = new URLSearchParams(currentFilters).toString();
  try {
    const res = await fetch(`/api/mistakes?${query}&limit=100`);
    allMistakes = await res.json();
    renderMistakeList(allMistakes);
    if (allMistakes.length > 0 && !currentMistake) {
      selectMistake(allMistakes[0]);
    }
  } catch (err) {
    console.error('Error loading mistakes:', err);
  }
}

function renderMistakeList(mistakes) {
  const listEl = $('#mistake-list');
  listEl.empty();

  if (mistakes.length === 0) {
    listEl.html('<div style="color:#64748b;text-align:center;padding:24px;">No mistakes found for this filter. Try syncing more games!</div>');
    return;
  }

  mistakes.forEach((m, idx) => {
    const activeClass = currentMistake && currentMistake.id === m.id ? 'active' : '';
    const badgeClass = `badge-${m.category}`;
    const solvedIcon = m.solved ? '✓ Solved' : '⭕ Retry';
    const solvedStyle = m.solved ? 'color:#10b981;font-weight:bold;' : 'color:#94a3b8;';

    const itemHtml = `
      <div class="mistake-item ${activeClass}" id="mistake-card-${m.id}" onclick="onMistakeCardClick(${m.id})">
        <div class="mistake-top">
          <span class="mistake-theme-badge ${badgeClass}">${formatTheme(m.theme)}</span>
          <span class="eval-drop-badge">-${m.eval_drop.toFixed(1)}</span>
        </div>
        <div class="mistake-desc">
          <span>Move ${m.move_number} vs <strong>${m.opponent_name || 'Opponent'}</strong></span>
          <span style="${solvedStyle}">${solvedIcon}</span>
        </div>
        <div class="mistake-footer">
          <span>You played: <strong style="color:#ef4444">${m.user_move_san || m.user_move}</strong></span>
          <span>${(m.time_class || '').toUpperCase()}</span>
        </div>
      </div>
    `;
    listEl.append(itemHtml);
  });
}

function updateMistakeItemInList(id, isSolved) {
  const card = $(`#mistake-card-${id}`);
  if (card.length) {
    card.find('.mistake-desc span:last-child').html('✓ Solved').css({'color': '#10b981', 'font-weight': 'bold'});
  }
}

window.onMistakeCardClick = function(id) {
  const m = allMistakes.find(item => item.id === id);
  if (m) selectMistake(m);
};

function formatTheme(theme) {
  if (!theme) return 'Tactics';
  return theme.replace(/_/g, ' ');
}

function renderMarkdown(txt) {
  if (!txt) return '';
  return txt
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>');
}

function setupEventListeners() {
  // Filter selects
  $('#filter-theme').on('change', function() {
    currentFilters.theme = $(this).val();
    loadMistakes();
  });

  $('#filter-category').on('change', function() {
    currentFilters.category = $(this).val();
    loadMistakes();
  });

  $('#filter-time').on('change', function() {
    currentFilters.time_class = $(this).val();
    loadMistakes();
  });

  // Solved tabs
  $('.tab-btn').on('click', function() {
    $('.tab-btn').removeClass('active');
    $(this).addClass('active');
    currentFilters.solved = $(this).data('tab');
    loadMistakes();
  });

  // Action buttons
  $('#btn-hint').on('click', showHint);
  $('#btn-solution').on('click', showSolution);
  $('#btn-retry').on('click', resetPosition);
  $('#btn-spar').on('click', function() {
    enableSparringMode(false);
  });

  $('#btn-next').on('click', function() {
    if (!currentMistake || allMistakes.length === 0) return;
    const idx = allMistakes.findIndex(m => m.id === currentMistake.id);
    if (idx !== -1 && idx + 1 < allMistakes.length) {
      selectMistake(allMistakes[idx + 1]);
    } else {
      showStatus('prompt', 'You reached the end of this batch! Choose another lesson from the sidebar.');
    }
  });

  $('#btn-flip').on('click', function() {
    board.flip();
  });

  // Username input listener
  $('#username-input').on('change blur', function() {
    const val = $(this).val().trim();
    if (val) localStorage.setItem('chess_username', val);
  });

  // Sync button
  $('#btn-sync').on('click', triggerSync);
}

async function triggerSync() {
  const username = ($('#username-input').val() || '').trim();
  if (!username) {
    showStatus('error', '⚠️ Please enter your Chess.com username in the top bar before syncing.');
    $('#username-input').focus();
    return;
  }
  localStorage.setItem('chess_username', username);

  const btn = $('#btn-sync');
  btn.addClass('loading').text('⏳ Fetching & Analyzing...');
  showStatus('prompt', `Connecting to Chess.com API for ${username} & analyzing recent games with Stockfish...`);

  try {
    const res = await fetch(`/api/sync?username=${encodeURIComponent(username)}&games_count=30`, { method: 'POST' });
    const data = await res.json();
    if (res.ok) {
      pollSyncStatus();
    } else {
      btn.removeClass('loading').html('🔄 Sync Chess.com Games');
      showStatus('error', data.error || 'Sync request failed.');
    }
  } catch (err) {
    btn.removeClass('loading').html('🔄 Sync Chess.com Games');
    showStatus('error', 'Sync failed. Please check network connection.');
  }
}

function pollSyncStatus() {
  const interval = setInterval(async () => {
    try {
      const res = await fetch('/api/sync/status');
      const data = await res.json();
      showStatus('prompt', data.last_message || 'Analyzing games with Stockfish...');

      if (!data.is_syncing) {
        clearInterval(interval);
        $('#btn-sync').removeClass('loading').html('🔄 Sync Chess.com Games');
        showStatus('success', 'Sync complete! Fresh mistake lessons are ready.');
        loadStats();
        loadMistakes();
      }
    } catch (e) {
      clearInterval(interval);
      $('#btn-sync').removeClass('loading').html('🔄 Sync Chess.com Games');
    }
  }, 2000);
}
