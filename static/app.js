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

// WebSocket connection
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
    if (data.last_price !== null) {
        currentPrice.textContent = formatPrice(data.last_price);
    }

    // Update tick history
    updateTickTable(data.tick_history);

    // Update indicators
    updateIndicators(data.rsi, data.ema, data.last_price);

    // Update signal
    updateSignal(data.signal, data.candles_count);

    // Update timestamp
    lastUpdate.textContent = `Last Update: ${new Date().toLocaleTimeString()}`;
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
    if (!ticks || ticks.length === 0) return;

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
    if (rsi !== null) {
        rsiValue.textContent = rsi.toFixed(2);

        // Update RSI bar
        rsiBar.style.width = `${rsi}%`;
        rsiBar.classList.remove('oversold', 'overbought');

        if (rsi < 30) {
            rsiStatus.textContent = '⬆️ OVERSOLD';
            rsiStatus.style.color = '#00ff88';
            rsiBar.classList.add('oversold');
        } else if (rsi > 70) {
            rsiStatus.textContent = '⬇️ OVERBOUGHT';
            rsiStatus.style.color = '#ff4466';
            rsiBar.classList.add('overbought');
        } else {
            rsiStatus.textContent = '↔️ NEUTRAL';
            rsiStatus.style.color = '#ffaa00';
        }
    } else {
        rsiValue.textContent = '--';
        rsiStatus.textContent = 'Need more data...';
        rsiStatus.style.color = '#a0a0b0';
    }

    // EMA
    if (ema !== null) {
        emaValue.textContent = `₹${formatPrice(ema)}`;

        if (price !== null) {
            if (price > ema) {
                emaStatus.textContent = '⬆️ Price ABOVE EMA';
                emaStatus.style.color = '#00ff88';
            } else {
                emaStatus.textContent = '⬇️ Price BELOW EMA';
                emaStatus.style.color = '#ff4466';
            }
        }
    } else {
        emaValue.textContent = '--';
        emaStatus.textContent = 'Need more data...';
        emaStatus.style.color = '#a0a0b0';
    }
}

function updateSignal(signal, candlesCount) {
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

// Scalping DOM Elements
const futurePrice = document.getElementById('future-price');
const cePrice = document.getElementById('ce-price');
const pePrice = document.getElementById('pe-price');
const basisValue = document.getElementById('basis-value');
const biasFill = document.getElementById('bias-fill');
const straddleValue = document.getElementById('straddle-value');
const scalpingStatus = document.getElementById('scalping-status');
const scalpingSignalBox = document.getElementById('scalping-signal-box');
const scalpSignalIcon = document.getElementById('scalp-signal-icon');
const scalpSignalText = document.getElementById('scalp-signal-text');
const scalpSignalDesc = document.getElementById('scalp-signal-desc');

// Chart.js instance
let straddleChart = null;

// Custom Plugin: Pulsing Dot + Price Label at Latest Point
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

        // Pulsing outer ring (animated via CSS on wrapper, here just static glow)
        ctx.save();
        ctx.beginPath();
        ctx.arc(x, y, 8, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(255, 170, 0, 0.3)';
        ctx.fill();

        // Solid inner dot
        ctx.beginPath();
        ctx.arc(x, y, 4, 0, Math.PI * 2);
        ctx.fillStyle = '#ffaa00';
        ctx.fill();
        ctx.restore();

        // Price Label
        ctx.save();
        ctx.font = 'bold 11px Inter, sans-serif';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'middle';

        const text = `₹${value.toFixed(2)}`;
        const textWidth = ctx.measureText(text).width;
        const padding = 6;
        const labelX = x + 12;
        const labelY = y;

        // Background pill
        ctx.fillStyle = 'rgba(18, 18, 26, 0.9)';
        ctx.strokeStyle = '#ffaa00';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.roundRect(labelX - padding, labelY - 10, textWidth + padding * 2, 20, 4);
        ctx.fill();
        ctx.stroke();

        // Text
        ctx.fillStyle = '#ffaa00';
        ctx.fillText(text, labelX, labelY);
        ctx.restore();
    }
};
Chart.register(lastPointPlugin);

