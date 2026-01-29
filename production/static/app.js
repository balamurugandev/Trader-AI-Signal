/**
 * NIFTY 50 Scalping Dashboard - Frontend JavaScript
 * Real-time WebSocket client for super fast updates
 */

// DOM Elements
const marketStatus = document.getElementById('market-status');
const statusBadge = document.getElementById('status-badge');
const tickCount = document.getElementById('tick-count');
const candleCount = document.getElementById('candle-count');
const currentPrice = document.getElementById('current-price');
const tickTableBody = document.getElementById('tick-table-body');
const rsiValue = document.getElementById('rsi-value');
const rsiStatus = document.getElementById('rsi-status');
const rsiBar = document.getElementById('rsi-bar');
const emaValue = document.getElementById('ema-value');
const emaStatus = document.getElementById('ema-status');
const signalBox = document.getElementById('signal-box');
const signalIcon = document.getElementById('signal-icon');
const signalText = document.getElementById('signal-text');
const signalDesc = document.getElementById('signal-desc');
const lastUpdate = document.getElementById('last-update');

// Cached Scalping Elements
let scalpingStatus, futurePrice, cePrice, pePrice, basisValue, biasFill, straddleValue;
window.lastSignalState = null; // Track last signal for history log
let scalpingSignalBox, scalpSignalIcon, scalpSignalText, scalpSignalDesc;
let ceStrike, peStrike, tradeSuggestion, latencyDot, latencyText, momentumBar, velocityValue, newsTicker;
let pcrBadgeSignal, pcrValueSignal, pcrBadge, pcrValueEl;

document.addEventListener('DOMContentLoaded', () => {
    // Initialize Cache
    scalpingStatus = document.getElementById('scalping-status');
    futurePrice = document.getElementById('future-price');
    cePrice = document.getElementById('ce-price');
    pePrice = document.getElementById('pe-price');
    basisValue = document.getElementById('basis-value');
    biasFill = document.getElementById('bias-fill');
    straddleValue = document.getElementById('straddle-value');
    scalpingSignalBox = document.getElementById('scalping-signal-box');
    scalpSignalIcon = document.getElementById('scalp-signal-icon');
    scalpSignalText = document.getElementById('scalp-signal-text');
    scalpSignalDesc = document.getElementById('scalp-signal-desc');
    ceStrike = document.getElementById('ce-strike');
    peStrike = document.getElementById('pe-strike');
    tradeSuggestion = document.getElementById('trade-suggestion');
    latencyDot = document.getElementById('latency-dot');
    latencyText = document.getElementById('latency-text');
    momentumBar = document.getElementById('momentum-bar');
    momentumBar = document.getElementById('momentum-bar');
    velocityValue = document.getElementById('velocity-value');
    newsTicker = document.getElementById('news-ticker');
    pcrBadgeSignal = document.getElementById('pcr-badge-signal');
    pcrValueSignal = document.getElementById('pcr-value-signal');
    pcrBadge = document.getElementById('pcr-badge');
    pcrValueEl = document.getElementById('pcr-value');

    // Connect WS
    connectWebSocket();
});

// WebSocket connection (rest of file uses these let variables)
let ws = null;
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 10;

function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        console.log('🔌 WebSocket connected');
        reconnectAttempts = 0;
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        updateDashboard(data);
    };

    ws.onclose = () => {
        console.log('📴 WebSocket disconnected');
        attemptReconnect();
    };

    ws.onerror = (error) => {
        console.error('❌ WebSocket error:', error);
    };
}

function attemptReconnect() {
    if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
        reconnectAttempts++;
        const delay = Math.min(1000 * reconnectAttempts, 5000);
        console.log(`🔄 Reconnecting in ${delay}ms (attempt ${reconnectAttempts})`);
        setTimeout(connectWebSocket, delay);
    }
}

