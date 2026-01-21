/**
 * AniVerse Frontend Application v2.0
 * AI-powered anime discovery with auth, lists, and ratings
 */

// Auto-detect API base: use relative path in production (Docker), localhost in dev
const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
    ? 'http://127.0.0.1:8000'
    : '';

// Auth State
let currentUser = null;
let authToken = localStorage.getItem('aniverse_token');

// DOM Elements
const searchInput = document.getElementById('searchInput');
const searchBtn = document.getElementById('searchBtn');
const animeGrid = document.getElementById('animeGrid');
const loadingState = document.getElementById('loadingState');
const emptyState = document.getElementById('emptyState');
const resultsTitle = document.getElementById('resultsTitle');
const resultsCount = document.getElementById('resultsCount');
const resultsSection = document.getElementById('resultsSection');

// Modal elements
const animeModal = document.getElementById('animeModal');
const modalBackdrop = document.getElementById('modalBackdrop');
const modalClose = document.getElementById('modalClose');
const modalBody = document.getElementById('modalBody');

// Chat elements
const chatPanel = document.getElementById('chatPanel');
const chatToggle = document.getElementById('chatToggle');
const chatHeader = document.querySelector('.chat-header');
const chatMessages = document.getElementById('chatMessages');
const chatInput = document.getElementById('chatInput');
const chatSend = document.getElementById('chatSend');

// Theme toggle
const themeToggle = document.getElementById('themeToggle');

// State
let chatHistory = [];
let isSearching = false;
let userAnimeList = {};
let userMangaList = {};
let currentMode = 'anime'; // 'anime' or 'manga'

// ============================================
// Auth Functions
// ============================================

function getAuthHeaders() {
    return authToken ? { 'Authorization': `Bearer ${authToken}` } : {};
}

async function register(email, username, password) {
    const response = await fetch(`${API_BASE}/api/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, username, password })
    });
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Registration failed');
    }
    return response.json();
}

async function login(email, password) {
    const response = await fetch(`${API_BASE}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
    });
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Login failed');
    }
    return response.json();
}

async function fetchCurrentUser() {
    if (!authToken) return null;
    try {
        const response = await fetch(`${API_BASE}/api/auth/me`, {
            headers: getAuthHeaders()
        });
        if (response.ok) {
            return response.json();
        }
    } catch (e) { }
    return null;
}

function setAuth(token, user) {
    authToken = token;
    currentUser = user;
    localStorage.setItem('aniverse_token', token);
    updateAuthUI();
}

function logout() {
    authToken = null;
    currentUser = null;
    userAnimeList = {};
    localStorage.removeItem('aniverse_token');
    updateAuthUI();
}

function updateAuthUI() {
    const navActions = document.querySelector('.nav-actions');
    const existingAuthBtn = document.getElementById('authBtn');
    if (existingAuthBtn) existingAuthBtn.remove();

    if (currentUser) {
        navActions.insertAdjacentHTML('afterbegin', `
            <div id="authBtn" class="user-dropdown">
                <span class="user-avatar">👤</span>
                <span class="user-name">${currentUser.username}</span>
                <div class="dropdown-menu">
                    <a href="#" onclick="showMyList('all'); return false;">📋 My List</a>
                    <a href="#" onclick="showRecommendations(); return false;">✨ For You</a>
                    <a href="#" onclick="showImportModal(); return false;">🔄 Import from MAL</a>
                    <a href="#" onclick="logout(); return false;">🚪 Logout</a>
                </div>
            </div>
        `);
    } else {
        navActions.insertAdjacentHTML('afterbegin', `
            <button id="authBtn" class="btn-auth" onclick="showAuthModal()">
                Login / Sign Up
            </button>
        `);
    }
}

function showAuthModal() {
    const modal = document.createElement('div');
    modal.className = 'auth-modal';
    modal.innerHTML = `
        <div class="auth-backdrop" onclick="this.parentElement.remove()"></div>
        <div class="auth-content">
            <button class="modal-close" onclick="this.parentElement.parentElement.remove()">✕</button>
            <div class="auth-tabs">
                <button class="auth-tab active" data-tab="login">Login</button>
                <button class="auth-tab" data-tab="register">Sign Up</button>
            </div>
            <form id="authForm" class="auth-form">
                <div id="registerFields" style="display: none;">
                    <input type="text" name="username" placeholder="Username" minlength="3">
                </div>
                <input type="email" name="email" placeholder="Email" required>
                <input type="password" name="password" placeholder="Password" required minlength="6">
                <button type="submit" class="btn-submit">Login</button>
                <p class="auth-error" id="authError"></p>
            </form>
        </div>
    `;
    document.body.appendChild(modal);

    // Tab switching
    modal.querySelectorAll('.auth-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            modal.querySelectorAll('.auth-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            const isRegister = tab.dataset.tab === 'register';
            document.getElementById('registerFields').style.display = isRegister ? 'block' : 'none';
            modal.querySelector('.btn-submit').textContent = isRegister ? 'Sign Up' : 'Login';
        });
    });

    // Form submission
    document.getElementById('authForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        const formData = new FormData(e.target);
        const isRegister = modal.querySelector('.auth-tab.active').dataset.tab === 'register';
        const errorEl = document.getElementById('authError');

        try {
            let result;
            if (isRegister) {
                result = await register(formData.get('email'), formData.get('username'), formData.get('password'));
            } else {
                result = await login(formData.get('email'), formData.get('password'));
            }
            setAuth(result.access_token, result.user);
            modal.remove();
            loadUserAnimeList();
        } catch (err) {
            errorEl.textContent = err.message;
        }
    });
}

// ============================================
// List Functions
// ============================================

