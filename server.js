const express = require('express');
const bodyParser = require('body-parser');
const WebSocket = require('ws');
const { WebcastPushConnection } = require('tiktok-live-connector');
require('axios');

const app = express();
const port = process.argv[2] || 8080; // Change default port to 8080

let tiktokConnection = null;
let currentKeyword = '';
let viewersSet = new Set();
let wsClient = null;

app.use(bodyParser.json());

const server = app.listen(port, () => {
    console.log(`🚀 Server is running on http://localhost:${port}`);
});

const shutdown = () => {
    console.log('🛑 Shutting down server...');
    if (tiktokConnection) {
        tiktokConnection.disconnect();
        console.log('🔌 TikTok connection closed');
    }
    if (wsClient) {
        wsClient.close();
        console.log('❌ WebSocket client closed');
    }
    server.close(() => {
        console.log('✅ HTTP server closed');
        process.exit(0);
    });
};

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

// WebSocket setup
const wss = new WebSocket.Server({ server });

// Heartbeat function to keep WebSocket alive
function heartbeat() {
    this.isAlive = true;
}

wss.on('connection', ws => {
    console.log('🔌 GUI connected via WebSocket');
    ws.isAlive = true;

    // Listen for pong messages to confirm the client is alive
    ws.on('pong', heartbeat);

    wsClient = ws;

    ws.on('close', () => {
        console.log('❌ GUI WebSocket disconnected');
        wsClient = null;
    });

    ws.on('error', error => {
        console.log(`❌ WebSocket error: ${error}`);
    });
});

// Periodically check if WebSocket clients are alive
const interval = setInterval(() => {
    wss.clients.forEach(ws => {
        if (!ws.isAlive) {
            console.log('❌ Terminating unresponsive WebSocket client');
            return ws.terminate();
        }

        ws.isAlive = false;
        ws.ping(); // Send a ping to the client
    });
}, 30000); // Check every 30 seconds

// Cleanup interval on server shutdown
server.on('close', () => {
    clearInterval(interval);
});

// Utility to check if a message matches the keyword
function isValidKeywordMessage(message, keyword) {
    const cleaned = message.trim().toLowerCase();

    // Reject if the whole message is just "@keyword"
    if (cleaned === '@' + keyword) return false;

    const parts = cleaned.split(/\s+/);

    // Remove leading @mentions
    const words = parts.filter(word => !word.startsWith('@'));

    if (words.length === 0) return false;

    // Regex to match the keyword followed only by emojis, symbols, or numbers — no letters
    const regex = new RegExp(`^${keyword}(?![a-z])[^\sa-zA-Z@]*$`);

    // All remaining words must be valid keyword matches
    for (const word of words) {
        if (!regex.test(word)) {
            return false;
        }
    }

    return true;
}

function createKeywordMatcher(keyword) {
    const normalizeText = (text) => {
        return text.toLowerCase()
            .replace(/['']/g, "'")    // normalize apostrophes to single type
            .replace(/\s+/g, ' ')     // normalize spaces
            .trim();
    };

    // Normalize input keyword
    const normalizedKeyword = normalizeText(keyword);
    const words = normalizedKeyword.split(/\s+/);
    
    if (words.length > 1) {
        // For multi-word phrases
        const phrasePattern = words
            .map(word => {
                const baseWord = word.replace(/'/g, ""); // remove apostrophes for base matching
                const escaped = baseWord.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                return `${escaped}(?:'s|s)?`; // optional 's or s suffix
            })
            .join("['''\\s]+"); // allow any type of apostrophe or space between words

        return new RegExp(
            `(?:^|\\s|@)${phrasePattern}(?:[!.?]*[\\u{1F300}-\\u{1F9FF}]*|\\s|$)`,
            'iu'
        );
    } else {
        // For single words
        const baseWord = words[0].replace(/'/g, ""); // remove apostrophes for base matching
        const escaped = baseWord.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const repeated = escaped.replace(/(.)\1/g, '$1{2,}');
        
        return new RegExp(
            `(?:^|\\s|@)(?:${escaped}(?:'s|s)?|${repeated})(?:[!.?]*[\\u{1F300}-\\u{1F9FF}]*|\\s|$)`,
            'iu'
        );
    }
}

// Start TikTok connection
app.post('/start', async (req, res) => {
    const { username } = req.body;
    if (!username) return res.status(400).send('Username required.');

    try {
        tiktokConnection = new WebcastPushConnection(username);

        tiktokConnection.on('chat', data => {
            const nickname = data.nickname?.trim() || '';
            const message = data.comment?.trim() || '';
            console.log(`💬 ${nickname}: ${message}`);

            if (currentKeyword && !viewersSet.has(nickname)) {
                const matcher = createKeywordMatcher(currentKeyword);
                if (matcher.test(message)) {
                    viewersSet.add(nickname);
                    if (wsClient && wsClient.readyState === WebSocket.OPEN) {
                        wsClient.send(nickname);
                    }
                }
            }
        });

        await tiktokConnection.connect();
        console.log(`✅ Connected to TikTok Live @${username}`);
        res.send('Connected');
    } catch (err) {
        console.error('❌ Failed to connect:', err);
        res.status(500).send('Connection failed');
    }
});

// Set keyword
app.post('/keyword', (req, res) => {
    const { keyword } = req.body;
    if (!keyword) return res.status(400).send('Keyword required.');
    currentKeyword = keyword.trim();
    viewersSet.clear();
    console.log(`🔑 Keyword set: ${currentKeyword}`);
    res.send('Keyword set');
});

// Reset keyword endpoint
app.post('/clearKeyword', (req, res) => {
    currentKeyword = '';
    viewersSet.clear();
    console.log('🔑 Keyword cleared');
    
    // Send reset message to GUI
    if (wsClient && wsClient.readyState === WebSocket.OPEN) {
        wsClient.send('clearViewers');
    }

    res.send('Keyword cleared');
});

// Add these endpoints
app.post('/disconnect', async (req, res) => {
    if (tiktokConnection) {
        await tiktokConnection.disconnect();
        tiktokConnection = null;
    }
    res.send('Disconnected from TikTok stream');
});

// Shutdown endpoint
app.post('/shutdown', (req, res) => {
    res.send('Shutting down...');
    shutdown();
});