function updateDashboard(data) {
    // Update market status
    updateStatus(data.market_status);

    // DEBUG: Trace PCR Data Flow
    if (data.pcr !== undefined) {
        console.log(`📡 PCR Update: Val=${data.pcr}, Age=${data.pcr_age}s`);
    }

    // Update stats
    tickCount.textContent = data.total_ticks.toLocaleString();
    candleCount.textContent = `${data.candles_count}/200`;

    // Update price
    if (data.last_price !== null && currentPrice) {
        currentPrice.textContent = formatPrice(data.last_price);
    }

    // Update Tick History
    if (typeof updateTickTable === 'function') {
        updateTickTable(data.tick_history);
    }

    // Update Ticker Tape (New)
    if (data.tickers && typeof updateTickerTape === 'function') {
        updateTickerTape(data.tickers);
    }

    // Update indicators
    updateIndicators(data.rsi, data.ema, data.last_price);

    // Update signal
    updateSignal(data.signal, data.candles_count);

    // Update News Ticker
    // Update News Ticker (List View)
    if (data.news && newsTicker) {
        // Only update if content changed significantly
        if (newsTicker.getAttribute('data-last-news') !== data.news) {
            newsTicker.setAttribute('data-last-news', data.news);

            // Split string by separator '✦' and filter empty strings
            const headlines = data.news.split('✦').map(h => h.trim()).filter(h => h.length > 0);

            // Render as List
            if (headlines.length > 0) {
                // Clear existing
                newsTicker.innerHTML = '';
                const ul = document.createElement('div');
                ul.className = 'news-grid'; // Use grid/flex for layout

                headlines.forEach(head => {
                    const item = document.createElement('div');
                    item.className = 'news-item';

                    // Parse "Headline###Source"
                    let title = head;
                    let source = "";
                    if (head.includes('###')) {
                        const parts = head.split('###');
                        title = parts[0];
                        source = parts[1];
                    } else if (head.includes('|')) {
                        // Fallback for any cached old data
                        const parts = head.split('|');
                        title = parts[0];
                        source = parts[1] || "";
                    }

                    // Clean symbols
                    const cleanHead = title.replace(/[►▼▲]/g, '').trim();

                    // Render with Source Badge
                    item.innerHTML = `
                        <span class="news-bullet">➤</span> 
                        <span class="news-text">${cleanHead}</span>
                        ${source ? `<span class="news-source">(${source})</span>` : ''}
                    `;
                    ul.appendChild(item);
                });
                newsTicker.appendChild(ul);

                // ⚡ Flash effect for dynamic update
                const container = document.querySelector('.news-container');
                if (container) {
                    container.style.transition = 'border-color 0.3s';
                    const originalBorder = container.style.borderColor;
                    container.style.borderColor = 'var(--text-primary)'; // Flash white border
                    setTimeout(() => {
                        container.style.borderColor = ''; // Revert to CSS default
                    }, 500);
                }

            } else {
                newsTicker.innerHTML = '<div class="news-fetching">Waiting for updates...</div>';
            }
        }
    }

    // Update timestamp
    if (lastUpdate) {
        lastUpdate.textContent = `Last Update: ${new Date().toLocaleTimeString()}`;
    }
}

function updateTickerTape(tickers) {
    const tickerContainer = document.querySelector('.ticker-tape');
    if (!tickerContainer) return;

    // Helper to create HTML for a ticker item
    const createTickerItem = (name, data) => {
        // const changeClass = data.change >= 0 ? 'positive' : 'negative';
        // const arrow = data.change >= 0 ? '▲' : '▼';
        return `
            <div class="ticker-item">
                <span class="ticker-name">${name}</span>
                <span class="ticker-value">${data.price.toFixed(2)}</span>
            </div>
        `;
    };

    // Re-render logic (optimized to avoid full redraw if possible, but innerHTML is fast enough for 5 items)
    // To prevent scrolling reset, we should update values if elements exist, but for now simple innerHTML is robust.

    // Check if we need to build structure or just update
    // For smoothness, let's try to update in place if ids exist, otherwise rebuild for now.
    // Actually, simple rebuild is fine for 100ms updates if the list is small.
    // BUT resetting innerHTML might kill scroll position. Let's update intelligently.

    // indices mapping
    const indices = ['nifty', 'sensex', 'banknifty', 'midcpnifty', 'indiavix'];
    const displayNames = {
        'nifty': 'NIFTY 50', 'sensex': 'SENSEX', 'banknifty': 'BANKNIFTY',
        'midcpnifty': 'MIDCPNIFTY', 'indiavix': 'INDIA VIX'
    };

    // Check if structure exists, if not create it (FIRST RUN)
    if (tickerContainer.children.length === 0 || tickerContainer.getAttribute('data-init') !== 'true') {
        tickerContainer.innerHTML = indices.map(key => {
            const data = tickers[key];
            if (!data) return '';
            return createTickerItem(displayNames[key], data);
        }).join('');
        tickerContainer.setAttribute('data-init', 'true');
    } else {
        // UPDATE IN PLACE to preserve scroll and selection
        // Cache children to avoid repeated Array.from() allocations
        if (!window.cachedTickerItems || window.cachedTickerItems.length !== tickerContainer.children.length) {
            window.cachedTickerItems = Array.from(tickerContainer.children);
        }
        const items = window.cachedTickerItems;

        indices.forEach((key, index) => {
            if (index >= items.length) return;
            const data = tickers[key];
            if (!data) return;

            const item = items[index];
            const valueEl = item.querySelector('.ticker-value');
            const changeEl = item.querySelector('.ticker-change');

            if (valueEl) valueEl.textContent = data.price.toFixed(2);
            // Change removed as per request
            if (changeEl) changeEl.style.display = 'none';
        });
    }
}

function updateStatus(status) {
    marketStatus.textContent = status;

    statusBadge.classList.remove('live', 'error');

    if (status === 'LIVE' || status === 'SUBSCRIBED') {
        statusBadge.classList.add('live');
    } else if (status.includes('ERROR') || status.includes('Error')) {
        statusBadge.classList.add('error');
    }
}

// CACHED FORMATTER (Optimization)
const currencyFormatter = new Intl.NumberFormat('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
});

function formatPrice(price) {
    if (price === undefined || price === null) return '--';
    return currencyFormatter.format(price);
}