async function loadUserAnimeList() {
    if (!authToken) return;
    try {
        const response = await fetch(`${API_BASE}/api/lists/all`, {
            headers: getAuthHeaders()
        });
        if (response.ok) {
            const data = await response.json();
            userAnimeList = {};
            data.items.forEach(item => {
                userAnimeList[item.anime_id] = item;
            });
        }
    } catch (e) { console.error('Failed to load user list:', e); }
}

async function loadUserMangaList() {
    if (!authToken) return;
    try {
        const response = await fetch(`${API_BASE}/api/lists/manga/all`, {
            headers: getAuthHeaders()
        });
        if (response.ok) {
            const data = await response.json();
            userMangaList = {};
            data.items.forEach(item => {
                userMangaList[item.manga_id] = item;
            });
        }
    } catch (e) { console.error('Failed to load user manga list:', e); }
}

async function addToList(animeId, status, rating = null) {
    if (!authToken) {
        showAuthModal();
        return;
    }
    try {
        await fetch(`${API_BASE}/api/lists/add`, {
            method: 'POST',
            headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
            body: JSON.stringify({ anime_id: animeId, status, rating })
        });
        await loadUserAnimeList();
        updateModalListButtons(animeId);
        showToast(`Added to ${status}`, 'success');
    } catch (e) {
        console.error('Failed to add to list:', e);
        showToast('Failed to add', 'error');
    }
}

async function addMangaToList(mangaId, status, rating = null) {
    if (!authToken) {
        showAuthModal();
        return;
    }
    try {
        await fetch(`${API_BASE}/api/lists/manga/add`, {
            method: 'POST',
            headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
            body: JSON.stringify({ manga_id: mangaId, status, rating })
        });
        await loadUserMangaList();
        updateMangaModalListButtons(mangaId);
        showToast(`Added to ${status}`, 'success');
    } catch (e) {
        console.error('Failed to add manga to list:', e);
        showToast('Failed to add', 'error');
    }
}

async function rateAnime(animeId, rating) {
    if (!authToken) {
        showAuthModal();
        return;
    }
    try {
        await fetch(`${API_BASE}/api/lists/${animeId}`, {
            method: 'PATCH',
            headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
            body: JSON.stringify({ rating })
        });
        await loadUserAnimeList();
        updateModalListButtons(animeId);
        showToast(`Rated ${rating}/10`, 'success');
    } catch (e) {
        console.error('Failed to rate:', e);
        showToast('Failed to rate', 'error');
    }
}

async function rateManga(mangaId, rating) {
    if (!authToken) {
        showAuthModal();
        return;
    }
    try {
        await fetch(`${API_BASE}/api/lists/manga/${mangaId}`, {
            method: 'PATCH',
            headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
            body: JSON.stringify({ rating })
        });
        await loadUserMangaList();
        updateMangaModalListButtons(mangaId);
        showToast(`Rated ${rating}/10`, 'success');
    } catch (e) {
        console.error('Failed to rate manga:', e);
        showToast('Failed to rate', 'error');
    }
}

async function removeFromMangaList(mangaId) {
    if (!authToken) return;
    try {
        await fetch(`${API_BASE}/api/lists/manga/${mangaId}`, {
            method: 'DELETE',
            headers: getAuthHeaders()
        });
        await loadUserMangaList();
        updateMangaModalListButtons(mangaId);
        showToast('Removed from list', 'success');
    } catch (e) {
        console.error('Failed to remove from manga list:', e);
        showToast('Failed to remove', 'error');
    }
}

async function showMyList(status) {
    if (!authToken) return;

    loadingState.style.display = 'block';
    animeGrid.innerHTML = '';
    animeGrid.appendChild(loadingState);
    resultsTitle.textContent = status === 'all' ? 'My List' : `My ${status.charAt(0).toUpperCase() + status.slice(1)} List`;
    resultsSection.scrollIntoView({ behavior: 'smooth' });

    try {
        // Fetch both anime and manga lists
        const [animeResponse, mangaResponse] = await Promise.all([
            fetch(`${API_BASE}/api/lists/${status}`, { headers: getAuthHeaders() }),
            fetch(`${API_BASE}/api/lists/manga/${status}`, { headers: getAuthHeaders() })
        ]);

        const animeData = await animeResponse.json();
        const mangaData = await mangaResponse.json();

        // Fetch anime details for each item
        const animePromises = (animeData.items || []).map(item =>
            fetch(`${API_BASE}/api/anime/${item.anime_id}`).then(r => r.json()).catch(() => null)
        );
        const animeList = await Promise.all(animePromises);
        const validAnime = animeList.filter(a => a !== null).map((anime, i) => ({
            ...anime,
            user_rating: animeData.items[i].rating,
            user_status: animeData.items[i].status
        }));

        // Fetch manga details for each item
        const mangaPromises = (mangaData.items || []).map(item =>
            fetch(`${API_BASE}/api/manga/${item.manga_id}`).then(r => r.json()).catch(() => null)
        );
        const mangaList = await Promise.all(mangaPromises);
        const validManga = mangaList.filter(m => m !== null).map((manga, i) => ({
            ...manga,
            user_rating: mangaData.items[i].rating,
            user_status: mangaData.items[i].status
        }));

        // Clear grid and render both sections
        animeGrid.innerHTML = '';

        const totalCount = validAnime.length + validManga.length;
        resultsCount.textContent = `${totalCount} total`;

        // Anime section
        if (validAnime.length > 0) {
            const animeSection = document.createElement('div');
            animeSection.className = 'list-section';
            animeSection.innerHTML = `<h3 class="list-section-title">📺 Anime (${validAnime.length})</h3>`;
            animeGrid.appendChild(animeSection);

            const animeSubgrid = document.createElement('div');
            animeSubgrid.className = 'anime-grid section-grid';
            animeGrid.appendChild(animeSubgrid);

            validAnime.forEach(anime => {
                const card = createAnimeCard(anime, true);
                animeSubgrid.appendChild(card);
            });
        }

        // Manga section
        if (validManga.length > 0) {
            const mangaSection = document.createElement('div');
            mangaSection.className = 'list-section';
            mangaSection.innerHTML = `<h3 class="list-section-title">📚 Manga (${validManga.length})</h3>`;
            animeGrid.appendChild(mangaSection);

            const mangaSubgrid = document.createElement('div');
            mangaSubgrid.className = 'anime-grid section-grid';
            animeGrid.appendChild(mangaSubgrid);

            validManga.forEach(manga => {
                const card = createMangaCard(manga);
                mangaSubgrid.appendChild(card);
            });
        }

        // Empty state if no items
        if (totalCount === 0) {
            emptyState.querySelector('p').textContent = 'Your list is empty';
            emptyState.style.display = 'block';
        }

        loadingState.style.display = 'none';
    } catch (e) {
        console.error('Failed to load list:', e);
        loadingState.style.display = 'none';
        emptyState.querySelector('p').textContent = 'Failed to load your list';
        emptyState.style.display = 'block';
    }
}

