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
let scalpingSignalBox, scalpSignalIcon, scalpSignalText, scalpSignalDesc;
let ceStrike, peStrike, tradeSuggestion, latencyDot, latencyText, momentumBar;
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
        const changeClass = data.change >= 0 ? 'positive' : 'negative';
        const arrow = data.change >= 0 ? '▲' : '▼';
        return `
            <div class="ticker-item">
                <span class="ticker-name">${name}</span>
                <span class="ticker-value">${data.price.toFixed(2)}</span>
                <span class="ticker-change ${changeClass}">
                    ${data.change > 0 ? '+' : ''}${data.change.toFixed(2)} 
                    (${data.p_change.toFixed(2)}%) ${arrow}
                </span>
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
    const indices = ['nifty', 'sensex', 'banknifty', 'midcpnifty', 'niftysmallcap', 'indiavix'];
    const displayNames = {
        'nifty': 'NIFTY 50', 'sensex': 'SENSEX', 'banknifty': 'BANKNIFTY',
        'midcpnifty': 'MIDCPNIFTY', 'niftysmallcap': 'NIFTY SMALLCAP', 'indiavix': 'INDIA VIX'
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
        const items = Array.from(tickerContainer.children);
        indices.forEach((key, index) => {
            if (index >= items.length) return;
            const data = tickers[key];
            if (!data) return;

            const item = items[index];
            const valueEl = item.querySelector('.ticker-value');
            const changeEl = item.querySelector('.ticker-change');

            if (valueEl) valueEl.textContent = data.price.toFixed(2);
            if (changeEl) {
                const changeClass = data.change >= 0 ? 'positive' : 'negative';
                const arrow = data.change >= 0 ? '▲' : '▼';
                changeEl.className = `ticker-change ${changeClass}`;
                changeEl.textContent = `${data.change > 0 ? '+' : ''}${data.change.toFixed(2)} (${data.p_change.toFixed(2)}%) ${arrow}`;
            }
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

function formatPrice(price) {
    return price.toLocaleString('en-IN', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
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

function updateScalperUI(data) {
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
        // This prevents the "Graph stuck in middle" issue where labels > data
        const validHistory = data.history.filter(h => h.straddle !== null && h.straddle > 0);

        // Slice last 40 points for "Ultra Fast" zoom (approx 40 seconds)
        const recentHistory = validHistory.slice(-40);

        straddleChart.data.labels = recentHistory.map(h => h.time);
        straddleChart.data.datasets[0].data = recentHistory.map(h => h.straddle);

        // DYNAMIC Y-AXIS SCALING (Heartbeat View)
        // Calculate min/max with ±2 padding for tight zoom
        const displayValues = straddleChart.data.datasets[0].data;
        if (displayValues.length > 0) {
            const minVal = Math.min(...displayValues);
            const maxVal = Math.max(...displayValues);
            straddleChart.options.scales.y.suggestedMin = minVal - 2;
            straddleChart.options.scales.y.suggestedMax = maxVal + 2;
        }

        // TREND-BASED LINE COLOR
        const trend = data.trend || 'FLAT';
        let lineColor = '#ffaa00'; // Default: Amber
        let fillColor = 'rgba(255, 170, 0, 0.05)';

        if (trend === 'RISING') {
            lineColor = '#00E396';  // Bright Green - Momentum
            fillColor = 'rgba(0, 227, 150, 0.1)';
        } else if (trend === 'FALLING') {
            lineColor = '#FF4560';  // Orange-Red - Decay
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

            // More helpful wait message
            if (trend === 'FALLING') {
                scalpSignalDesc.textContent = '📉 Straddle Decay - Do Not Enter';
            } else {
                scalpSignalDesc.textContent = `${sentiment} | Waiting for trend...`;
            }
        }
    }

    // Update ATM Strike badges with full symbol names
    const ceStrike = document.getElementById('ce-strike');
    const peStrike = document.getElementById('pe-strike');

    // Format symbol: "NIFTY27JAN2525050CE" -> "27 Jan 25050CE"
    const formatSymbol = (symbol) => {
        if (!symbol || symbol.length < 10) return symbol;
        // Extract date and strike from symbol like "NIFTY27JAN2525050CE"
        const match = symbol.match(/NIFTY(\d{2})([A-Z]{3})(\d{2})(\d+)(CE|PE)/);
        if (match) {
            const [, day, month, year, strike, type] = match;
            const monthMap = {
                JAN: 'Jan', FEB: 'Feb', MAR: 'Mar', APR: 'Apr', MAY: 'May', JUN: 'Jun',
                JUL: 'Jul', AUG: 'Aug', SEP: 'Sep', OCT: 'Oct', NOV: 'Nov', DEC: 'Dec'
            };
            return `${day} ${monthMap[month] || month} ${strike}${type}`;
        }
        return symbol;
    };

    if (data.ce_symbol && ceStrike) {
        ceStrike.textContent = formatSymbol(data.ce_symbol);
    } else if (data.atm_strike && ceStrike) {
        ceStrike.textContent = data.atm_strike; // Fallback
    }

    if (data.pe_symbol && peStrike) {
        peStrike.textContent = formatSymbol(data.pe_symbol);
    } else if (data.atm_strike && peStrike) {
        peStrike.textContent = data.atm_strike; // Fallback
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

    // 2. Velocity Momentum Bar
    if (data.velocity !== undefined && momentumBar) {
        // Cap at 10 pts/sec for 100% width
        const velocity = Math.abs(data.velocity);
        const width = Math.min((velocity / 10) * 100, 100);
        momentumBar.style.width = `${width}%`;
    }

    // 3. PCR Badge (Signal Box)
    if (data.pcr !== undefined && data.pcr !== null && pcrBadgeSignal && pcrValueSignal) {
        pcrBadgeSignal.style.display = 'block';
        pcrValueSignal.textContent = data.pcr.toFixed(2);

        if (data.pcr > 1.0) {
            pcrValueSignal.style.color = 'var(--accent-green)';
        } else if (data.pcr < 0.7) {
            pcrValueSignal.style.color = 'var(--accent-red)';
        } else {
            pcrValueSignal.style.color = 'var(--text-muted)';
        }
    } else if (pcrBadgeSignal) {
        pcrBadgeSignal.style.display = 'none';
    }

    // Update PCR Badge (New)
    if (data.pcr !== undefined && pcrBadge && pcrValueEl) {
        pcrBadge.style.display = 'block';
        pcrValueEl.textContent = data.pcr.toFixed(2);

        pcrBadge.classList.remove('bullish', 'bearish');
        if (data.pcr > 1.0) {
            pcrBadge.classList.add('bullish');
        } else if (data.pcr < 0.7) {
            pcrBadge.classList.add('bearish');
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
});