function updateTickTable(ticks) {
    if (!ticks || ticks.length === 0 || !tickTableBody) return;

    tickTableBody.innerHTML = ticks.map(tick => {
        const changeClass = tick.change > 0 ? 'change-positive' :
            tick.change < 0 ? 'change-negative' : '';
        const changeSign = tick.change > 0 ? '+' : '';

        return `
            <tr>
                <td>${tick.time}</td>
                <td>₹${formatPrice(tick.price)}</td>
                <td class="${changeClass}">${changeSign}${tick.change.toFixed(2)}</td>
            </tr>
        `;
    }).join('');
}

function updateIndicators(rsi, ema, price) {
    // RSI
    if (rsi !== null && rsiValue) {
        rsiValue.textContent = rsi.toFixed(2);

        // Update RSI bar
        if (rsiBar) {
            rsiBar.style.width = `${rsi}%`;
            rsiBar.classList.remove('oversold', 'overbought');

            if (rsi < 30) {
                rsiBar.classList.add('oversold');
            } else if (rsi > 70) {
                rsiBar.classList.add('overbought');
            }
        }

        if (rsiStatus) {
            if (rsi < 30) {
                rsiStatus.textContent = '⬆️ OVERSOLD';
                rsiStatus.style.color = '#00ff88';
            } else if (rsi > 70) {
                rsiStatus.textContent = '⬇️ OVERBOUGHT';
                rsiStatus.style.color = '#ff4466';
            } else {
                rsiStatus.textContent = '↔️ NEUTRAL';
                rsiStatus.style.color = '#ffaa00';
            }
        }
    } else if (rsiValue) {
        rsiValue.textContent = '--';
        if (rsiStatus) {
            rsiStatus.textContent = 'Need more data...';
            rsiStatus.style.color = '#a0a0b0';
        }
    }

    // EMA
    if (ema !== null && emaValue) {
        emaValue.textContent = `₹${formatPrice(ema)}`;

        if (price !== null && emaStatus) {
            if (price > ema) {
                emaStatus.textContent = '⬆️ Price ABOVE EMA';
                emaStatus.style.color = '#00ff88';
            } else {
                emaStatus.textContent = '⬇️ Price BELOW EMA';
                emaStatus.style.color = '#ff4466';
            }
        }
    } else if (emaValue) {
        emaValue.textContent = '--';
        if (emaStatus) {
            emaStatus.textContent = 'Need more data...';
            emaStatus.style.color = '#a0a0b0';
        }
    }
}

function updateSignal(signal, candlesCount) {
    if (!signalBox || !signalIcon || !signalText || !signalDesc) return;

    signalBox.classList.remove('waiting', 'buy-call', 'buy-put');

    if (signal === 'BUY CALL') {
        signalBox.classList.add('buy-call');
        signalIcon.textContent = '🟢';
        signalText.textContent = 'BUY CALL';
        signalDesc.textContent = 'RSI Oversold + Price Above EMA → BULLISH REVERSAL';
    } else if (signal === 'BUY PUT') {
        signalBox.classList.add('buy-put');
        signalIcon.textContent = '🔴';
        signalText.textContent = 'BUY PUT';
        signalDesc.textContent = 'RSI Overbought + Price Below EMA → BEARISH REVERSAL';
    } else {
        signalBox.classList.add('waiting');
        signalIcon.textContent = '⏳';
        signalText.textContent = 'WAITING';

        if (candlesCount < 50) {
            signalDesc.textContent = `Collecting data... Need ${50 - candlesCount} more candles`;
        } else {
            signalDesc.textContent = 'Analyzing market conditions...';
        }
    }
}

// =============================================================================
// SCALPING MODULE - JavaScript (NEW)
// =============================================================================

// Scalping DOM Elements (Defined Globally above)

// Chart.js instance
let straddleChart = null;