// Helper function to create anime card
function createAnimeCard(anime, showUserRating = false) {
    const card = document.createElement('div');
    card.className = 'anime-card';
    card.onclick = () => openAnimeModal(anime.mal_id);

    const genres = anime.genres || '';
    const score = anime.score || 'N/A';
    const imageUrl = anime.image_url || 'https://via.placeholder.com/225x350?text=No+Image';

    card.innerHTML = `
        <div class="anime-card-image">
            <img src="${imageUrl}" alt="${anime.title}" loading="lazy" onerror="this.src='https://via.placeholder.com/225x350?text=No+Image'">
            <div class="anime-card-score">⭐ ${score}</div>
            ${anime.similarity ? `<div class="anime-card-similarity">${Math.round(anime.similarity * 100)}% match</div>` : ''}
            ${showUserRating && anime.user_rating ? `<div class="anime-card-user-rating">Your: ${anime.user_rating}/10</div>` : ''}
        </div>
        <div class="anime-card-info">
            <div class="anime-card-title">${anime.title}</div>
            <div class="anime-card-genres">${genres}</div>
        </div>
    `;
    return card;
}

// Helper function to create manga card
function createMangaCard(manga) {
    const card = document.createElement('div');
    card.className = 'anime-card';
    card.onclick = () => openMangaModal(manga.mal_id);

    const genres = manga.genres || '';
    const score = manga.score || 'N/A';
    const imageUrl = manga.image_url || 'https://via.placeholder.com/225x350?text=No+Image';

    card.innerHTML = `
        <div class="anime-card-image">
            <img src="${imageUrl}" alt="${manga.title}" loading="lazy" onerror="this.src='https://via.placeholder.com/225x350?text=No+Image'">
            <div class="anime-card-score">⭐ ${score}</div>
            ${manga.user_rating ? `<div class="anime-card-user-rating">Your: ${manga.user_rating}/10</div>` : ''}
        </div>
        <div class="anime-card-info">
            <div class="anime-card-title">${manga.title}</div>
            <div class="anime-card-genres">${genres}</div>
        </div>
    `;
    return card;
}

async function showRecommendations() {
    if (!authToken) return;

    loadingState.style.display = 'block';
    animeGrid.innerHTML = '';
    animeGrid.appendChild(loadingState);
    resultsTitle.textContent = '✨ Recommended For You';
    resultsSection.scrollIntoView({ behavior: 'smooth' });

    try {
        const response = await fetch(`${API_BASE}/api/recommendations?limit=20`, {
            headers: getAuthHeaders()
        });
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail);
        }
        const data = await response.json();

        resultsCount.textContent = `${data.recommendations.length} recommendations`;
        renderAnimeGrid(data.recommendations.map(r => ({
            mal_id: r.mal_id,
            title: r.title,
            score: r.score,
            genres: r.genres,
            image_url: r.image_url,
            similarity: r.similarity,
            reason: r.reason
        })), true);
    } catch (e) {
        emptyState.querySelector('p').textContent = e.message || 'Rate some anime first!';
        loadingState.style.display = 'none';
        emptyState.style.display = 'block';
    }
}

// ============================================
// API Functions
// ============================================

async function searchAnime(query) {
    const response = await fetch(`${API_BASE}/api/search?q=${encodeURIComponent(query)}&limit=20`);
    if (!response.ok) throw new Error('Search failed');
    return response.json();
}

async function getAnimeDetails(malId) {
    const response = await fetch(`${API_BASE}/api/anime/${malId}`);
    if (!response.ok) throw new Error('Failed to get anime details');
    return response.json();
}

async function getSimilarAnime(malId) {
    const response = await fetch(`${API_BASE}/api/search/similar/${malId}?limit=6`);
    if (!response.ok) throw new Error('Failed to get similar anime');
    return response.json();
}

async function chatWithAI(message) {
    const response = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            ...getAuthHeaders()
        },
        body: JSON.stringify({
            message,
            history: chatHistory.slice(-6),
            use_context: true
        })
    });
    if (!response.ok) throw new Error('Chat failed');
    return response.json();
}

async function getTopAnime() {
    const response = await fetch(`${API_BASE}/api/anime?limit=20&sort_by=score&order=desc&min_score=8`);
    if (!response.ok) throw new Error('Failed to get top anime');
    return response.json();
}

// ============================================
// Render Functions
// ============================================

