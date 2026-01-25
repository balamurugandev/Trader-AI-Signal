/**
 * Market Schedule Configuration for 2026
 * Handles Holidays, Weekends, and Special Trading Sessions.
 */

const MarketSchedule = {
    // Standard Hours (IST)
    MARKET_OPEN: 915,  // 09:15 AM
    MARKET_CLOSE: 1530, // 03:30 PM

    // 2026 Holidays (Closed Days)
    HOLIDAYS: [
        "2026-01-26", // Republic Day
        "2026-03-03", // Holi
        "2026-03-26", // Ram Navami
        "2026-03-31", // Mahavir Jayanti
        "2026-04-03", // Good Friday
        "2026-04-14", // Dr. Ambedkar Jayanti
        "2026-05-01", // Maharashtra Day
        "2026-05-28", // Bakri Id (Eid-ul-Adha)
        "2026-06-26", // Muharram
        "2026-08-15", // Independence Day
        "2026-09-14", // Ganesh Chaturthi
        "2026-10-02", // Mahatma Gandhi Jayanti
        "2026-10-20", // Dussehra
        "2026-11-10", // Diwali Balipratipada
        "2026-11-24", // Gurunanak Jayanti
        "2026-12-25"  // Christmas
    ],

    // Special Trading Sessions (Date -> Open/Close Times in HHMM)
    SPECIAL_SESSIONS: {
        "2026-02-01": { open: 915, close: 1530, name: "Union Budget (Special Sunday)" },
        "2026-11-08": { open: 1800, close: 1915, name: "Diwali Muhurat Trading" } // Approx 1hr evening window
    },

    /**
     * Checks if the market is open at the given Date object.
     * @param {Date} now - Current Date object
     * @returns {Object} { isOpen: boolean, statusText: string, cssClass: string }
     */
    getStatus: function (now) {
        // 1. Setup Data
        // Convert to IST string YYYY-MM-DD for key lookup
        const istOffset = 5.5 * 60 * 60 * 1000;
        const istDate = new Date(now.getTime() + istOffset);

        const yyyy = istDate.getUTCFullYear();
        const mm = String(istDate.getUTCMonth() + 1).padStart(2, '0');
        const dd = String(istDate.getUTCDate()).padStart(2, '0');
        const dateKey = `${yyyy}-${mm}-${dd}`;

        const day = istDate.getUTCDay(); // 0=Sun, 6=Sat
        const hours = istDate.getUTCHours();
        const minutes = istDate.getUTCMinutes();
        const currentTimeVal = hours * 100 + minutes;

        // 2. Check Special Sessions First (Overrides Weekends/Holidays)
        if (this.SPECIAL_SESSIONS[dateKey]) {
            const session = this.SPECIAL_SESSIONS[dateKey];
            if (currentTimeVal >= session.open && currentTimeVal < session.close) {
                return { isOpen: true, statusText: `MARKET OPEN (${session.name})`, cssClass: "open" };
            } else if (currentTimeVal < session.open) {
                return { isOpen: false, statusText: `CLOSED (Opens ${Math.floor(session.open / 100)}:${String(session.open % 100).padStart(2, '0')})`, cssClass: "closed" };
            } else {
                return { isOpen: false, statusText: "MARKET CLOSED", cssClass: "closed" };
            }
        }

        // 3. Check Holidays
        if (this.HOLIDAYS.includes(dateKey)) {
            return { isOpen: false, statusText: "MARKET CLOSED (Holiday)", cssClass: "closed" };
        }

        // 4. Check Weekends
        if (day === 0 || day === 6) {
            return { isOpen: false, statusText: "MARKET CLOSED", cssClass: "closed" };
        }

        // 5. Normal Trading Hours
        if (currentTimeVal >= this.MARKET_OPEN && currentTimeVal < this.MARKET_CLOSE) {
            return { isOpen: true, statusText: "MARKET OPEN", cssClass: "open" };
        }

        return { isOpen: false, statusText: "MARKET CLOSED", cssClass: "closed" };
    }
};