// Custom Plugin: Pulsing Dot + Price Label (Canvas Draw)
const lastPointPlugin = {
    id: 'lastPointHighlight',
    afterDatasetsDraw(chart) {
        const dataset = chart.data.datasets[0];
        if (!dataset || dataset.data.length === 0) return;

        const lastIndex = dataset.data.length - 1;
        const meta = chart.getDatasetMeta(0);
        const lastPoint = meta.data[lastIndex];
        if (!lastPoint) return;

        const ctx = chart.ctx;
        const x = lastPoint.x;
        const y = lastPoint.y;
        const value = dataset.data[lastIndex];

        // 1. Draw Vertical Dashed Line
        ctx.save();
        ctx.beginPath();
        ctx.setLineDash([4, 4]);
        ctx.strokeStyle = 'rgba(255, 170, 0, 0.4)'; // Faint line
        ctx.lineWidth = 1;
        ctx.moveTo(x, y);
        ctx.lineTo(x, chart.chartArea.bottom);
        ctx.stroke();
        ctx.restore();

        // 2. Draw Pulsing Dot (Static Glow for Performance)
        ctx.save();
        // Outer Glow
        ctx.beginPath();
        ctx.arc(x, y, 10, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(255, 170, 0, 0.25)';
        ctx.fill();
        // Inner Glow
        ctx.beginPath();
        ctx.arc(x, y, 6, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(255, 170, 0, 0.5)';
        ctx.fill();
        // Solid Center
        ctx.beginPath();
        ctx.arc(x, y, 3, 0, Math.PI * 2);
        ctx.fillStyle = '#ffaa00';
        ctx.fill();
        ctx.restore();

        // 3. Draw Price Label (Canvas Text)
        if (value !== undefined && value !== null) {
            ctx.save();
            ctx.font = 'bold 11px Inter, sans-serif';
            ctx.textBaseline = 'middle';

            const text = `₹${value.toFixed(2)}`;
            const textWidth = ctx.measureText(text).width;
            const paddingX = 6;
            const paddingY = 4;
            const labelX = x + 15; // Offset to right
            const labelY = y;

            // Background Pill
            ctx.fillStyle = 'rgba(18, 18, 26, 0.95)';
            ctx.strokeStyle = '#ffaa00';
            ctx.lineWidth = 1;

            ctx.beginPath();
            if (ctx.roundRect) {
                ctx.roundRect(labelX - paddingX, labelY - 10, textWidth + paddingX * 2, 20, 4);
            } else {
                ctx.rect(labelX - paddingX, labelY - 10, textWidth + paddingX * 2, 20);
            }
            ctx.fill();
            ctx.stroke();

            // Text
            ctx.fillStyle = '#ffaa00';
            ctx.fillText(text, labelX, labelY);
            ctx.restore();
        }
    }
};

function initStraddleChart() {
    const ctx = document.getElementById('straddleChart');
    if (!ctx) return;

    // Safe Registration: Check if Chart is loaded
    if (typeof Chart !== 'undefined') {
        const registry = Chart.registry || Chart.defaults; // fallback
        // Avoid re-registering if already done (though Chart.js handles it usually)
        if (Chart.register) {
            Chart.register(lastPointPlugin);
        }
    } else {
        console.error("Chart.js library not loaded!");
        return;
    }

    straddleChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Straddle Price',
                data: [],
                borderColor: '#ffaa00',
                backgroundColor: 'rgba(255, 170, 0, 0.05)',
                borderWidth: 2,
                fill: true,
                tension: 0.4,
                pointRadius: 0,
                pointHoverRadius: 4
            }]
        },
        options: {
            layout: {
                padding: {
                    right: 80, // Space for the floating label
                    top: 20,
                    bottom: 20
                }
            },
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 0 },
            interaction: {
                intersect: false,
                mode: 'index'
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(18, 18, 26, 0.95)',
                    titleColor: '#fff',
                    bodyColor: '#ffaa00',
                    borderColor: 'rgba(255, 255, 255, 0.1)',
                    borderWidth: 1
                }
            },
            scales: {
                x: {
                    display: true,
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#606070', maxTicksLimit: 12 }
                },
                y: {
                    display: true,
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#606070' }
                }
            }
        }
    });
}

async function updateScalper() {
    try {
        const response = await fetch('/api/scalper-data');
        if (!response.ok) return;
        const data = await response.json();
        updateScalperUI(data);
    } catch (error) {
        console.error('Scalper update error:', error);
    }
}

// OPTIMIZATION: RequestAnimationFrame Wrapper (60fps Limit)
let pendingScalperData = null;
let scalperRafId = null;

function updateScalperUI(data) {
    if (!data) return;
    pendingScalperData = data;
    if (!scalperRafId) {
        scalperRafId = requestAnimationFrame(renderScalperUI);
    }
}