function renderAnimeCard(anime, showSimilarity = true) {
    const similarity = anime.similarity ? Math.round(anime.similarity * 100) : null;
    const genres = typeof anime.genres === 'string' ? anime.genres : (anime.genres || []).join(', ');
    const userEntry = userAnimeList[anime.mal_id];

    return `
        <div class="anime-card" data-mal-id="${anime.mal_id}">
            <div class="anime-card-image">
                <img src="${anime.image_url || 'https://via.placeholder.com/200x280?text=No+Image'}" 
                     alt="${anime.title}" 
                     loading="lazy"
                     onerror="this.src='https://via.placeholder.com/200x280?text=No+Image'">
                ${anime.score ? `<div class="anime-card-score">⭐ ${anime.score.toFixed(1)}</div>` : ''}
                ${similarity && showSimilarity ? `<div class="anime-card-similarity">${similarity}% Match</div>` : ''}
                ${userEntry ? `<div class="anime-card-status status-${userEntry.status}">${userEntry.status}</div>` : ''}
                <div class="quick-actions">
                    <button class="quick-btn" onclick="event.stopPropagation(); addToList(${anime.mal_id}, 'planned')" title="Add to watchlist">+</button>
                </div>
            </div>
            <div class="anime-card-info">
                <div class="anime-card-title">${anime.title}</div>
                <div class="anime-card-genres">${genres}</div>
                ${anime.reason ? `<div class="anime-card-reason">${anime.reason}</div>` : ''}
            </div>
        </div>
    `;
}

function renderAnimeGrid(animes, showSimilarity = true) {
    hideSkeleton();

    if (!animes || animes.length === 0) {
        loadingState.style.display = 'none';
        emptyState.style.display = 'block';
        return;
    }

    loadingState.style.display = 'none';
    emptyState.style.display = 'none';

    animeGrid.innerHTML = animes.map(a => renderAnimeCard(a, showSimilarity)).join('');

    document.querySelectorAll('.anime-card').forEach(card => {
        card.addEventListener('click', () => openAnimeModal(card.dataset.malId));
    });
}

function updateModalListButtons(animeId) {
    const userEntry = userAnimeList[animeId];
    const buttonsContainer = document.getElementById('listButtons');
    if (!buttonsContainer) return;

    const statuses = ['watching', 'completed', 'planned', 'dropped'];
    buttonsContainer.innerHTML = statuses.map(s => `
        <button class="list-btn ${userEntry?.status === s ? 'active' : ''}" 
                onclick="addToList(${animeId}, '${s}')">
            ${s === 'watching' ? '👁️' : s === 'completed' ? '✅' : s === 'planned' ? '📋' : '❌'} 
            ${s.charAt(0).toUpperCase() + s.slice(1)}
        </button>
    `).join('');

    // Rating stars
    const ratingContainer = document.getElementById('ratingStars');
    if (ratingContainer) {
        const currentRating = userEntry?.rating || 0;
        ratingContainer.innerHTML = Array.from({ length: 10 }, (_, i) => `
            <span class="star ${i < currentRating ? 'filled' : ''}" 
                  onclick="rateAnime(${animeId}, ${i + 1})">★</span>
        `).join('');
    }
}

function updateMangaModalListButtons(mangaId) {
    const userEntry = userMangaList[mangaId];
    const buttonsContainer = document.getElementById('listButtons');
    if (!buttonsContainer) return;

    const statuses = ['watching', 'completed', 'planned', 'dropped'];
    buttonsContainer.innerHTML = statuses.map(s => `
        <button class="list-btn ${userEntry?.status === s ? 'active' : ''}" 
                onclick="addMangaToList(${mangaId}, '${s}')">
            ${s === 'watching' ? '📖 Reading' : s === 'completed' ? '✅ Done' : s === 'planned' ? '📋 Planned' : '❌ Dropped'}
        </button>
    `).join('');

    if (userEntry) {
        buttonsContainer.innerHTML += `
            <button class="list-btn remove-btn" onclick="removeFromMangaList(${mangaId})">
                🗑️ Remove
            </button>
        `;
    }

    // Rating stars
    const ratingContainer = document.getElementById('ratingStars');
    if (ratingContainer) {
        const currentRating = userEntry?.rating || 0;
        ratingContainer.innerHTML = Array.from({ length: 10 }, (_, i) => `
            <span class="star ${i < currentRating ? 'filled' : ''}" 
                  onclick="rateManga(${mangaId}, ${i + 1})">★</span>
        `).join('');
    }
}