function initStraddleChart() {
    const ctx = document.getElementById('straddleChart');
    if (!ctx) return;

    straddleChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Straddle Price',
                data: [],
                borderColor: '#ffaa00',
                backgroundColor: 'rgba(255, 170, 0, 0.1)',
                borderWidth: 2,
                fill: true,
                tension: 0.3,
                pointRadius: 0,
                pointHoverRadius: 4
            }]
        },
        options: {
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
                    ticks: { color: '#606070', maxTicksLimit: 6 }
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
            const labels = data.history.map(h => h.time);
            const values = data.history.map(h => h.straddle).filter(v => v !== null);

            const displayLabels = labels.slice(-30);
            const displayValues = values.slice(-30);

            straddleChart.data.labels = displayLabels;
            straddleChart.data.datasets[0].data = displayValues;

            // DYNAMIC Y-AXIS SCALING (Heartbeat View)
            // Calculate min/max with ±2 padding for tight zoom
            if (displayValues.length > 0) {
                const minVal = Math.min(...displayValues);
                const maxVal = Math.max(...displayValues);
                straddleChart.options.scales.y.suggestedMin = minVal - 2;
                straddleChart.options.scales.y.suggestedMax = maxVal + 2;
            }

            // TREND-BASED LINE COLOR
            const trend = data.trend || 'FLAT';
            let lineColor = '#ffaa00'; // Default: Amber
            let fillColor = 'rgba(255, 170, 0, 0.1)';

            if (trend === 'RISING') {
                lineColor = '#00E396';  // Bright Green - Momentum
                fillColor = 'rgba(0, 227, 150, 0.15)';
            } else if (trend === 'FALLING') {
                lineColor = '#FF4560';  // Orange-Red - Decay
                fillColor = 'rgba(255, 69, 96, 0.15)';
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

        // Update ATM Strike badges
        const ceStrike = document.getElementById('ce-strike');
        const peStrike = document.getElementById('pe-strike');
        if (data.atm_strike) {
            if (ceStrike) ceStrike.textContent = data.atm_strike;
            if (peStrike) peStrike.textContent = data.atm_strike;
        }

        // Update Trade Suggestion
        const tradeSuggestion = document.getElementById('trade-suggestion');
        if (data.suggestion && tradeSuggestion) {
            tradeSuggestion.textContent = data.suggestion;

            // Dynamic coloring
            tradeSuggestion.style.color = 'var(--text-primary)'; // Default
            if (data.suggestion.includes('BUY')) {
                if (data.suggestion.includes('CE')) tradeSuggestion.style.color = 'var(--accent-green)';
                if (data.suggestion.includes('PE')) tradeSuggestion.style.color = 'var(--accent-red)';
            }
        }

        // Update PCR Badge (New)
        const pcrBadge = document.getElementById('pcr-badge');
        const pcrValueEl = document.getElementById('pcr-value');

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

    } catch (error) {
        console.error('Scalper update error:', error);
    }
}

// =============================================================================
// DATE/TIME UPDATER
// =============================================================================
function updateDateTime() {
    const now = new Date();

    // Format date: Fri, 24 Jan 2026
    const dateOptions = { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' };
    const dateStr = now.toLocaleDateString('en-IN', dateOptions);

    // Format time: 11:17:43 PM IST
    const timeOptions = { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true };
    const timeStr = now.toLocaleTimeString('en-IN', timeOptions) + ' IST';

    const dateEl = document.getElementById('current-date');
    const timeEl = document.getElementById('current-time');

    if (dateEl) dateEl.textContent = dateStr;
    if (timeEl) timeEl.textContent = timeStr;
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    connectWebSocket();
    initStraddleChart();

    // Update date/time every second
    updateDateTime();
    setInterval(updateDateTime, 1000);

    // Poll scalper data every 1 second
    setInterval(updateScalper, 1000);
    updateScalper(); // Initial fetch
});