function renderScalperUI() {
    const data = pendingScalperData;
    scalperRafId = null;
    if (!data) return;

    // Update status
    if (scalpingStatus) {
        scalpingStatus.textContent = data.status;
        scalpingStatus.classList.toggle('live', data.status === 'LIVE');
    }

    // Update prices
    if (futurePrice && data.future_price !== null) {
        futurePrice.textContent = `₹${formatPrice(data.future_price)}`;
    }
    if (cePrice && data.ce_price !== null) {
        cePrice.textContent = `₹${formatPrice(data.ce_price)}`;
    }
    if (pePrice && data.pe_price !== null) {
        pePrice.textContent = `₹${formatPrice(data.pe_price)}`;
    }

    // Update Real Basis (Synthetic) with gauge and sentiment
    const displayBasis = data.real_basis !== null ? data.real_basis : data.basis;
    if (basisValue && displayBasis !== null) {
        basisValue.textContent = (displayBasis >= 0 ? '+' : '') + displayBasis.toFixed(2);
        basisValue.classList.remove('positive', 'negative');
        basisValue.classList.add(displayBasis >= 0 ? 'positive' : 'negative');

        // Update bias fill gauge (-50 to +50 range mapped to 0-50% width)
        if (biasFill) {
            const normalizedBasis = Math.min(Math.max(displayBasis, -50), 50);
            const fillWidth = Math.abs(normalizedBasis) + '%';
            biasFill.style.width = fillWidth;
            biasFill.classList.remove('positive', 'negative');
            biasFill.classList.add(displayBasis >= 0 ? 'positive' : 'negative');
        }
    }

    // Update Straddle value with SMA indicator
    if (straddleValue && data.straddle_price !== null) {
        const smaIndicator = data.sma3 ? ` (SMA: ${data.sma3.toFixed(2)})` : '';
        straddleValue.textContent = `₹${formatPrice(data.straddle_price)}`;
    }

    // ================================================================
    // DYNAMIC SCALING & TREND-COLORED CHART
    // ================================================================
    if (straddleChart && data.history && data.history.length > 0) {
        // Fix: Filter history FIRST to ensure 1:1 mapping of Labels vs Data
        const validHistory = data.history.filter(h => h.straddle !== null && h.straddle > 0);

        // Slice last 40 points for "Ultra Fast" zoom
        const recentHistory = validHistory.slice(-40);

        straddleChart.data.labels = recentHistory.map(h => h.time);
        straddleChart.data.datasets[0].data = recentHistory.map(h => h.straddle);

        // DYNAMIC Y-AXIS SCALING (Heartbeat View)
        const displayValues = straddleChart.data.datasets[0].data;
        if (displayValues.length > 0) {
            const minVal = Math.min(...displayValues);
            const maxVal = Math.max(...displayValues);
            straddleChart.options.scales.y.suggestedMin = minVal - 2;
            straddleChart.options.scales.y.suggestedMax = maxVal + 2;
        }

        // TREND-BASED LINE COLOR
        const trend = data.trend || 'FLAT';
        let lineColor = '#ffaa00';
        let fillColor = 'rgba(255, 170, 0, 0.05)';

        if (trend === 'RISING') {
            lineColor = '#00E396';
            fillColor = 'rgba(0, 227, 150, 0.1)';
        } else if (trend === 'FALLING') {
            lineColor = '#FF4560';
            fillColor = 'rgba(255, 69, 96, 0.1)';
        }

        straddleChart.data.datasets[0].borderColor = lineColor;
        straddleChart.data.datasets[0].backgroundColor = fillColor;

        straddleChart.update('none');
    }

    // ================================================================
    // SCALPING SIGNAL BOX (Professional Edition)
    // ================================================================
    if (scalpingSignalBox) {
        scalpingSignalBox.classList.remove('wait', 'buy-call', 'buy-put');

        const sentiment = data.sentiment || 'NEUTRAL';
        const trend = data.trend || 'FLAT';

        if (data.signal === 'BUY CALL') {
            scalpingSignalBox.classList.add('buy-call');
            scalpSignalIcon.textContent = '🟢';
            scalpSignalText.textContent = 'BUY CALL';
            scalpSignalDesc.textContent = `${sentiment} + ${trend} Straddle → CALL Entry`;
        } else if (data.signal === 'BUY PUT') {
            scalpingSignalBox.classList.add('buy-put');
            scalpSignalIcon.textContent = '🔴';
            scalpSignalText.textContent = 'BUY PUT';
            scalpSignalDesc.textContent = `${sentiment} + ${trend} Straddle → PUT Entry`;
        } else if (data.signal === 'TRAP') {
            scalpingSignalBox.classList.add('trap');
            scalpSignalIcon.textContent = '⚠️';
            scalpSignalText.textContent = 'TRAP';
            scalpSignalDesc.textContent = `OI Trap Detected: ${sentiment} but High PCR Reversal Risk!`;
        } else {
            scalpingSignalBox.classList.add('wait');
            scalpSignalIcon.textContent = '⚪';
            scalpSignalText.textContent = 'WAIT';

            if (trend === 'FALLING') {
                scalpSignalDesc.textContent = '📉 Straddle Decay - Do Not Enter';
            } else {
                scalpSignalDesc.textContent = `${sentiment} | Waiting for trend...`;
            }
        }

        // ===================================
        // SIGNAL HISTORY LOG (Last 5)
        // ===================================
        // Only log if signal changed AND it's a trade signal (BUY/SELL/TRAP)
        // OR if it changed from a trade signal back to WAIT (to show exit/reset)
        if (data.signal !== window.lastSignalState) {
            // Log valuable state changes
            const meaningfulSignals = ['BUY CALL', 'BUY PUT', 'TRAP'];
            const wasMeaningful = meaningfulSignals.includes(window.lastSignalState);
            const isMeaningful = meaningfulSignals.includes(data.signal);

            // Log if it's a new Trade Signal OR a Trap
            if (isMeaningful) {
                console.log("HISTORY UPDATE:", data.signal);
                updateSignalHistory(data.signal, data);
            }

            window.lastSignalState = data.signal;
        }
    }

    // Update ATM Strike badges with full symbol names
    const ceStrikeEl = document.getElementById('ce-strike');
    const peStrikeEl = document.getElementById('pe-strike');

    // Helper to flash element on change
    const updateAndFlash = (element, newValue) => {
        if (!element || element.textContent === newValue) return;
        element.textContent = newValue;
        element.style.color = 'var(--accent-yellow)';
        element.style.transition = 'none';

        // Force reflow
        void element.offsetWidth;

        element.style.transition = 'color 1s ease';
        setTimeout(() => {
            element.style.color = 'var(--accent-yellow)'; // Keep it yellow or revert to default?
            // User wants it dynamic. Let's keep it yellow (like in screenshot) or revert.
            // Screenshot has it yellow.
        }, 50);
    };

    if (data.ce_symbol) {
        if (ceStrikeEl) updateAndFlash(ceStrikeEl, formatSymbol(data.ce_symbol));
    } else if (data.atm_strike && ceStrikeEl) {
        ceStrikeEl.textContent = `${data.atm_strike} CE`; // Fallback with CE
    }

    if (data.pe_symbol) {
        if (peStrikeEl) updateAndFlash(peStrikeEl, formatSymbol(data.pe_symbol));
    } else if (data.atm_strike && peStrikeEl) {
        peStrikeEl.textContent = `${data.atm_strike} PE`; // Fallback with PE
    }

    // Update Trade Suggestion
    if (data.suggestion && tradeSuggestion) {
        tradeSuggestion.textContent = data.suggestion;

        // Dynamic coloring
        tradeSuggestion.style.color = 'var(--text-primary)'; // Default
        if (data.suggestion.includes('BUY')) {
            if (data.suggestion.includes('CE')) tradeSuggestion.style.color = 'var(--accent-green)';
            if (data.suggestion.includes('PE')) tradeSuggestion.style.color = 'var(--accent-red)';
        }
    }

    // ===================================
    // Health Checks (V7)
    // ===================================

    // 1. Latency Monitor
    if (data.latency_ms !== undefined && latencyDot && latencyText) {
        latencyText.textContent = `${data.latency_ms}ms`;
        latencyDot.className = 'latency-dot'; // Reset class

        if (data.latency_ms < 500) {
            latencyDot.classList.add('latency-good');
            latencyText.style.color = 'var(--accent-green)';
        } else if (data.latency_ms < 1500) {
            latencyDot.classList.add('latency-warn');
            latencyText.style.color = 'var(--accent-yellow)';
        } else {
            latencyDot.classList.add('latency-bad');
            latencyText.style.color = 'var(--accent-red)';
        }
    }

    // 2. Velocity Momentum Bar (Enhanced)
    if (data.velocity !== undefined) {
        // Update Bar Width
        if (momentumBar) {
            // Cap at 10 pts/sec for 100% width
            const velocity = Math.abs(data.velocity);
            const width = Math.min((velocity / 10) * 100, 100);
            momentumBar.style.width = `${width}%`;
        }

        // Update Text Label
        if (velocityValue) {
            const vel = Math.abs(data.velocity).toFixed(2);
            velocityValue.textContent = `${vel} pts/s`;

            // Dynamic Color for Text
            velocityValue.style.color = (Math.abs(data.velocity) > 3.0) ? 'var(--accent-green)' : 'var(--accent-yellow)';
        }
    }

    // 3. PCR Badge (Signal Box)
    // 3. PCR Badge (Signal Box)
    if (pcrBadgeSignal && pcrValueSignal) {
        pcrBadgeSignal.style.display = 'block'; // Always show

        let pcrVal = data.pcr;
        if (pcrVal === undefined || pcrVal === null) pcrVal = 1.0; // Default Neutral

        pcrValueSignal.textContent = pcrVal.toFixed(2);

        if (pcrVal > 1.0) {
            pcrValueSignal.style.color = 'var(--accent-green)';
        } else if (pcrVal < 0.7) {
            pcrValueSignal.style.color = 'var(--accent-red)';
        } else {
            pcrValueSignal.style.color = 'var(--text-muted)';
        }
    }

    // Update PCR Badge (New)
    if (data.pcr !== undefined && pcrBadgeSignal && pcrValueSignal) {
        pcrBadgeSignal.style.display = 'block';

        // Show PCR value with staleness indicator
        const pcrAge = data.pcr_age !== undefined ? data.pcr_age : -1;
        let ageText = '';
        let ageColor = '';

        if (pcrAge >= 0) {
            if (pcrAge < 15) {
                ageText = `(${pcrAge}s)`;
                ageColor = 'var(--accent-green)'; // Fresh
            } else if (pcrAge < 30) {
                ageText = `(${pcrAge}s)`;
                ageColor = 'var(--accent-yellow)'; // Moderate
            } else {
                ageText = `(${pcrAge}s ⚠️)`;
                ageColor = 'var(--accent-red)'; // Stale
            }
        }

        pcrValueSignal.innerHTML = `${data.pcr.toFixed(2)} <span style="font-size: 0.7em; color: ${ageColor};">${ageText}</span>`;

        pcrBadgeSignal.classList.remove('bullish', 'bearish');
        if (data.pcr > 1.0) {
            pcrBadgeSignal.classList.add('bullish');
        } else if (data.pcr < 0.7) {
            pcrBadgeSignal.classList.add('bearish');
        }
    }

}