function renderModal(anime, similar) {
    const genres = Array.isArray(anime.genres) ? anime.genres : [];
    const studios = Array.isArray(anime.studios) ? anime.studios : [];
    const userEntry = userAnimeList[anime.mal_id];

    modalBody.innerHTML = `
        <div class="modal-hero">
            <div class="modal-image">
                <img src="${anime.image_url || 'https://via.placeholder.com/200x280'}" alt="${anime.title}">
            </div>
            <div class="modal-details">
                <h2 class="modal-title">${anime.title}</h2>
                ${anime.title_english && anime.title_english !== anime.title ?
            `<p style="color: var(--text-muted); margin-bottom: 1rem;">${anime.title_english}</p>` : ''}
                <div class="modal-meta">
                    ${anime.score ? `<span class="modal-badge modal-score">⭐ ${anime.score.toFixed(2)}</span>` : ''}
                    <span class="modal-badge">${anime.media_type?.toUpperCase() || 'ANIME'}</span>
                    ${anime.episodes ? `<span class="modal-badge">${anime.episodes} eps</span>` : ''}
                    <span class="modal-badge">${anime.status?.replace(/_/g, ' ') || 'Unknown'}</span>
                </div>
                <div class="modal-meta" style="margin-bottom: 1rem;">
                    ${genres.map(g => `<span class="modal-badge">${g}</span>`).join('')}
                </div>
                ${studios.length ? `<p style="color: var(--text-muted); font-size: 0.9rem;">Studio: ${studios.join(', ')}</p>` : ''}
                
                ${currentUser ? `
                    <div class="list-actions">
                        <div id="listButtons" class="list-buttons"></div>
                        <div class="rating-section">
                            <span>Your Rating:</span>
                            <div id="ratingStars" class="rating-stars"></div>
                        </div>
                    </div>
                ` : `
                    <button class="btn-auth-cta" onclick="showAuthModal()">
                        Login to add to your list
                    </button>
                `}
            </div>
        </div>
        
        <div class="modal-section">
            <h3 class="modal-section-title">Synopsis</h3>
            <p class="modal-synopsis">${anime.synopsis || 'No synopsis available.'}</p>
        </div>
        
        ${similar && similar.length > 0 ? `
            <div class="modal-section">
                <h3 class="modal-section-title">Similar Anime</h3>
                <div class="anime-grid" style="grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 1rem;">
                    ${similar.map(s => `
                        <div class="anime-card" data-mal-id="${s.mal_id}" style="cursor: pointer;">
                            <div class="anime-card-image" style="aspect-ratio: 3/4;">
                                <img src="${s.image_url || 'https://via.placeholder.com/120x160'}" 
                                     alt="${s.title}" 
                                     style="width: 100%; height: 100%; object-fit: cover;">
                                <div class="anime-card-similarity">${Math.round((s.similarity || 0) * 100)}%</div>
                            </div>
                            <div class="anime-card-info" style="padding: 0.5rem;">
                                <div class="anime-card-title" style="font-size: 0.8rem;">${s.title}</div>
                            </div>
                        </div>
                    `).join('')}
                </div>
            </div>
        ` : ''}
    `;

    // Update list buttons
    if (currentUser) {
        updateModalListButtons(anime.mal_id);
    }

    // Add click handlers for similar anime
    modalBody.querySelectorAll('.anime-card').forEach(card => {
        card.addEventListener('click', (e) => {
            e.stopPropagation();
            openAnimeModal(card.dataset.malId);
        });
    });
}

function formatMarkdown(text) {
    // Simple markdown formatting
    return text
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.+?)\*/g, '<em>$1</em>')
        .replace(/`(.+?)`/g, '<code>$1</code>')
        .replace(/\n\n/g, '</p><p>')
        .replace(/\n/g, '<br>')
        .replace(/^- (.+)/gm, '• $1');
}

function addChatMessage(content, role, isAction = false) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `chat-message ${role}${isAction ? ' action' : ''}`;
    const formatted = role === 'assistant' ? formatMarkdown(content) : content;
    messageDiv.innerHTML = `<p>${formatted}</p>`;
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// ============================================
// Event Handlers
// ============================================

async function handleSearch() {
    const query = searchInput.value.trim();
    if (!query || isSearching) return;

    isSearching = true;
    loadingState.style.display = 'block';
    emptyState.style.display = 'none';
    animeGrid.innerHTML = '';
    animeGrid.appendChild(loadingState);

    resultsTitle.textContent = `Results for "${query}"`;
    resultsCount.textContent = '';

    resultsSection.scrollIntoView({ behavior: 'smooth' });

    try {
        // Search based on current mode
        if (currentMode === 'manga') {
            const data = await searchManga(query);
            resultsCount.textContent = `${data.count} found`;
            renderMangaGrid(data.results);
        } else {
            const data = await searchAnime(query);
            resultsCount.textContent = `${data.count} found`;
            renderAnimeGrid(data.results);
        }
    } catch (error) {
        console.error('Search error:', error);
        emptyState.querySelector('p').textContent = 'Search failed. Is the backend running?';
        loadingState.style.display = 'none';
        emptyState.style.display = 'block';
    } finally {
        isSearching = false;
    }
}

async function openAnimeModal(malId) {
    animeModal.classList.add('active');
    modalBody.innerHTML = '<div class="loading-state"><div class="loader"></div><p>Loading...</p></div>';

    try {
        const [anime, similarData] = await Promise.all([
            getAnimeDetails(malId),
            getSimilarAnime(malId).catch(() => ({ similar: [] }))
        ]);

        renderModal(anime, similarData.similar || []);
    } catch (error) {
        console.error('Error loading anime:', error);
        modalBody.innerHTML = '<p style="text-align: center; padding: 2rem;">Failed to load anime details.</p>';
    }
}

function closeModal() {
    animeModal.classList.remove('active');
}

function toggleChat() {
    chatPanel.classList.toggle('collapsed');
}

async function handleChatSend() {
    const message = chatInput.value.trim();
    if (!message) return;

    addChatMessage(message, 'user');
    chatHistory.push({ role: 'user', content: message });
    chatInput.value = '';

    const typingDiv = document.createElement('div');
    typingDiv.className = 'chat-message assistant';
    typingDiv.innerHTML = '<p>Thinking...</p>';
    chatMessages.appendChild(typingDiv);

    try {
        const response = await chatWithAI(message);
        typingDiv.remove();

        // Show actions taken (if any)
        if (response.actions_taken && response.actions_taken.length > 0) {
            for (const action of response.actions_taken) {
                const icon = action.success ? '✓' : '✗';
                addChatMessage(`${icon} ${action.message}`, 'assistant', true);
            }
            // Refresh user list if actions were taken
            await loadUserAnimeList();
        }

        // Show AI reply with formatting
        addChatMessage(response.reply, 'assistant');
        chatHistory.push({ role: 'assistant', content: response.reply });

        // Show context anime as clickable links
        if (response.context_anime && response.context_anime.length > 0 && !response.actions_taken?.length) {
            const contextHtml = response.context_anime.slice(0, 5).map(a =>
                `<span class="anime-link" onclick="openAnimeModal(${a.mal_id})">${a.title}</span>`
            ).join(', ');
            addChatMessage(`📺 ${contextHtml}`, 'assistant');
        }
    } catch (error) {
        typingDiv.remove();
        addChatMessage('Sorry, I couldn\'t process that. Make sure you have a GROQ_API_KEY set.', 'assistant');
    }
}

function toggleTheme() {
    const html = document.documentElement;
    const currentTheme = html.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', newTheme);
    themeToggle.querySelector('.theme-icon').textContent = newTheme === 'dark' ? '🌙' : '☀️';
}

// ============================================
// Initialize
// ============================================

async function init() {
    // Check auth state
    if (authToken) {
        currentUser = await fetchCurrentUser();
        if (currentUser) {
            await Promise.all([
                loadUserAnimeList(),
                loadUserMangaList()
            ]);
        } else {
            logout();
        }
    }
    updateAuthUI();

    // Search handlers
    searchBtn.addEventListener('click', handleSearch);
    searchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') handleSearch();
    });

    // Example chip handlers
    document.querySelectorAll('.example-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            searchInput.value = chip.dataset.query;
            handleSearch();
        });
    });

    // Modal handlers
    modalBackdrop.addEventListener('click', closeModal);
    modalClose.addEventListener('click', closeModal);
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeModal();
            document.getElementById('shortcutsModal')?.classList.remove('active');
        }
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        // Ignore when typing in inputs
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

        switch (e.key) {
            case '/':
                e.preventDefault();
                searchInput.focus();
                break;
            case 't':
            case 'T':
                toggleTheme();
                break;
            case '?':
                document.getElementById('shortcutsModal')?.classList.toggle('active');
                break;
        }
    });

    // Chat handlers
    chatHeader.addEventListener('click', toggleChat);
    chatSend.addEventListener('click', handleChatSend);
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') handleChatSend();
    });

    // Theme toggle
    themeToggle.addEventListener('click', toggleTheme);

    // Load initial data
    loadInitialData();
}