// =============================================================================
// DATE/TIME UPDATER
// =============================================================================
function updateDateTime() {
    const now = new Date();

    // Format date: Sun, 25 Jan, 2026
    const dateOptions = { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' };
    // Force "Sun, 25 Jan, 2026" - some locales might differ, manually constructing to be safe if needed, 
    // but en-GB/IN usually does "Sun, 25 Jan 2026". 
    // Let's use en-GB which is consistently "Sun, 25 Jan 2026" or similar.
    // User asked for "Sun, 25 Jan, 2026".
    const datePart = now.toLocaleDateString('en-GB', { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' });
    // en-GB gives "Sun, 25 Jan 2026". Adding comma manually if needed or accepting it.
    // Let's try to match exactly. 
    // Manual construction for precision:
    const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const dayName = days[now.getDay()];
    const dayNum = String(now.getDate()).padStart(2, '0');
    const monthName = months[now.getMonth()];
    const year = now.getFullYear();
    const dateStr = `${dayName}, ${dayNum} ${monthName}, ${year}`;

    // Format time: 06:35:21 pm IST
    let hours = now.getHours();
    const minutes = String(now.getMinutes()).padStart(2, '0');
    const seconds = String(now.getSeconds()).padStart(2, '0');
    const ampm = hours >= 12 ? 'pm' : 'am';
    hours = hours % 12;
    hours = hours ? hours : 12; // the hour '0' should be '12'
    const strHours = String(hours).padStart(2, '0');

    const timeStr = `${strHours}:${minutes}:${seconds} ${ampm} IST`;

    const dateEl = document.getElementById('current-date');
    const timeEl = document.getElementById('current-time');

    if (dateEl) dateEl.textContent = dateStr;
    if (timeEl) timeEl.textContent = timeStr;
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    // 1. Initialize DOM Cache (Global Performance Optimization)
    scalpingStatus = document.getElementById('scalping-status');
    futurePrice = document.getElementById('future-price');
    cePrice = document.getElementById('ce-price');
    pePrice = document.getElementById('pe-price');
    basisValue = document.getElementById('basis-value');
    biasFill = document.getElementById('bias-fill');
    straddleValue = document.getElementById('straddle-value');
    scalpingSignalBox = document.getElementById('scalping-signal-box');
    scalpSignalIcon = document.getElementById('scalp-signal-icon');
    scalpSignalText = document.getElementById('scalp-signal-text');
    scalpSignalDesc = document.getElementById('scalp-signal-desc');
    ceStrike = document.getElementById('ce-strike');
    peStrike = document.getElementById('pe-strike');
    tradeSuggestion = document.getElementById('trade-suggestion');
    latencyDot = document.getElementById('latency-dot');
    latencyText = document.getElementById('latency-text');
    momentumBar = document.getElementById('momentum-bar');
    velocityValue = document.getElementById('velocity-value');
    newsTicker = document.getElementById('news-ticker');
    pcrBadgeSignal = document.getElementById('pcr-badge-signal');
    pcrValueSignal = document.getElementById('pcr-value-signal');
    pcrBadge = document.getElementById('pcr-badge');
    pcrValueEl = document.getElementById('pcr-value');

    connectWebSocket();
    initStraddleChart();

    // Update date/time every second
    // Initial update
    updateDateTime();
    setInterval(updateDateTime, 1000);

    // ==========================================================
    // MARKET STATUS INDICATOR (NEW)
    // ==========================================================
    const marketSignalBadge = document.getElementById('market-status-badge');
    const marketStateText = document.getElementById('market-state-text');

    function updateMarketStatusIndicator() {
        const now = new Date();

        // Use the robust MarketSchedule logic from market_schedule.js
        let status = { isOpen: false, statusText: "MARKET CLOSED", cssClass: "closed" };

        if (typeof MarketSchedule !== 'undefined') {
            status = MarketSchedule.getStatus(now);
        }

        if (marketSignalBadge && marketStateText) {
            // Reset classes
            marketSignalBadge.classList.remove('open', 'closed');

            // Apply new status
            marketSignalBadge.classList.add(status.cssClass);
            marketStateText.textContent = status.statusText;
        }
    }

    // Update immediately and then every minute
    updateMarketStatusIndicator();
    setInterval(updateMarketStatusIndicator, 60000); // Check every minute

    // Poll scalper data every 1 second
    setInterval(updateScalper, 1000);
    updateScalper(); // Initial fetch
    loadSignalHistory(); // Load saved history
});

// Format symbol: "NIFTY27JAN2525050CE" -> "27 Jan 25050CE"
// Moved to global scope for reuse in history log
const formatSymbol = (symbol) => {
    if (!symbol || symbol.length < 10) return symbol;

    // Pattern 1: NIFTY27JAN25100CE (Old)
    // Pattern 2: NIFTY03FEB2525300CE (New API standard?)
    // Regex: NIFTY + (Day:2) + (Month:3) + (Year:2) + (Strike:Var) + (Type:2)
    const match = symbol.match(/NIFTY(\d{2})([A-Z]{3})(\d{2})(\d+)(CE|PE)/);

    if (match) {
        const [, day, month, year, strike, type] = match;
        // Capitalize month properly just in case
        const monthTitle = month.charAt(0).toUpperCase() + month.slice(1).toLowerCase();

        return `${day} ${monthTitle} ${strike}${type}`;
    }
    return symbol;
};

function loadSignalHistory() {
    const historyList = document.getElementById('signal-history-list');
    if (!historyList) return;

    const saved = localStorage.getItem('scalp_signal_history');
    if (saved) {
        try {
            const items = JSON.parse(saved);
            if (Array.isArray(items) && items.length > 0) {
                const emptyMsg = historyList.querySelector('.history-empty');
                if (emptyMsg) emptyMsg.remove();

                // Items saved as [newest, ..., oldest]
                // We append them in order because we are rebuilding from top down?
                // No, prepend adds to top. If we iterate [newest, oldest], and prepend each, oldest ends up on top!
                // So we must iterate in REVERSE (oldest to newest) to prepend correctly?
                // OR use appendChild. Since list is empty (except empty msg), if we append [newest, oldest], newest is first. Correct.

                items.forEach(data => {
                    const item = createHistoryItem(data.signal, data.timestamp, data);
                    historyList.appendChild(item);
                });

                // Restore last state
                if (items[0]) window.lastSignalState = items[0].signal;
            }
        } catch (e) {
            console.error(e);
        }
    }
}

function createHistoryItem(signal, time, data) {
    const item = document.createElement('div');
    const typeClass = signal === 'BUY CALL' ? 'call' :
        signal === 'BUY PUT' ? 'put' :
            signal === 'TRAP' ? 'trap' : '';

    item.className = `history-item ${typeClass}`;

    const icon = signal === 'BUY CALL' ? '🟢' :
        signal === 'BUY PUT' ? '🔴' :
            '⚠️';

    // Dynamic Details Logic
    let detailsHtml = '';

    if (signal === 'BUY CALL') {
        // Show Full Strike - Price
        // e.g., "27 Jan 25050CE - ₹103.50"
        const symbol = data.ce_symbol ? formatSymbol(data.ce_symbol) : 'ATM CE';
        const price = data.ce_price ? `₹${data.ce_price.toFixed(2)}` : '--';
        detailsHtml = `<span style="color:#fff; font-weight:500;">${symbol}</span> <span style="opacity:0.6; margin:0 5px;">-</span> <span style="color:#00E396;">${price}</span>`;
    } else if (signal === 'BUY PUT') {
        const symbol = data.pe_symbol ? formatSymbol(data.pe_symbol) : 'ATM PE';
        const price = data.pe_price ? `₹${data.pe_price.toFixed(2)}` : '--';
        detailsHtml = `<span style="color:#fff; font-weight:500;">${symbol}</span> <span style="opacity:0.6; margin:0 5px;">-</span> <span style="color:#FF4560;">${price}</span>`;
    } else if (signal === 'TRAP') {
        // Keep PCR/Bias for TRAP diagnosis if available, or just "Trap Detected"
        // User asked to remove PCR/Bias generally, but maybe useful here?
        // Let's stick to minimal.
        const pcrStr = data.pcr ? `PCR: ${data.pcr}` : '';
        detailsHtml = `<span style="color:#ffaa00;">Trap Detected</span> ${pcrStr ? `<span style="opacity:0.5; font-size:0.8em; margin-left:5px;">(${pcrStr})</span>` : ''}`;
    } else {
        // Fallback/Legacy
        const pcrStr = data.pcr ? `PCR: ${data.pcr}` : '';
        const basisStr = data.basis ? `Bias: ${data.basis}` : '';
        detailsHtml = `${pcrStr} <span style="opacity:0.3">|</span> ${basisStr}`;
    }

    item.innerHTML = `
        <div class="h-left" style="display:flex; align-items:center; gap:8px;">
            <div class="h-time" style="min-width:65px;">${time}</div>
            <div class="h-signal" style="font-weight:700;">${icon} ${signal}</div>
        </div>
        <div class="h-details">
            ${detailsHtml}
        </div>
    `;
    return item;
}

function updateSignalHistory(signal, data) {
    const historyList = document.getElementById('signal-history-list');
    if (!historyList) return;

    // Remove empty placeholder
    const emptyMsg = historyList.querySelector('.history-empty');
    if (emptyMsg) emptyMsg.remove();

    const time = new Date().toLocaleTimeString('en-US', { hour12: true, hour: '2-digit', minute: '2-digit', second: '2-digit' });

    // Create & Prepend UI (Pass full data for extracting prices/symbols)
    const item = createHistoryItem(signal, time, data);
    historyList.prepend(item);

    // Limit to 5
    if (historyList.children.length > 5) {
        historyList.removeChild(historyList.lastElementChild);
    }

    // Save
    saveHistory(signal, time, data);
}

function saveHistory(signal, time, data) {
    try {
        let items = [];
        const saved = localStorage.getItem('scalp_signal_history');
        if (saved) items = JSON.parse(saved);

        // Store minimal required data to save space
        const entry = {
            signal,
            timestamp: time,
            pcr: data.pcr ? data.pcr.toFixed(2) : null,
            basis: data.basis ? data.basis.toFixed(1) : null,
            ce_symbol: data.ce_symbol,
            pe_symbol: data.pe_symbol,
            ce_price: data.ce_price,
            pe_price: data.pe_price
        };

        items.unshift(entry);
        if (items.length > 5) items = items.slice(0, 5);

        localStorage.setItem('scalp_signal_history', JSON.stringify(items));
    } catch (e) { }
}