// Toast notification system
function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const icons = { success: '✓', error: '✗', info: 'ℹ' };
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <span class="toast-icon">${icons[type]}</span>
        <span class="toast-message">${message}</span>
    `;

    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(20px)';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Hide skeleton and show content
function hideSkeleton() {
    const skeleton = document.getElementById('skeletonGrid');
    if (skeleton) skeleton.style.display = 'none';
}

async function loadInitialData() {
    try {
        const data = await getTopAnime();
        hideSkeleton();
        resultsTitle.textContent = 'Top Rated';
        resultsCount.textContent = `${data.results.length} anime`;
        renderAnimeGrid(data.results, false);
    } catch (error) {
        console.error('Failed to load initial data:', error);
        hideSkeleton();
        loadingState.style.display = 'none';
        emptyState.style.display = 'block';
        emptyState.querySelector('p').textContent = 'Could not connect to API. Make sure the backend is running.';
    }
}

// Global functions for onclick handlers
window.openAnimeModal = openAnimeModal;
window.showAuthModal = showAuthModal;
window.logout = logout;
window.showMyList = showMyList;
window.showRecommendations = showRecommendations;
window.addToList = addToList;
window.rateAnime = rateAnime;
window.loadInitialData = loadInitialData;
window.showToast = showToast;

// ============================================
// Navigation Functions
// ============================================

function updateNavActive(view) {
    document.querySelectorAll('.nav-link').forEach(link => {
        link.classList.toggle('active', link.dataset.view === view);
    });
}

async function loadTopRated() {
    updateNavActive('top-rated');
    loadingState.style.display = 'block';
    animeGrid.innerHTML = '';
    animeGrid.appendChild(loadingState);

    const isManga = currentMode === 'manga';
    resultsTitle.textContent = isManga ? 'Top Rated Manga' : 'Top Rated Anime';
    resultsSection.scrollIntoView({ behavior: 'smooth' });

    try {
        const endpoint = isManga ? '/api/manga' : '/api/anime';
        const response = await fetch(`${API_BASE}${endpoint}?limit=30&sort_by=score&order=desc`);
        const data = await response.json();
        resultsCount.textContent = `${data.results.length} ${isManga ? 'manga' : 'anime'}`;
        if (isManga) {
            renderMangaGrid(data.results);
        } else {
            renderAnimeGrid(data.results, false);
        }
    } catch (e) {
        console.error('Failed to load top rated:', e);
    }
}

async function loadPopular() {
    updateNavActive('popular');
    loadingState.style.display = 'block';
    animeGrid.innerHTML = '';
    animeGrid.appendChild(loadingState);

    const isManga = currentMode === 'manga';
    resultsTitle.textContent = isManga ? 'Most Popular Manga' : 'Most Popular Anime';
    resultsSection.scrollIntoView({ behavior: 'smooth' });

    try {
        const endpoint = isManga ? '/api/manga' : '/api/anime';
        const sortField = isManga ? 'members' : 'scored_by';
        const response = await fetch(`${API_BASE}${endpoint}?limit=30&sort_by=${sortField}&order=desc`);
        const data = await response.json();
        resultsCount.textContent = `${data.results.length} ${isManga ? 'manga' : 'anime'}`;
        if (isManga) {
            renderMangaGrid(data.results);
        } else {
            renderAnimeGrid(data.results, false);
        }
    } catch (e) {
        console.error('Failed to load popular:', e);
    }
}

// ============================================
// Genre Filter Functions
// ============================================

const GENRES = ['Action', 'Adventure', 'Comedy', 'Drama', 'Fantasy', 'Horror', 'Mystery',
    'Psychological', 'Romance', 'Sci-Fi', 'Slice of Life', 'Sports', 'Supernatural', 'Thriller'];

function showGenreFilter() {
    const modal = document.getElementById('genreModal');
    const grid = document.getElementById('genreGrid');

    grid.innerHTML = GENRES.map(g => `
        <button class="genre-chip" onclick="filterByGenre('${g}')">${g}</button>
    `).join('');

    modal.classList.add('active');
}

function closeGenreModal() {
    document.getElementById('genreModal').classList.remove('active');
}

async function filterByGenre(genre) {
    closeGenreModal();
    updateNavActive('genres');
    loadingState.style.display = 'block';
    animeGrid.innerHTML = '';
    animeGrid.appendChild(loadingState);

    const isManga = currentMode === 'manga';
    resultsTitle.textContent = `${genre} ${isManga ? 'Manga' : 'Anime'}`;
    resultsSection.scrollIntoView({ behavior: 'smooth' });

    try {
        const endpoint = isManga ? '/api/manga' : '/api/anime';
        const response = await fetch(`${API_BASE}${endpoint}?limit=50&genre=${encodeURIComponent(genre)}&sort_by=score&order=desc`);
        const data = await response.json();
        resultsCount.textContent = `${data.results.length} found`;
        if (isManga) {
            renderMangaGrid(data.results);
        } else {
            renderAnimeGrid(data.results);
        }
    } catch (e) {
        console.error('Failed to filter by genre:', e);
    }
}

// ============================================
// View Toggle Functions
// ============================================

function initViewToggle() {
    document.querySelectorAll('.view-toggle').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.view-toggle').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            if (btn.dataset.view === 'list') {
                animeGrid.classList.add('list-view');
            } else {
                animeGrid.classList.remove('list-view');
            }
        });
    });
}

// ============================================
// MAL Import Functions
// ============================================

let selectedXmlFile = null;

function showImportModal() {
    if (!authToken) {
        showAuthModal();
        return;
    }
    document.getElementById('importModal').classList.add('active');
    initFileUpload();
}

function closeImportModal() {
    document.getElementById('importModal').classList.remove('active');
    document.getElementById('importProgress').style.display = 'none';
    document.querySelector('.import-options').style.display = 'flex';
}

async function startMALOAuth() {
    try {
        showToast('Connecting to MyAnimeList...', 'info');
        const response = await fetch(`${API_BASE}/api/import/mal/auth`, {
            headers: getAuthHeaders()
        });
        const data = await response.json();

        if (data.auth_url) {
            window.location.href = data.auth_url;
        }
    } catch (e) {
        showToast('Failed to connect to MAL', 'error');
        console.error('MAL OAuth error:', e);
    }
}

function initFileUpload() {
    const uploadZone = document.getElementById('uploadZone');
    const fileInput = document.getElementById('xmlFileInput');
    const fileName = document.getElementById('fileName');
    const uploadBtn = document.getElementById('uploadBtn');

    // Drag and drop
    uploadZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadZone.classList.add('dragover');
    });

    uploadZone.addEventListener('dragleave', () => {
        uploadZone.classList.remove('dragover');
    });

    uploadZone.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadZone.classList.remove('dragover');
        const file = e.dataTransfer.files[0];
        if (file && (file.name.endsWith('.xml') || file.name.endsWith('.gz'))) {
            selectedXmlFile = file;
            fileName.textContent = file.name;
            uploadBtn.disabled = false;
        }
    });

    // File input change
    fileInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            selectedXmlFile = file;
            fileName.textContent = file.name;
            uploadBtn.disabled = false;
        }
    });
}

async function uploadMALXml() {
    if (!selectedXmlFile) return;

    const importOptions = document.querySelector('.import-options');
    const importProgress = document.getElementById('importProgress');
    const importStatus = document.getElementById('importStatus');

    importOptions.style.display = 'none';
    importProgress.style.display = 'block';
    importStatus.textContent = 'Uploading and importing...';

    const formData = new FormData();
    formData.append('file', selectedXmlFile);

    try {
        const response = await fetch(`${API_BASE}/api/import/mal/xml`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: formData
        });

        const result = await response.json();

        if (result.success) {
            showToast(`Imported ${result.imported} anime, updated ${result.skipped}`, 'success');
            closeImportModal();
            await loadUserAnimeList();
        } else {
            showToast(result.message || 'Import failed', 'error');
            importOptions.style.display = 'flex';
            importProgress.style.display = 'none';
        }
    } catch (e) {
        showToast('Failed to import: ' + e.message, 'error');
        importOptions.style.display = 'flex';
        importProgress.style.display = 'none';
    }
}

// Check for import callback params in URL
function checkImportCallback() {
    const params = new URLSearchParams(window.location.search);

    if (params.get('import_success') === 'true') {
        const imported = params.get('imported') || '0';
        const updated = params.get('updated') || '0';
        showToast(`Successfully imported ${imported} anime, updated ${updated}!`, 'success');
        loadUserAnimeList();
        // Clean URL
        window.history.replaceState({}, '', window.location.pathname);
    } else if (params.get('import_error')) {
        showToast(`Import failed: ${params.get('import_error')}`, 'error');
        window.history.replaceState({}, '', window.location.pathname);
    }
}

// Register all new global functions
window.loadTopRated = loadTopRated;
window.loadPopular = loadPopular;
window.showGenreFilter = showGenreFilter;
window.closeGenreModal = closeGenreModal;
window.filterByGenre = filterByGenre;
window.showImportModal = showImportModal;
window.closeImportModal = closeImportModal;
window.startMALOAuth = startMALOAuth;
window.uploadMALXml = uploadMALXml;

// ============================================
// Manga Mode Functions
// ============================================

function switchMode(mode) {
    currentMode = mode;

    // Update toggle buttons
    document.querySelectorAll('.mode-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.mode === mode);
    });

    // Reload current view with new mode
    loadCurrentMode();
}

function loadCurrentMode() {
    updateNavActive('discover');
    if (currentMode === 'manga') {
        loadMangaDiscover();
    } else {
        loadInitialData();
    }
}

async function loadMangaDiscover() {
    loadingState.style.display = 'block';
    animeGrid.innerHTML = '';
    animeGrid.appendChild(loadingState);
    resultsTitle.textContent = '📚 Discover Manga';
    resultsSection.scrollIntoView({ behavior: 'smooth' });

    try {
        const response = await fetch(`${API_BASE}/api/manga?limit=30&sort_by=score&order=desc`);
        const data = await response.json();
        resultsCount.textContent = `${data.results.length} manga`;
        renderMangaGrid(data.results);
    } catch (e) {
        console.error('Failed to load manga:', e);
        emptyState.style.display = 'block';
    }
}

async function searchManga(query) {
    const response = await fetch(`${API_BASE}/api/manga/search?q=${encodeURIComponent(query)}&limit=30`);
    return await response.json();
}

function renderMangaGrid(mangaList) {
    animeGrid.innerHTML = '';

    if (!mangaList || mangaList.length === 0) {
        emptyState.style.display = 'block';
        loadingState.style.display = 'none';
        return;
    }

    mangaList.forEach(manga => {
        const card = document.createElement('div');
        card.className = 'anime-card';
        card.onclick = () => openMangaModal(manga.mal_id);

        const genres = manga.genres || '';
        const score = manga.score || 'N/A';
        const imageUrl = manga.image_url || 'https://via.placeholder.com/225x350?text=No+Image';

        card.innerHTML = `
            <div class="anime-card-image">
                <img src="${imageUrl}" alt="${manga.title}" loading="lazy" onerror="this.src='https://via.placeholder.com/225x350?text=No+Image'">
                <div class="anime-card-score">⭐ ${score}</div>
                ${manga.similarity ? `<div class="anime-card-similarity">${Math.round(manga.similarity * 100)}% match</div>` : ''}
            </div>
            <div class="anime-card-info">
                <div class="anime-card-title">${manga.title}</div>
                <div class="anime-card-genres">${genres}</div>
            </div>
        `;

        animeGrid.appendChild(card);
    });

    loadingState.style.display = 'none';
}

async function openMangaModal(malId) {
    modalBody.innerHTML = '<div class="loading-state"><div class="spinner"></div><p>Loading manga...</p></div>';
    animeModal.classList.add('active');

    try {
        const response = await fetch(`${API_BASE}/api/manga/${malId}`);
        const manga = await response.json();

        const genres = Array.isArray(manga.genres) ? manga.genres.join(', ') : manga.genres || '';
        const authors = Array.isArray(manga.authors) ? manga.authors.join(', ') : manga.authors || '';

        modalBody.innerHTML = `
            <div class="modal-grid">
                <div class="modal-image">
                    <img src="${manga.image_url || 'https://via.placeholder.com/300x450?text=No+Image'}" alt="${manga.title}">
                </div>
                <div class="modal-details">
                    <h2 class="modal-title">${manga.title}</h2>
                    <div class="modal-meta">
                        <span class="meta-badge type">${manga.media_type || 'Manga'}</span>
                        <span class="meta-badge score">⭐ ${manga.score || 'N/A'}</span>
                        ${manga.volumes ? `<span class="meta-badge">📖 ${manga.volumes} vols</span>` : ''}
                        ${manga.rank ? `<span class="meta-badge">🏆 #${manga.rank}</span>` : ''}
                    </div>
                    ${genres ? `<div class="modal-genres">${genres.split(', ').map(g => `<span class="genre-tag">${g}</span>`).join('')}</div>` : ''}
                    ${authors ? `<p class="modal-authors"><strong>Authors:</strong> ${authors}</p>` : ''}
                    ${manga.published ? `<p class="modal-published"><strong>Published:</strong> ${manga.published}</p>` : ''}
                    
                    ${currentUser ? `
                        <div class="list-actions">
                            <div id="listButtons" class="list-buttons"></div>
                            <div class="rating-section">
                                <span>Your Rating:</span>
                                <div id="ratingStars" class="rating-stars"></div>
                            </div>
                        </div>
                    ` : `
                        <button class="btn-auth-cta" onclick="showAuthModal()">
                            Login to add to your list
                        </button>
                    `}
                </div>
            </div>
            <div class="modal-section">
                <h3 class="modal-section-title">Synopsis</h3>
                <p class="modal-synopsis">${manga.synopsis || 'No synopsis available.'}</p>
            </div>
        `;

        if (currentUser) {
            updateMangaModalListButtons(malId);
        }
    } catch (e) {
        console.error('Failed to load manga details:', e);
        modalBody.innerHTML = '<p>Failed to load manga details</p>';
    }
}

// Register manga functions
window.switchMode = switchMode;
window.loadCurrentMode = loadCurrentMode;
window.loadMangaDiscover = loadMangaDiscover;
window.openMangaModal = openMangaModal;
window.addMangaToList = addMangaToList;
window.rateManga = rateManga;
window.removeFromMangaList = removeFromMangaList;

// Start the app
init();
initViewToggle();
checkImportCallback();

